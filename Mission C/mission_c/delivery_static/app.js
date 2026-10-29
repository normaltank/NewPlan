'use strict';
const $ = id => document.getElementById(id);
let current = null, ready = false, busy = false, issueOffset = 0, timer, exported = '';
let selected = new URLSearchParams(location.search).get('batch');
function node(tag, text) { const n = document.createElement(tag); if (text !== undefined) n.textContent = String(text); return n; }
function error(message = '') { $('error').textContent = message; $('error').hidden = !message; }
async function api(path, options = {}) {
  let response;
  try { response = await fetch(path, {...options, headers:{'X-Mission-C':'1', ...options.headers}}); }
  catch { throw Error('暂时无法连接本地服务，请保持服务窗口打开后重试。'); }
  let data;
  try { data = await response.json(); } catch { throw Error('服务暂时没有返回可用结果，请稍后重试。'); }
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : '操作未完成，请检查文件后重试。');
  return data;
}
function controls() {
  $('inputs').disabled = !ready || busy || !!current?.queued;
  $('start').disabled = busy || !current?.total;
  $('pause').disabled = busy || !!current?.paused;
  $('resume').disabled = busy;
  $('more-issues').disabled = busy;
}
async function action(fn) {
  if (busy) return;
  busy = true; error(); controls();
  try { await fn(); } catch (e) { error(e.message); }
  finally { busy = false; controls(); schedule(); }
}
function remember(id) {
  selected = id;
  history.replaceState(null, '', '?batch=' + encodeURIComponent(id));
  try { localStorage.setItem('mission-c-delivery-batch', id); } catch {}
}
async function choose(batch) {
  remember(batch.id); current = batch; issueOffset = 0; exported = '';
  $('downloads').replaceChildren(); $('issues').replaceChildren();
  await render(); await loadIssues();
}
async function render() {
  if (!current) { controls(); return; }
  $('result').hidden = false;
  const p = current.preflight;
  const started = current.queued || current.processed > 0;
  const done = !current.queued && current.total > 0 && current.processed === current.total;
  const itemLabel = started ? '条目' : '待处理条目';
  $('preflight').textContent = current.delivery_mode === 'demo' ? `离线示例已准备，共 ${current.total} 个${itemLabel}。` : `已预检 ${p.files} 个文件，共 ${current.total} 个${itemLabel}。`;
  $('schools').textContent = p.schools.map(s => `${s.school} · ${s.colleges.join('、')}`).join('；') + (p.duplicate_rows ? ` · 已合并 ${p.duplicate_rows} 个重复输入` : '');
  $('import-problems').hidden = !p.issue_count;
  $('issue-title').textContent = `${p.issue_count} 个导入问题，请查看`;
  $('mode-help').textContent = started ? '' : ({demo:'仅使用虚构本地材料，不访问网站。',cache:'开始后读取维护人员配置的本地材料，不访问网站。',live:'预检不会访问网页；点击开始后，将读取表中个人主页。',unavailable:'文件已保存，尚未开始。当前服务未开放网页处理，请联系维护人员，或先离线试用。'}[current.delivery_mode] || '');
  $('start').textContent = current.delivery_mode === 'demo' ? '开始离线试用' : '开始采集';
  $('start').hidden = started || !current.total;
  $('progress-area').hidden = !started;
  const failed = current.delivery_counts.exceptions;
  $('status-title').textContent = done ? '处理完成' : current.paused ? '已暂停' : '正在处理…';
  $('status-text').textContent = done ? `可下载教师资料，待核或失败 ${failed} 条。请查看 ZIP 中的异常明细与原文。` : current.paused ? '当前页结束后停止，点击继续即可处理剩余条目。' : '每处理完一条更新进度，单页较慢时数值会暂时保持。';
  if (done && failed) {
    const reasons = {identity_review:'姓名或页面身份还需确认',suspected_non_personal:'链接疑似不是个人主页',temporarily_unavailable:'页面正在维护或暂不可用',origin_unavailable:'原网页访问失败',provider_candidate:'补充材料还需人工核对'};
    const notes = Object.entries(reasons).filter(([key]) => current.quality_counts[key]).map(([key,label]) => `${label} ${current.quality_counts[key]} 条`);
    if (notes.length) $('status-text').textContent += ' ' + notes.join('；') + '。';
  }
  if (current.worker_error) $('status-text').textContent = '后台暂时无法继续：' + current.worker_error;
  const percent = current.total ? Math.floor(current.processed * 100 / current.total) : 0;
  $('progress').value = percent;
  $('progress-text').textContent = `已处理 ${current.processed} / ${current.total} 条`;
  $('progress-percent').textContent = percent + '%';
  $('pause').hidden = !current.queued || current.paused;
  $('resume').hidden = !current.queued || !current.paused;
  controls();
  if (done && exported !== current.id) {
    const id = current.id;
    const result = await api(`/api/batches/${id}/exports`, {method:'POST'});
    if (current?.id !== id) return;
    $('downloads').replaceChildren(...result.exports.map(e => {
      const box = node('div'); box.className = 'download';
      box.append(node('strong', `${e.school} · 教师 ${e.records} 人`));
      for (const [label, url] of [['下载教师 Excel',e.xlsx_url],['下载全文与来源 ZIP',e.zip_url]]) {
        const link = node('a',label); link.href = url; link.download = ''; box.append(link);
      }
      return box;
    }));
    exported = id;
  }
}
async function loadIssues() {
  if (!current?.preflight.issue_count) { $('issues').replaceChildren(); return; }
  const data = await api(`/api/batches/${selected}/issues?offset=${issueOffset}&limit=25`);
  $('issues').append(...data.items.map(i => {
    const reason = /BadZipFile|not a zip file|InvalidFileException|XMLSyntaxError|ParseError/i.test(i.reason) ? '文件无法读取，请确认是完整的 XLSX 文件后重新选择。' : i.reason;
    return node('p',[i.file,i.sheet,i.row ? `第 ${i.row} 行` : '',reason].filter(Boolean).join(' · '));
  }));
  $('more-issues').hidden = issueOffset + 25 >= data.total;
}
async function refresh() {
  const id = selected;
  const batch = await api('/api/batches/' + id);
  if (id !== selected) return;
  current = batch; await render();
}
function schedule() {
  clearTimeout(timer);
  if (!selected) return;
  timer = setTimeout(async () => {
    if (!busy) { try { await refresh(); } catch (e) { error(e.message); } }
    schedule();
  }, 1500);
}
$('files').addEventListener('change', () => action(async () => {
  const files = [...$('files').files];
  current = null; selected = null; exported = '';
  $('result').hidden = true; $('downloads').replaceChildren(); $('issues').replaceChildren();
  history.replaceState(null, '', location.pathname);
  try { localStorage.removeItem('mission-c-delivery-batch'); } catch {}
  $('file-names').textContent = files.length ? `已选择 ${files.length} 个文件：` + files.map(f => f.name).join('、') : '尚未选择文件';
  if (!files.length) return;
  if (files.length > 20 || files.reduce((n,f) => n + f.size,0) > 20 * 1024 * 1024) throw Error('每批最多 20 个 Excel 文件，合计不能超过 20 MiB。请减少文件后重试。');
  const form = new FormData(); for (const file of files) form.append('files',file);
  $('file-names').textContent += ' · 正在预检…';
  await choose(await api('/api/import', {method:'POST',body:form}));
  $('file-names').textContent = `已选择 ${files.length} 个文件：` + files.map(f => f.name).join('、');
}));
$('demo').addEventListener('click', () => action(async () => {
  await choose(await api('/api/demo', {method:'POST'}));
  $('files').value = ''; $('file-names').textContent = '正在查看虚构离线示例';
}));
$('start').addEventListener('click', () => action(async () => {
  await api(`/api/batches/${selected}/delivery-start`, {method:'POST'}); await refresh();
}));
for (const op of ['pause','resume']) $(op).addEventListener('click', () => action(async () => {
  await api(`/api/batches/${selected}/${op}`, {method:'POST'}); await refresh();
}));
$('more-issues').addEventListener('click', () => action(async () => { issueOffset += 25; await loadIssues(); }));
(async () => {
  try {
    await api('/api/config');
    if (!selected) { try { selected = localStorage.getItem('mission-c-delivery-batch'); } catch {} }
    if (!selected) { const batches = await api('/api/batches'); selected = batches.at(-1)?.id; }
    if (selected) { remember(selected); await refresh(); await loadIssues(); $('file-names').textContent = `已恢复 ${current.preflight.files} 个输入文件：` + current.preflight.file_names.join('、'); }
  } catch (e) { error(e.message); }
  ready = true; controls(); schedule();
})();
