"""Private support mail; independent of verification decisions and downloads."""
from email.message import EmailMessage
from email.utils import formatdate, parseaddr
import hashlib
import json
import queue
import re
import smtplib
import ssl
import threading
import zipfile

from app import atomic_json, now

MAX_ATTACHMENT_BYTES = 18 * 1024 * 1024


class DeliveryUncertain(Exception):
    """DATA was attempted but the remote acknowledgement was not received."""


class AttachmentTooLarge(Exception):
    pass


def load_config(path):
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding='utf-8'))
    for key in ('host', 'sender', 'recipient', 'password'):
        if not isinstance(value.get(key), str) or not value[key].strip() or any(c in value[key] for c in '\r\n'):
            raise ValueError('邮件配置不完整')
    for key in ('sender', 'recipient'):
        if parseaddr(value[key])[1] != value[key] or value[key].count('@') != 1:
            raise ValueError('邮件地址无效')
    if type(value.get('port', 465)) is not int or not 1 <= value.get('port', 465) <= 65535:
        raise ValueError('邮件端口无效')
    return {key: value[key] for key in ('host', 'sender', 'recipient', 'password')} | {'port': value.get('port', 465)}


def package_log(journal, job_id, target):
    """Extract one completed run, including its original startup and evidence."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    started = finished = False
    startup = None
    try:
        with journal.lock, journal.path.open(encoding='utf-8') as source, \
                zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive, \
                archive.open('MissionB.log', 'w', force_zip64=True) as output:
            for line in source:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record['event'] == 'startup':
                    startup = line
                if record.get('job_id') != job_id:
                    continue
                if record['event'] == 'run_started':
                    if startup:
                        output.write(journal.redact(startup).encode('utf-8'))
                    started = True
                if record['event'] not in ('run_started', 'evidence', 'run_finished', 'maintenance_error'):
                    continue
                output.write(journal.redact(line).encode('utf-8'))
                finished |= record['event'] == 'run_finished'
        if not started or not finished:
            raise ValueError('本批日志尚不完整')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def send_mail(config, job_id, count, version, attachment, before_send=lambda: None):
    if attachment.stat().st_size > MAX_ATTACHMENT_BYTES:
        raise AttachmentTooLarge('日志压缩包超过18MB，保留本地文件供人工传回')
    message = EmailMessage()
    message['From'] = config['sender']
    message['To'] = config['recipient']
    message['Subject'] = f'Mission B 特殊情况日志 · {job_id[:8]}'
    message['Date'] = formatdate(localtime=True)
    message['Message-ID'] = f'<missionb-{job_id}@{config["sender"].split("@", 1)[1]}>'
    message.set_content(f'Mission B 精简版 {version}\n任务：{job_id}\n特殊情况学院：{count}\n\n'
                        '附件为本次任务的脱敏日志，含已取得的网页和模型证据。\n'
                        '此通知不代表核验程序存在故障；请按保存的材料复核。\n')
    message.add_attachment(attachment.read_bytes(), maintype='application', subtype='zip',
                           filename=f'MissionB-log-{job_id[:8]}.zip')
    smtp = smtplib.SMTP_SSL(config['host'], config['port'], timeout=20, context=ssl.create_default_context())
    try:
        smtp.ehlo()
        smtp.login(config['sender'], config['password'])
        before_send()
        try:
            refused = smtp.send_message(message, from_addr=config['sender'], to_addrs=[config['recipient']])
        except (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused):
            raise
        except Exception as error:
            raise DeliveryUncertain('邮件提交后未获得确认，需人工确认是否已收到') from error
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
    finally:
        # QUIT failures after a positive DATA acknowledgement must not cause resend.
        try:
            smtp.close()
        except Exception:
            pass


class MailReporter:
    def __init__(self, root, journal, config, version):
        self.root, self.journal, self.config, self.version = root, journal, config, version
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.pending = queue.Queue()
        self.destination = hashlib.sha256(json.dumps({k: config[k] for k in ('host', 'port', 'sender', 'recipient')},
                                                     sort_keys=True).encode()).hexdigest()
        for path in sorted(root.glob('*/state.json')):
            try:
                state = json.loads(path.read_text(encoding='utf-8'))
                identifier = state['job_id']
                if not re.fullmatch('[a-f0-9]{32}', identifier) or path.parent.name != identifier:
                    raise ValueError('邮件记录标识无效')
                if state['destination'] != self.destination:
                    journal.write('mail_destination_changed', job_id=identifier)
                    continue
                if state['status'] == 'sending':
                    self.save(state, 'uncertain', error='程序在发送过程中退出，需人工确认是否已收到')
                elif state['status'] in ('queued', 'retry') and state['attempts'] < 3:
                    self.pending.put(state)
            except (OSError, ValueError, KeyError, TypeError):
                journal.write('mail_record_invalid', record=path.parent.name)
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def save(self, state, status, **values):
        with self.lock:
            if 'error' in values:
                values['error'] = self.journal.redact(str(values['error']))
            state.update(status=status, updated=now(), **values)
            atomic_json(self.root / state['job_id'] / 'state.json', state)
        self.journal.write('mail_' + status, job_id=state['job_id'], attempts=state['attempts'],
                           **{k: v for k, v in values.items() if k == 'error'})

    def submit(self, job_id, count):
        if not re.fullmatch('[a-f0-9]{32}', job_id) or type(count) is not int or count < 1:
            raise ValueError('邮件任务无效')
        with self.lock:
            if (self.root / job_id / 'state.json').exists():
                return
            state = dict(job_id=job_id, count=count, version=self.version, attempts=0,
                         destination=self.destination, created=now())
            self.save(state, 'queued')
            self.pending.put(state)

    def run(self):
        while not self.stopped.is_set():
            try:
                state = self.pending.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                self.deliver(state)
            except Exception as error:
                # A disk error cannot change verification/download state or lose other jobs.
                self.journal.write('mail_worker_error', job_id=state['job_id'], error=str(error))
            finally:
                self.pending.task_done()

    def deliver(self, state):
        job_id = state['job_id']
        try:
            self.save(state, 'queued', attempts=state['attempts'] + 1)
            attachment = package_log(self.journal, job_id, self.root / job_id / 'support.zip')
            send_mail(self.config, job_id, state['count'], state['version'], attachment,
                      before_send=lambda: self.save(state, 'sending'))
        except DeliveryUncertain as error:
            self.save(state, 'uncertain', error=str(error))
        except AttachmentTooLarge as error:
            self.save(state, 'failed', error=str(error))
        except Exception as error:
            self.save(state, 'retry' if state['attempts'] < 3 else 'failed', error=str(error))
        else:
            # Do not retry if persisting acceptance fails; 'sending' remains uncertain.
            self.save(state, 'sent', error='')

    def close(self):
        self.stopped.set()
        self.worker.join(1)
