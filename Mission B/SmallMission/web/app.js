'use strict';
const $ = (id) => document.getElementById(id);
let chosenFiles = [], preview = null, job = null, pollTimer = null, detailVersion = 0;
const stateNames = {running:'核验中', stopping:'正在停止', completed:'已完成', failed:'未完成', cancelled:'已停止', interrupted:'已中断'};
function node(tag, text, className) { const e = document.createElement(tag); if (text != null) e.textContent = text; if (className) e.className = className; return e; }
function error(message) { $('error').textContent = message || ''; $('error').hidden = !message; }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const data = await response.json(); if (!response.ok) throw new Error(data.error || '请求失败'); return data;
}
function show(view) {
  document.querySelectorAll('.view').forEach(e => e.hidden = e.id !== 'view-' + view);
  document.querySelectorAll('.nav').forEach(e => e.classList.toggle('active', e.dataset.view === view));
  error(''); if (view === 'history') loadHistory().catch(e => error(e.message));
}
function table(headers, rows, onClick) {
  const t = node('table'), head = node('thead'), h = node('tr'), body = node('tbody');
  headers.forEach(v => h.append(node('th', v))); head.append(h); t.append(head);
  rows.forEach((row, index) => { const tr = node('tr'); row.forEach(v => { const td = node('td'); td.append(v instanceof Node ? v : document.createTextNode(v == null ? '未判定' : String(v))); tr.append(td); });
    if (onClick) { tr.className = 'clickable'; tr.tabIndex = 0; tr.addEventListener('click', () => onClick(index)); tr.addEventListener('keydown', e => { if (e.key === 'Enter') onClick(index); }); }
    body.append(tr);
  }); t.append(body); return t;
}
function link(url, label) { if (!/^https?:\/\//i.test(url || '')) return node('span', label || url || '—'); const a = node('a', label || url); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; }
function sourceLinks(urls) { const box=node('div'); for(const url of urls){const line=node('div');line.append(link(url));box.append(line);} return box; }
function badge(text, type) { return node('span', text, 'badge ' + (type || '')); }
function verdict(r) { return !r.complete ? badge('需人工介入', 'pending') : r.verdict.includes('已自动修正') ? badge('已自动修正', 'changed') : badge('原表吻合', 'good'); }
function inputSummary(results) {
  const complete=results.filter(r=>r.complete), pending=results.length-complete.length;
  const total=key=>complete.reduce((n,r)=>n+(r.stats[key]||0),0);
  const missing=total('missing'), extra=total('extra');
  const other=total('input_duplicates')+total('protocol_changes')+total('input_placeholders');
  let title=!complete.length?'尚未判定原表是否有缺少或多出':missing||extra?`原表缺少 ${missing} 条，多出 ${extra} 条`:other?'原表无缺少或多出，但有重复或写法等差异':'原表无链接差异';
  if(pending&&complete.length)title='已核验部分：'+title;
  const detail=complete.length?`${complete.length} 个来源已对账${missing||extra||other?'，差异已自动修正':'，输入与源页面吻合'}。`:'尚未取得可靠名单。';
  return {title,detail:detail+(pending?`另有 ${pending} 个来源未能判定，需人工介入。`:''),tone:pending||missing||extra?'pending':other?'changed':'good'};
}
function invalidate() { preview = null; $('preview-panel').hidden = true; }
function refreshFiles() {
  $('file-list').replaceChildren(...chosenFiles.map((f, index) => { const li = node('li'); li.append(node('span', f.name + ' · ' + Math.ceil(f.size / 1024) + ' KB')); const b = node('button', '移除', 'text-button'); b.onclick = () => { chosenFiles.splice(index, 1); refreshFiles(); invalidate(); }; li.append(b); return li; }));
}
function addFiles(files) { for (const f of files) { if (!chosenFiles.some(x => x.name === f.name && x.size === f.size)) chosenFiles.push(f); } refreshFiles(); invalidate(); }
function listMessages(target, messages, type) { $(target).replaceChildren(); if (!messages.length) return; const box = node('div', null, 'alert ' + type); messages.slice(0, 100).forEach(m => box.append(node('p', m))); if (messages.length > 100) box.append(node('p', '还有 ' + (messages.length - 100) + ' 项，请修正后重新预览。')); $(target).append(box); }
async function encodeFile(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve({name:file.name, content:reader.result.split(',')[1]}); reader.onerror = () => reject(new Error('无法读取 ' + file.name)); reader.readAsDataURL(file); }); }
async function previewInput() {
  error(''); const button = $('preview-button'); button.disabled = true; button.textContent = '正在解析…';
  try {
    if (chosenFiles.some(f => f.size > 10*1024*1024)) throw new Error('单个文件不能超过10MB');
    if (chosenFiles.reduce((n,f) => n+f.size, 0) > 20*1024*1024) throw new Error('本次文件总量超过20MB，请分批导入');
    const inputText = $('paste').value, files = [...chosenFiles];
    const data = await api('/api/preview', {text:inputText, files:await Promise.all(files.map(encodeFile))});
    if (inputText !== $('paste').value || files.length !== chosenFiles.length || files.some((f,i) => f !== chosenFiles[i])) throw new Error('输入已改变，请重新解析预览');
    preview = data; $('preview-panel').hidden = false; $('start-button').disabled = data.errors.length > 0 || !data.task_count;
    $('preview-stats').replaceChildren(...[[data.row_count,'行数据'],[data.college_count,'个学院'],[data.source_count,'个师资页'],[data.placeholder_count,'行非URL标记']].map(([v,l]) => {const d=node('span');d.append(node('strong',v),document.createTextNode(l));return d;}));
    listMessages('preview-errors', data.errors, 'error');
    const warnings = [...data.warnings]; if (data.groups.some(g => !g.supported)) warnings.push('部分师资页尚未配置可靠的名单区域：它们会标为需人工介入，不会自动清空或改写原数据。');
    if (data.placeholder_count) warnings.push('非URL标记会保留在逐项证据中；只有来源可靠、核验完成时才从修正后的纯链接表中移出。');
    listMessages('preview-warnings', warnings, 'warning');
    $('preview-groups').replaceChildren(table(['学校','学院','师资页','输入行','页面适配'],data.groups.map(g=>[g.school,g.college,sourceLinks(g.roster_urls||[g.roster_url]),g.rows,g.supported?badge('已有名单配置','good'):badge('需核实名单区域','pending')])));
    $('preview-rows').replaceChildren(table(['学校','学院','师资URL','教师URL'],data.sample)); $('preview-panel').scrollIntoView({behavior:'smooth',block:'start'});
  } catch(e) { error(e.message); } finally { button.disabled=false; button.textContent='解析并预览 →'; }
}
async function start() {
  if(!preview) return; $('start-button').disabled=true; error('');
  try { const value = await api('/api/jobs',{preview_id:preview.id}); openJob(value); } catch(e) { error(e.message); } finally { $('start-button').disabled=false; }
}
function openJob(value) { job=value; detailVersion++; $('college-panel').hidden=true; show('job'); renderJob(); schedulePoll(); }
function schedulePoll() { clearTimeout(pollTimer); if (!job || !['running','stopping'].includes(job.status)) return; const id=job.id; pollTimer=setTimeout(async()=>{ try {const value=await api('/api/jobs/'+id); if(job?.id===id){job=value;renderJob();schedulePoll();}}catch(e){error(e.message);schedulePoll();}},1500); }
function renderJob() {
  $('job-date').textContent=new Date(job.created).toLocaleString()+' · '+job.total+' 个核验分组';
  $('job-message').textContent=job.message; $('job-progress').max=job.total||1; $('job-progress').value=job.completed;
  $('job-count').textContent=job.completed+' / '+job.total+' 个核验分组已处理'; $('job-status').textContent=stateNames[job.status]||job.status;
  $('cancel-button').hidden=!['running','stopping'].includes(job.status); $('cancel-button').disabled=job.status==='stopping';
  const finished=job.status==='completed'; $('downloads').hidden=!finished;
  $('job-hint').textContent=finished?'“无需人工”可以包含已经自动修正的输入。计数指链接，不等同于教师人数。':['running','stopping'].includes(job.status)?'逐个读取师资页。个别学校响应较慢时，需要等待浏览器重试；已完成的学院会先显示。':'这次任务没有完整交付表。输入和已取得的证据保留在 data/runs 对应任务文件夹中。';
  for(const [id,type] of [['download-summary','summary'],['download-excel','excel'],['download-corrected','corrected'],['download-all','all']]) $(id).href='/api/jobs/'+job.id+'/download/'+type;
  $('download-summary').hidden=!job.summary_available;
  const rs=job.results, total=(key)=>rs.reduce((n,r)=>n+(r.stats[key]||0),0);
  const metrics=[[rs.filter(r=>r.complete).length,'完成对账'],[rs.filter(r=>r.needs_human).length,'需要人工介入'],[total('missing'),'补入缺少链接'],[total('extra'),'移出范围外链接']];
  $('job-stats').replaceChildren(...metrics.map(([v,l])=>{const d=node('div',null,'metric');d.append(node('strong',v),node('span',l));return d;}));
  const summary=inputSummary(rs);$('input-summary').className='input-summary '+summary.tone;
  $('input-summary').replaceChildren(node('strong',summary.title),node('span',summary.detail+(job.completed<job.total?`还有 ${job.total-job.completed} 个来源尚未处理。`:'')));
  $('result-table').replaceChildren(rs.length?table(['学院 / 学校','原表是否出错','原始输入差异','官网展示 / 不同URL','处理后'],rs.map(r=>{const title=node('div');title.append(node('span',r.college,'cell-title'),node('span',r.school,'cell-small'));const quality=node('div'),a=r.input_assessment;quality.append(badge(a.title,a.tone),node('span',a.detail,'cell-small'),node('span',r.stats.input_rows+' 行 / '+r.stats.input_unique+' 个输入URL','cell-small'));const after=node('div');after.append(verdict(r),node('span',r.needs_human?'尚未修改原数据':'无需人工','cell-small'));return [title,badge(r.original_error||'未完成核验',r.original_error==='No'?'good':'pending'),quality,r.complete?r.stats.source_occurrences+' / '+r.stats.source_unique:'未判定',after];}),i=>showCollege(rs[i].id).catch(e=>error(e.message))):node('div','正在等待第一个学院的结果…','empty'));
}
async function showCollege(id) {
  const version=++detailVersion, jobId=job.id, r=await api('/api/jobs/'+jobId+'/college/'+id); if(version!==detailVersion||job.id!==jobId)return;
  $('college-title').textContent=r.school+' · '+r.college; const content=$('college-content');content.replaceChildren();
  const a=r.input_assessment,assessment=node('div',null,'input-summary '+a.tone);assessment.append(node('strong',a.title),node('span',a.detail));content.append(assessment);
  const source=node('p',null,'detail-line');source.append('师资页：',sourceLinks(r.roster_urls||[r.roster_url]));content.append(source,node('p',r.reason,'detail-line'));
  if(r.sources?.length){content.append(table(['师资页','读取结果'],r.sources.map(s=>[link(s.roster_url),s.complete?'已核验':s.issues.join('；')])));}
  if(r.complete){const s=r.stats;content.append(node('div',`官网 ${s.source_occurrences} 次链接展示 → ${s.source_unique} 个不同URL。输入重复 ${s.input_duplicates} 行，非URL标记 ${s.input_placeholders} 行；修正后 ${s.corrected} 个URL。`,'summary'));}
  const controls=node('div',null,'detail-controls'),search=node('input'),filter=node('select');search.placeholder='搜索姓名或链接';search.setAttribute('aria-label','搜索逐项差异');
  for(const [v,t] of [['changes','仅看变更 / 待处理'],['all','全部对账记录']]){const o=node('option',t);o.value=v;filter.append(o);}controls.append(search,filter);const rows=node('div',null,'table-wrap'),pages=node('div',null,'pagination');let current=0;
  const draw=()=>{const q=search.value.toLowerCase();const ds=r.diffs.filter(d=>(filter.value==='all'||d.action!=='保留')&&[d.name,d.value,d.new_url].join(' ').toLowerCase().includes(q));current=Math.min(current,Math.max(0,Math.ceil(ds.length/100)-1));rows.replaceChildren(ds.length?table(['处理','名单文字','原地址 / 标记','修正后地址','依据'],ds.slice(current*100,(current+1)*100).map(d=>[d.action,d.name||'—',link(d.value),link(d.new_url),d.reason])):node('p','没有符合条件的变更记录。','muted'));const prev=node('button','上一页','text-button'),next=node('button','下一页','text-button');prev.disabled=current===0;next.disabled=(current+1)*100>=ds.length;prev.onclick=()=>{current--;draw();};next.onclick=()=>{current++;draw();};pages.replaceChildren(prev,node('span',`共 ${ds.length} 条 · 第 ${current+1} / ${Math.max(1,Math.ceil(ds.length/100))} 页`),next);};search.oninput=()=>{current=0;draw();};filter.onchange=()=>{current=0;draw();};content.append(controls,rows,pages);draw();
  if(r.groups.length){const details=node('details');details.append(node('summary','名单区域计数 · '+r.groups.length+' 个区域（跨区域重复仍只计一个URL）'),table(['区域序号','可点击链接次数','区域内不同URL'],r.groups.map(g=>[g.index,g.occurrences,g.unique])));content.append(details);}
  if(r.notes.length){const details=node('details');details.append(node('summary','官网链接提示 · '+r.notes.length+' 条'),table(['提示','名单文字','地址','说明'],r.notes.map(n=>[n.kind,n.name,link(n.url),n.message])));content.append(details);}
  const excluded=r.anchors.filter(a=>!a.included);if(excluded.length){const d=node('details');d.append(node('summary','占位和空锚点 · '+excluded.length+' 条'),table(['文字','说明'],excluded.map(a=>[a.name||'（无文字）',a.reason])));content.append(d);}
  $('college-panel').hidden=false;$('college-panel').scrollIntoView({behavior:'smooth',block:'start'});
}
async function loadHistory(){const jobs=await api('/api/jobs');$('history-list').replaceChildren(...(jobs.length?jobs.map(j=>{const c=node('article',null,'panel history-card'),text=node('div');const summary=inputSummary(j.results);text.append(node('h2',new Date(j.created).toLocaleString()),node('p',`${j.completed} / ${j.total} 个师资来源 · ${j.results.map(r=>r.school).filter((x,i,a)=>a.indexOf(x)===i).join('、')||j.message}`,'muted'),badge(summary.title,summary.tone));c.append(text,badge(stateNames[j.status],j.status==='completed'?'good':'pending'),node('span','查看 →'));c.tabIndex=0;c.onclick=()=>openJob(j);c.onkeydown=e=>{if(e.key==='Enter')openJob(j);};return c;}):[node('article','还没有任务。新建一次核验后，结果会保存在这里。','panel empty')]));}
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>show(b.dataset.view));
$('paste').addEventListener('input',invalidate);$('files').onchange=e=>{addFiles(e.target.files);e.target.value='';};
const zone=$('dropzone');zone.ondragover=e=>{e.preventDefault();zone.classList.add('drag');};zone.ondragleave=()=>zone.classList.remove('drag');zone.ondrop=e=>{e.preventDefault();zone.classList.remove('drag');addFiles(e.dataTransfer.files);};
$('example').onclick=()=>{ $('paste').value='学校\t学院\t师资url\t教师url\n山东理工大学\t农业工程与食品科学学院\thttps://qgxy.sdut.edu.cn/szml/list.htm\thttps://qgxy.sdut.edu.cn/example-only.htm';invalidate();error('示例仅演示输入格式，故意包含一个示例地址；运行后会按官网当前名单补齐并移出它。');};
$('preview-button').onclick=previewInput;$('start-button').onclick=start;
$('cancel-button').onclick=async()=>{try{job=await api('/api/jobs/'+job.id+'/cancel',{});renderJob();schedulePoll();}catch(e){error(e.message);}};
$('close-college').onclick=()=>{$('college-panel').hidden=true;detailVersion++;};
$('quit').onclick=async()=>{try{await api('/api/shutdown',{});clearTimeout(pollTimer);document.body.replaceChildren(node('main','Mission B 已退出，可以关闭此标签页。'));}catch(e){error(e.message);}};
(async()=>{try{const token=new URLSearchParams(location.hash.slice(1)).get('token');if(token){await api('/api/session',{token});history.replaceState(null,'',location.pathname);}const config=await api('/api/config');$('version').textContent='VERSION '+config.version;$('support-note').textContent=`本版已有 ${config.supported} 个经过核实的师资页面配置。新师资URL需要核实其名单区域后才能自动判定。`;const jobs=await api('/api/jobs');const active=jobs.find(j=>['running','stopping'].includes(j.status));if(active)openJob(active);}catch(e){error(e.message);}})();
