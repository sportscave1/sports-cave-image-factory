// Adapt existing synthetic health snapshots to the incremental queue protocol.
exports.packet=(value,route,url)=>{
 const updating=url.pathname.endsWith('/updates'),body=updating?route.request().postDataJSON():{},cursor=url.searchParams.get('cursor')||'';
 const all=value.jobs||[],available=updating?all.filter(j=>Object.hasOwn(body.known||{},j.id)):all.filter(j=>j.id>cursor),rows=updating?available:available.slice(0,50);
 const summary={...value};delete summary.jobs;
 return {summary,jobs:rows.map(j=>({...j,version:'a'.repeat(20)})),removed:updating?Object.keys(body.known||{}).filter(id=>!all.some(j=>j.id===id)):[],total_rows:value.total_rows,next_cursor:available.length>50?rows.at(-1).id:null,scanned_to:available.length>50?rows.at(-1).id:'end'};
};
