'use strict';
const $ = id => document.getElementById(id);
const stateNames = {pending:'尚未开始',paused:'已暂停（当前页结束后生效）',completed:'处理结束',completed_with_gaps:'处理结束，有待核或失败条目',program_error:'处理出现程序异常'};
const taskNames = {pending:'未处理',running:'当前页处理中',success:'处理完成',review:'待核',failed:'读取失败',program_error:'程序异常',artifact_missing:'产物缺失或变化'};
const qualityNames = {not_read:'尚未读取',personal_candidate:'个人材料候选',provider_candidate:'提供方候选待核',origin_unavailable:'原站访问失败',temporarily_unavailable:'页面暂不可用',suspected_non_personal:'疑似非个人页',identity_review:'身份或页面待核'};
let selected = new URLSearchParams(location.search).get('batch');
let current = null, config = null, taskOffset = 0, issueOffset = 0, busy = false, poll = 0;
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(className)n.className=className;return n;}
function tell(text,error=false){$('message').textContent=text;$('message').className=error?'error':'';}
async function api(path, options={}){const headers={'X-Mission-C':'1',...options.headers};const response=await fetch(path,{...options,headers});let value;try{value=await response.json();}catch{throw Error('服务返回了无法读取的响应');}if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'请求未完成，请检查输入与选项');return value;}
async function action(fn){if(busy)return;busy=true;try{await fn();}catch(error){tell(error.message,true);}finally{busy=false;}}
function metrics(target,items){target.replaceChildren(...items.map(([number,label])=>{const n=node('div',undefined,'metric');n.append(node('strong',number),node('span',label));return n;}));}
function choose(id){selected=id;taskOffset=0;issueOffset=0;history.replaceState(null,'','?batch='+encodeURIComponent(id));$('downloads').replaceChildren();return refresh(true);}
function mode(){return document.querySelector('input[name=mode]:checked').value;}
function setOptions(){
  if(current?.mode)document.querySelector('input[name=mode][value='+current.mode+']').checked=true;
  const live=mode()==='live',locked=!!current?.queued||!!current?.processed;
  $('start').disabled=locked||!current?.total;
  $('pause').disabled=!current?.queued||current.paused;
  $('resume').disabled=!current?.queued||!current.paused;
  document.querySelectorAll('input[name=mode],#cache,#fetch-mode,#model-mode,#paid,#budget').forEach(n=>{
    n.disabled=locked||(n.id==='live'&&!config.allow_live)||(n.id==='paid'&&!config.allow_paid)||(n.id==='budget'&&!config.allow_paid);
  });
  if(live)$('cache').disabled=true;
  $('mode-help').textContent=current?.queued?
    '已保存的处理方式：'+(live?'在线访问':'严格缓存回放')+'。后台沿用开始时的材料和选项，继续不会改变运行方式。':
    current?.processed?'此批次已处理。实际读取方式与完整来源保存在下载包的逐条记录中。':
    live?'会访问表内个人 URL；师资列表仅保留为来源。在线 Fetch/模型需要额外付费许可。':
    '只读取选定缓存，不访问网站、网络媒体或密钥。缓存缺少的 URL 会保留为异常。';
}
async function refresh(details=false){
  const batches=await api('/api/batches');$('batch-list').replaceChildren(...batches.slice().reverse().map(b=>{const title=b.preflight.schools.map(s=>s.school).join('、')||'无可运行条目';const btn=node('button',title+' · '+(b.queued&&!b.paused?'处理中':stateNames[b.state]||b.state));btn.className=b.id===selected?'selected':'';btn.addEventListener('click',()=>action(()=>choose(b.id)));return btn;}));
  if(!selected){if(batches.length)await choose(batches[batches.length-1].id);return;}
  current=await api('/api/batches/'+selected);$('empty').hidden=true;$('batch').hidden=false;
  $('batch-state').textContent=current.queued&&!current.paused?'后台处理中':stateNames[current.state]||current.state;
  const p=current.preflight;metrics($('preflight'),[[p.files,'输入文件'],[p.accepted_rows,'已关联输入行'],[p.unique_tasks,'去重 URL 条目'],[p.duplicate_rows,'合并的重复行'],[p.issue_count,'格式 / 关联问题']]);
  $('schools').replaceChildren(...p.schools.map(s=>{const n=node('div',undefined,'school');n.append(node('strong',s.school),node('span',s.colleges.join('、')+' · '+s.tasks+' 条'));return n;}));
  $('issue-label').textContent='导入问题（'+p.issue_count+'）';$('progress-bar').style.width=(current.total?100*current.processed/current.total:0)+'%';$('progress-text').textContent='已处理 '+current.processed+' / '+current.total+' 条 · 当前处理中 '+current.running+' 条';
  const q=current.quality_counts,c=current.counts;metrics($('quality'),[[q.personal_candidate||0,'个人材料候选'],[(q.identity_review||0)+(q.suspected_non_personal||0)+(q.provider_candidate||0),'身份 / 页面待核'],[q.temporarily_unavailable||0,'暂不可用'],[(c.failed||0)+(c.program_error||0)+(c.artifact_missing||0),'读取 / 程序失败']]);$('worker-error').textContent=current.worker_error||'';setOptions();
  if(details||++poll%3===0)await Promise.all([loadTasks(),loadIssues()]);
}
function failureReason(task){
  let error={};try{error=JSON.parse(task.error||'{}');}catch{}
  if(error.code?.startsWith('http_'))return '原站返回 HTTP '+error.code.slice(5)+'，请核对链接与网站状态。';
  if(error.code?.startsWith('cache_'))return '缓存缺失或不匹配，本次未联网。';
  if(task.state==='program_error')return '处理程序异常，请展开详情查看。';
  if(task.state==='artifact_missing')return '已完成产物缺失或变化，需要核对原件。';
  if(error.code==='network_error')return '网络读取失败，已保留实际失败信息。';
  return task.quality.reasons?.join('；')||'';
}
async function loadTasks(){
  if(!selected)return;
  const value=await api('/api/batches/'+selected+'/tasks?offset='+taskOffset+'&limit=25');
  $('tasks').replaceChildren(...value.items.map(t=>{
    const tr=node('tr'),identity=node('td'),url=node('td',t.url),status=node('td');
    if(t.preview){
      identity.append(node('strong',t.preview.name||'姓名待核'));
      identity.append(node('span',(t.preview.title||'职称未获得')+' · '+(t.preview.email||'本人邮箱未获得'),'sub'));
    }else identity.append(node('strong','姓名未确认'));
    identity.append(node('span',t.school+' · '+[...new Set(t.relations.map(r=>r.college))].join('、'),'sub'));
    identity.append(node('span',t.sources.map(s=>s.file+' / '+s.sheet+' 第'+s.row+'行').join('；'),'sub'));
    status.append(node('strong',(taskNames[t.state]||t.state)+' · '+(qualityNames[t.quality.category]||t.quality.category)));
    status.append(node('span',t.rawtext_saved?'正文已保存（仍按质量结论准入）':'正文未保存或尚未完成','sub'));
    const reason=failureReason(t);if(reason)status.append(node('span',reason,'reason'));
    if(t.original_candidate||t.error){
      const detail=node('details');detail.append(node('summary','候选与错误详情'));
      if(t.original_candidate)detail.append(node('span','原始姓名候选（未确认）：'+(t.original_candidate.name||'未获得'),'sub'));
      if(t.error)detail.append(node('pre',t.error,'error-detail'));
      if(t.quality.reasons?.length)detail.append(node('span',t.quality.reasons.join('；'),'sub'));
      status.append(detail);
    }
    tr.append(identity,url,status);return tr;
  }));
  $('task-page').textContent=value.total?(taskOffset+1)+'–'+Math.min(taskOffset+25,value.total)+' / '+value.total:'0 条';
  $('prev-tasks').disabled=taskOffset===0;$('next-tasks').disabled=taskOffset+25>=value.total;
}
async function loadIssues(){if(!selected)return;const value=await api('/api/batches/'+selected+'/issues?offset='+issueOffset+'&limit=25');$('issues').replaceChildren(...value.items.map(i=>node('div',[i.file,i.sheet,i.row?'第'+i.row+'行':'',i.reason,i.input_url].filter(Boolean).join(' · '))));if(!value.total)$('issues').append(node('div','未发现格式或关联问题；网页质量在处理后另行判断。'));$('more-issues').hidden=issueOffset+25>=value.total;}
$('upload').addEventListener('click',()=>action(async()=>{if(!$('files').files.length)throw Error('请先选择 Excel 文件');const form=new FormData();for(const file of $('files').files)form.append('files',file);const result=await api('/api/import',{method:'POST',body:form});await choose(result.id);tell('输入已保存并完成预检，尚未开始处理。');}));
$('demo').addEventListener('click',()=>action(async()=>{const result=await api('/api/demo',{method:'POST'});await choose(result.id);tell('已载入虚构离线示例。查看预检后，点击开始处理。');}));
$('start').addEventListener('click',()=>action(async()=>{const result=await api('/api/batches/'+selected+'/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:mode(),cache_id:$('cache').value,fetch_mode:$('fetch-mode').value,model_mode:$('model-mode').value,allow_paid:$('paid').checked,paid_max_calls:Number($('budget').value)})});current=result;await refresh(true);tell('批次已交给后台。可关闭或刷新页面；请保持本地服务运行。');}));
for(const op of ['pause','resume'])$(op).addEventListener('click',()=>action(async()=>{await api('/api/batches/'+selected+'/'+op,{method:'POST'});await refresh(true);tell(op==='pause'?'已请求暂停，当前页结束后停止取新任务。':'已继续剩余任务，已完成条目不会重跑。');}));
$('export').addEventListener('click',()=>action(async()=>{const result=await api('/api/batches/'+selected+'/exports',{method:'POST'});$('downloads').replaceChildren(...result.exports.map(e=>{const box=node('div',undefined,'download');box.append(node('strong',e.school+' · 教师表 '+e.records+' 条'));for(const [label,url] of [['下载教师工作簿',e.xlsx_url],['下载全文与来源 ZIP',e.zip_url]]){const a=node('a',label);a.href=url;a.download='';box.append(a);}return box;}));tell('下载已准备。请同时查看 ZIP 内的异常明细和完整原件。');}));
$('prev-tasks').addEventListener('click',()=>action(async()=>{taskOffset=Math.max(0,taskOffset-25);await loadTasks();}));$('next-tasks').addEventListener('click',()=>action(async()=>{taskOffset+=25;await loadTasks();}));$('more-issues').addEventListener('click',()=>action(async()=>{issueOffset+=25;await loadIssues();}));document.querySelectorAll('input[name=mode]').forEach(n=>n.addEventListener('change',setOptions));
(async()=>{try{config=await api('/api/config');$('cache').replaceChildren(...config.caches.map(c=>{const option=node('option',c.label);option.value=c.id;return option;}));$('paid-note').textContent=config.allow_paid?'服务允许收费，总预算上限 '+config.paid_max_calls+' 次；仍需逐批明确选择，页面不接收密钥。':'在线收费默认关闭；当前服务未开放，页面与接口均不能启用。';$('budget').max=config.paid_max_calls;await refresh(true);}catch(error){tell(error.message,true);}setInterval(()=>{if(!busy)refresh().catch(error=>tell(error.message,true));},2000);})();
