'use strict';
const bulkSelection=new Set();
function clearBulk(){bulkSelection.clear()}
function renderBulk(){
  const items=filteredItems(),busy=['running','queued'].includes(state.cat.job.state);
  const allowed=new Set(items.map(i=>i.id));for(const id of bulkSelection)if(!allowed.has(id))bulkSelection.delete(id);
  $('#bulk-tools').innerHTML=`<label class="select-all"><input type="checkbox" id="bulk-all" ${busy?'disabled':''}>全选当前结果 (${items.length})</label><div class="bulk-count">已选 ${bulkSelection.size} 项 <button id="bulk-clear" class="smallbtn">清空</button></div><div class="bulk-actions">${state.tab==='people'?`<button id="bulk-accept" class="smallbtn" ${busy||!bulkSelection.size?'disabled':''}>批量确认此人</button>`:''}<button id="bulk-main" class="smallbtn" ${busy||!bulkSelection.size?'disabled':''}>${state.tab==='people'?'批量排除':'批量标为已处理'}</button><button id="bulk-followup" class="smallbtn" ${busy||!bulkSelection.size?'disabled':''}>留待补查</button></div>`;
  const all=$('#bulk-all');all.checked=items.length>0&&bulkSelection.size===items.length;all.indeterminate=bulkSelection.size>0&&!all.checked;
  all.onchange=()=>{for(const i of items)all.checked?bulkSelection.add(i.id):bulkSelection.delete(i.id);syncBulk()};
  $('#bulk-clear').onclick=()=>{clearBulk();syncBulk()};
  $('#bulk-main').onclick=()=>bulkReview(state.tab==='people'?'excluded':'resolved');
  $('#bulk-followup').onclick=()=>bulkReview('needs_followup');
  if($('#bulk-accept'))$('#bulk-accept').onclick=()=>bulkReview('accepted');
}
function syncBulk(){document.querySelectorAll('[data-bulk]').forEach(c=>c.checked=bulkSelection.has(c.dataset.bulk));renderBulk()}
function bulkReview(status){
  const selected=filteredItems().filter(i=>bulkSelection.has(i.id));if(!selected.length)return;
  const accepting=status==='accepted';
  if(accepting&&selected.some(i=>['duplicate','excluded'].includes(i.review.status))){toast('所选包含已排除或重复材料，请取消这些条目；恢复记录需单独核对',true);return}
  const snapshots=selected.map(i=>({id:i.id,revision:i.review.revision||0,...(accepting?{fields:JSON.parse(JSON.stringify(i.review.fields||{}))}:{})}));
  const title={accepted:'批量确认教师',excluded:'批量排除人员',resolved:'批量标为已处理',needs_followup:'批量留待补查'}[status];
  const preview=i=>{const f=i.review.fields||{};return `<div><b>${esc(f.name||i.name||issueTitle(i))}</b><small>${esc(i.profile_url||i.url||i.sources?.[0]||'学院层面')}</small>${accepting?`<p>${esc(i.review.reason||'')}</p>${[['title','职称'],['email','邮箱'],['profile_url','主页']].map(([k,label])=>`<small>${label}：${esc(f[k]||('空值 · '+(missingOptions[f.missing?.[k]]||'缺少原因，请单独补充')))}</small>`).join('')}<details><summary>简介：${f.biography?f.biography.length+' 字':'空值 · '+esc(missingOptions[f.missing?.biography]||'缺少原因')}</summary><pre class="rawtext">${esc(f.biography||'')}</pre></details>`:''}</div>`};
  const checks=accepting?`<div class="checks">${[['identity_checked','以上每条均已核对身份及同名问题'],['affiliation_checked','以上每条的官方依据均能证明学院师资归属'],['fields_checked','已核对以上每人的字段、原文及空值原因；保持预览值']].map(([k,t])=>`<label><input type="checkbox" id="bulk-${k}">${t}</label>`).join('')}</div>`:'';
  const popup=modal(`${title} · ${selected.length} 项`, `<p class="note">${accepting?'确认会采用下方逐人预览的字段；需要修改字段的请先单独编辑。':'以下条目将使用同一决定依据。'}每条记录分别保留原件、来源和修改历史；决定不会自动补采。</p><div class="bulk-preview">${selected.map(preview).join('')}</div>${checks}<label class="field">复核人<input id="bulk-actor" value="${esc(state.actor)}"></label><label class="field">决定依据<textarea id="bulk-reason" rows="3" placeholder="说明共同的核对依据"></textarea></label><label class="field">补充证据（可选）<textarea id="bulk-evidence" rows="2" placeholder="各条目已有来源会自动附上"></textarea></label><label class="select-all"><input type="checkbox" id="bulk-confirm">我已核对以上 ${selected.length} 项，确认使用此决定</label>`,async()=>{
    const actor=$('#bulk-actor').value.trim(),reason=$('#bulk-reason').value.trim();
    if(!actor||!reason)throw new Error('请填写复核人和决定依据');
    if(!$('#bulk-confirm').checked)throw new Error('请核对所选条目并勾选确认');
    const checked=accepting?Object.fromEntries(['identity_checked','affiliation_checked','fields_checked'].map(k=>[k,$('#bulk-'+k).checked])):{};
    if(accepting&&!Object.values(checked).every(Boolean))throw new Error('请完成所选人员的身份、归属和字段核对');
    await api(`/api/jobs/${jobId}/bulk-decisions`,{method:'POST',body:JSON.stringify({status,actor,reason,evidence:$('#bulk-evidence').value.trim(),items:snapshots,checks:checked})});
    state.actor=actor;localStorage.setItem('reviewActor',actor);clearBulk();state.selected=null;await refreshReview();toast(`已保存 ${selected.length} 项复核决定`);
  },{submitLabel:`保存 ${selected.length} 项决定`});
  return popup;
}

function crossCollege(p){
 if(!state.cat.related_loaded)return '<div id="cross-college"><button type="button" id="load-related" class="smallbtn">查看跨院关联</button><span class="hint">按需核对本批其他学院的同一人材料</span></div>';
 const group=(state.cat.cross_college||[]).find(g=>g.members.some(m=>m.run_id===jobId&&m.person_id===p.id));if(!group)return '';
 const conflicts=Object.entries(group.field_conflicts).map(([k,v])=>(k==='title'?'职称':'邮箱')+'待核：'+v.map(c=>c.college+' = '+c.value).join('；'));
 return `<div class="banner ${conflicts.length?'warning':''}">跨院材料已关联，批次导出合为一人：${esc(group.college)}。${conflicts.length?'<p>'+esc(conflicts.join('。'))+'。导出该字段留空，候选与依据保留在合并说明中。</p>':''}${group.members.map(m=>`<a class="source-link" href="/review/${m.run_id}?item=${m.person_id}">${esc(m.college)} · 查看原记录 →</a>`).join('')}</div>`;
}

async function loadRelated(p){
 const button=$('#load-related');button.disabled=true;button.textContent='正在核对本批跨院材料…';
 const cat=state.cat;
 try{
  const groups=await api('/api/jobs/'+jobId+'/related');
  if(state.cat!==cat)return;
  cat.cross_college=groups;cat.related_loaded=true;
  if(state.selected===p.id&&$('#cross-college'))$('#cross-college').outerHTML=crossCollege(p)||'<div class="hint">本批未找到有充分依据可关联的跨院记录。</div>';
 }catch(error){if(button.isConnected){button.disabled=false;button.textContent='重试跨院关联';button.title=error.message}}
}
