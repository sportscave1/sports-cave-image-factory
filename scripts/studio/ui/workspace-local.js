// Local fallback shares the exact editor module with the hosted OS.
import {mount} from '/workspace.js';
const params=new URLSearchParams(location.hash.slice(1));let token=params.get('token')||'';
const intent=params.get('intent')||'edit';history.replaceState(null,'',location.pathname);
let catalog={rows:[]};const status=t=>document.getElementById('local-status').textContent=t;
async function request(path,data,retried=false){
 const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':token},body:JSON.stringify(data)}),result=await r.json();
 if(r.status===401&&!retried){let origin;try{origin=localStorage.getItem('studio-approved-origin');}catch{}
  if(origin){const renew=()=>fetch('/api/device',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Local':'1'},body:JSON.stringify({operation:'renew',origin})});const restored=navigator.locks?await navigator.locks.request('studio-device-renewal',renew):await renew();if(restored.ok){token=(await restored.json()).token;return request(path,data,true);}}}
 if(!r.ok)throw Error(result.error||'Local operation rejected');return result;
}
try{
 catalog=await request('/api/action',{action:'catalog'});
 const view=await mount(document.getElementById('workspace'),request,{loadEditor:()=>import('/editor.js'),drafts:()=>catalog.rows,
  selectDraft:async id=>{if(!await view.canLeave())return;try{const result=await request('/api/action',{action:'handoff',draft_id:id,intent:'edit'});const u=new URL(result.url);if(u.protocol!=='http:'||u.hostname!=='127.0.0.1'||u.pathname!=='/workspace'||u.search||u.username||u.password)throw Error('Invalid local handoff');location.replace(result.url);}catch(e){status(e.message);}},
  back:()=>{location.replace('/#token='+encodeURIComponent(token));}});
 status('Sports Cave OS · selected local draft · production publishing disabled');await view.intent(intent);
}catch(e){status(e.message+' · Open this draft again from the connected OS. Unsaved work is never overwritten.');}
