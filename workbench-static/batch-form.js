'use strict';

function newBatch(){
  const requestId=crypto.randomUUID();
  let mode='manual';
  const overlay=modal('新建采集',`
    <p class="note">每行一个学院。可填写师资列表链接，也可让系统从学院官网发现入口。</p>
    <label class="field">批次名称<input id="batch-name" value="${new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Singapore'})} 学院采集" maxlength="120"></label>
    <div class="input-tabs" role="group" aria-label="输入方式"><button type="button" class="active" data-input-mode="manual">逐行填写</button><button type="button" data-input-mode="paste">从表格粘贴</button></div>
    <section id="manual-input"><div class="tablewrap"><table class="input-table"><thead><tr><th>大学 *</th><th>学院名 *</th><th>学院链接 *</th><th>师资列表链接（选填）</th><th></th></tr></thead><tbody id="input-rows"></tbody></table></div><button id="add-input-row" type="button" class="smallbtn">＋ 添加学院</button></section>
    <section id="paste-input" hidden><label class="field">粘贴三列或四列数据<textarea id="batch-targets" rows="7" placeholder="大学&#9;学院名&#9;学院链接&#9;师资列表链接（选填）"></textarea></label><p class="note">支持从 Excel 复制粘贴、CSV、Markdown 表格或空格分隔；有无表头均可。名称含空格时请用制表符或 CSV。</p></section>
    <p class="note">多个师资链接用分号分隔；目前须与学院官网属于同一域名。每批最多 100 个学院。</p>
    <div class="batch-policy"><span>采集人：<b>自动采集</b></span><span>采集日期：<b>运行开始日期</b></span></div>
    <div class="preview-action"><button id="preview-input" type="button">检查输入</button><span class="note">检查不会启动采集或调用模型。</span></div>
    <div id="input-preview" aria-live="polite"></div>
    <p class="note">开始后加入任务队列，采集会产生 API 用量。结果可下载教师名单及四列师资链接表。</p>`,async()=>{
      const result=await check();
      if(result.errors.length)throw Error('请先修正输入中标出的错误');
      const r=await api('/api/batches',{method:'POST',body:JSON.stringify({name:$('#batch-name').value.trim(),targets:result.targets,request_id:requestId})});
      state.batch=r.id;
      // A successful create is final even if the subsequent dashboard refresh fails.
      try{state.overview=await api('/api/overview');dashboard()}catch(e){toast('批次已创建，稍后将自动同步',true)}
      toast(result.count+' 个学院任务已加入采集队列');
    },{className:'batch-modal',submitLabel:'开始采集'});

  function dirty(){$('#input-preview').innerHTML=''}
  function addRow(values={}){
    const index=$$('#input-rows tr').length+1;
    if(index>100){toast('每批最多 100 个学院',true);return}
    const row=document.createElement('tr');
    row.innerHTML=['university','college','url','entries'].map((key,i)=>`<td><input data-key="${key}" aria-label="第 ${index} 行${['大学','学院名','学院链接','师资列表链接'][i]}" placeholder="${['例如：南通大学','例如：医学院','https://…','选填 https://…'][i]}" value="${esc(values[key]||'')}"></td>`).join('')+'<td><button type="button" class="smallbtn remove-row" aria-label="删除本行">删除</button></td>';
    row.querySelector('.remove-row').onclick=()=>{row.remove();dirty();if(!$$('#input-rows tr').length)addRow()};
    row.oninput=dirty;$('#input-rows').append(row);dirty();
  }
  function payload(){
    if(mode==='paste')return {text:$('#batch-targets').value};
    return {targets:$$('#input-rows tr').map(row=>{
      const value={};row.querySelectorAll('[data-key]').forEach(el=>value[el.dataset.key]=el.value.trim());
      value.entries=value.entries.split(/[;；\n]/).map(v=>v.trim()).filter(Boolean);return value;
    })};
  }
  async function check(){
    const button=$('#preview-input');button.disabled=true;
    try{
      const result=await api('/api/batches/preview',{method:'POST',body:JSON.stringify(payload())});
      $('#input-preview').innerHTML=(result.errors.length?`<div class="banner warning"><b>输入有 ${result.errors.length} 处问题</b><ul>${result.errors.map(e=>`<li>${e.row?'第 '+e.row+' 行：':''}${esc(e.message)}</li>`).join('')}</ul></div>`:`<div class="banner"><b>${result.count} 个学院可以开始采集</b> · ${result.without_entries} 个需要发现师资入口${result.duplicates_merged?' · 已合并 '+result.duplicates_merged+' 行重复输入':''}</div>`)+(result.targets.length?`<div class="tablewrap preview-table"><table><thead><tr><th>大学</th><th>学院名</th><th>学院链接</th><th>师资列表链接</th></tr></thead><tbody>${result.targets.map(t=>`<tr><td>${esc(t.university)}</td><td>${esc(t.college)}</td><td>${link(t.url,'学院官网')}</td><td>${t.entries.length?t.entries.map(u=>link(u)).join(''):'自动发现'}</td></tr>`).join('')}</tbody></table></div>`:'');
      return result;
    }finally{button.disabled=false}
  }
  overlay.querySelectorAll('[data-input-mode]').forEach(button=>button.onclick=()=>{
    mode=button.dataset.inputMode;
    overlay.querySelectorAll('[data-input-mode]').forEach(b=>b.classList.toggle('active',b===button));
    $('#manual-input').hidden=mode!=='manual';$('#paste-input').hidden=mode!=='paste';dirty();
  });
  $('#add-input-row').onclick=()=>addRow();
  $('#batch-targets').oninput=dirty;
  $('#preview-input').onclick=()=>check().catch(e=>toast(e.message,true));
  addRow();
}
function $$(selector){return [...document.querySelectorAll(selector)]}
