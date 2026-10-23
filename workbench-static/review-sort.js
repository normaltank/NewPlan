(function(root){
  'use strict';
  const collator=new Intl.Collator('zh-CN',{numeric:true,sensitivity:'base'});
  const name=p=>p.review?.fields?.name||p.name||p.issue_kind||'';
  const reason=p=>(p.review?.anomalies?.length?p.review.anomalies:p.flags?.length?p.flags:[p.review?.reason||p.issue_kind||'']).slice().sort(collator.compare).join('；');
  function sort(items,mode){
    if(mode==='original')return items.slice();
    return items.map((p,index)=>({p,index})).sort((a,b)=>{
      const byName=collator.compare(name(a.p),name(b.p));
      return (mode==='reason'?collator.compare(reason(a.p),reason(b.p))||byName:mode==='name_desc'?-byName:byName)||a.index-b.index;
    }).map(x=>x.p);
  }
  root.ReviewSort={sort,reason};
  if(typeof module!=='undefined')module.exports=root.ReviewSort;
})(globalThis);
