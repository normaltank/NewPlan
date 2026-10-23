'use strict';
const $ = id => document.getElementById(id);
let current = null, timer = null, submitting = false, ready = false, maxFiles = 20;
const active = job => job && ['running', 'stopping', 'finalizing'].includes(job.status);
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作未完成，请重试');
  return data;
}
function error(message = '') {$('error').textContent = message; $('error').hidden = !message;}
function controls() {
  $('inputs').disabled = !ready || submitting || active(current);
  $('quit').disabled = !ready || submitting || active(current);
  $('start').disabled = !ready || submitting || active(current) || $('files').files.length > maxFiles;
}
function renderProgress(job) {
  const total = Math.max(0, Number(job.total) || 0);
  const completed = Math.min(total, Math.max(0, Number(job.completed) || 0));
  const done = job.status === 'completed' && job.results_ready;
  const preparing = job.status === 'finalizing' || (active(job) && total > 0 && completed === total);
  $('progress-area').hidden = !active(job) && !done;
  if (done) {
    $('progress').value = 100;
    $('progress-text').textContent = '全部完成';
    $('progress-percent').textContent = '100%';
  } else if (preparing || !total) {
    $('progress').removeAttribute('value');
    $('progress-text').textContent = preparing ? '正在整理下载文件…' : '正在准备…';
    $('progress-percent').textContent = '';
  } else {
    const percent = Math.floor(completed * 100 / total);
    $('progress').value = percent;
    $('progress-text').textContent = `已完成 ${completed} / ${total}`;
    $('progress-percent').textContent = `${percent}%`;
  }
}
function renderSummary(job) {
  const body = $('summary').querySelector('tbody');
  body.replaceChildren();
  $('summary').hidden = !job.results_ready;
  if (!job.results_ready) return;
  for (const values of job.summary_rows) {
    const row = document.createElement('tr');
    values.forEach((value, index) => {
      const cell = document.createElement('td');
      cell.textContent = value;
      if (index === 2) cell.className = {'正确':'result-correct', '错误':'result-error', '特殊情况':'result-special'}[value] || '';
      row.append(cell);
    });
    body.append(row);
  }
}
function render(job) {
  current = job;
  $('result').hidden = !job;
  controls();
  if (!job) return;
  const states = {
    running:['正在核验…','请稍等，完成后即可下载结果。'],
    stopping:['正在停止…','请稍等。'],
    finalizing:['正在整理结果…','马上就好。'],
    completed:['核验完成','表中标为“特殊情况”的学院，请人工查看原网页。'],
    cancelled:['已停止','可以重新放入名单，开始核验。'],
    interrupted:['上次没有完成','请重新放入名单，开始核验。'],
    failed:['没能完成核验','请把文件夹里的 MissionB.log 发给我们。'],
  };
  const [title, description] = states[job.status] || ['本次未完成','请发送 MissionB.log 给维护人员。'];
  $('status-title').textContent = title;
  $('status-text').textContent = description;
  if (job.status === 'completed') {
    $('status-text').textContent = '下载包含核验结果和“错误”学院的更新链接表。';
    if (job.counts['特殊情况']) $('status-text').textContent += '“特殊情况”请人工查看原网页。';
  }
  renderProgress(job);
  renderSummary(job);
  $('download').hidden = !job.download_ready;
  if (job.download_ready) $('download').href = `/api/jobs/${job.id}/download`;
  else $('download').removeAttribute('href');
  $('cancel').hidden = !['running','stopping'].includes(job.status);
  $('cancel').disabled = job.status === 'stopping';
}
function schedule() {
  clearTimeout(timer);
  if (!active(current)) return;
  timer = setTimeout(async () => {
    try {render(await api(`/api/jobs/${current.id}`)); error();}
    catch (e) {error(e.message);}
    schedule();
  }, 1000);
}
function filePayload(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({name:file.name, content:reader.result.split(',')[1]});
    reader.onerror = () => reject(new Error('文件读取失败，请重新选择'));
    reader.readAsDataURL(file);
  });
}
$('files').addEventListener('change', () => {
  const files = [...$('files').files];
  $('file-names').textContent = files.length ? `已选择 ${files.length} / ${maxFiles} 个文件：` + files.map(f => f.name).join('、') : '尚未选择文件';
  error(files.length > maxFiles ? `每批最多${maxFiles}个文件，请减少文件后重试` : '');
  controls();
});
$('input-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (submitting || active(current)) return;
  error(); submitting = true; controls();
  try {
    const files = [...$('files').files];
    if (!files.length && !$('text').value.trim()) throw new Error('请选择文件或粘贴待核验名单');
    if (files.length > maxFiles || files.some(f => f.size > 10 * 1024 * 1024) || files.reduce((n,f) => n + f.size,0) > 20 * 1024 * 1024) throw new Error(`请拆分为较小批次，每批最多${maxFiles}个文件，单个文件不超过10MB、合计不超过20MB`);
    const job = await api('/api/start', {files:await Promise.all(files.map(filePayload)), text:$('text').value});
    render(job); schedule();
  } catch (e) {error(e.message);}
  finally {submitting = false; controls();}
});
$('cancel').addEventListener('click', async () => {
  $('cancel').disabled = true;
  try {render(await api(`/api/jobs/${current.id}/cancel`, {})); schedule();}
  catch (e) {error(e.message); $('cancel').disabled = false;}
});
$('quit').addEventListener('click', async () => {
  try {await api('/api/shutdown', {}); ready = false; controls(); clearTimeout(timer); error('工具已退出，可以关闭此页面。');}
  catch (e) {error(e.message);}
});
(async () => {
  try {
    const token = new URLSearchParams(location.hash.slice(1)).get('token');
    if (token) {history.replaceState(null, '', location.pathname); await api('/api/session', {token});}
    const state = await api('/api/state');
    maxFiles = state.max_files;
    $('file-limit').textContent = `支持 Excel 和文本文件，最多 ${maxFiles} 个文件`;
    if (state.automatic_support_mail) $('support-note').textContent = '遇到特殊情况，本批日志会自动发送给维护人员。';
    ready = true; render(state.job); schedule();
    if (!state.configured) {ready = false; controls(); $('quit').disabled = false; error('工具尚未配置完成，请联系维护人员。');}
  } catch (e) {error(e.message);}
})();
