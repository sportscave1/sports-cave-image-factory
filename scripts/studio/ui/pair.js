"use strict";
(() => {
 const $=id=>document.getElementById(id), nonce=location.hash.slice(1), opener=window.opener;
 history.replaceState(null,"",location.pathname);
 let origin="", token="", approved=false, rows=[], pending=null, timer, busy=false;
 const status=s=>$("status").textContent=s;
 const send=(type,extra={})=>{if(origin&&opener)opener.postMessage({studio:1,nonce,type,...extra},origin);};
 function revoke(){send("disconnected");approved=false;token="";rows=[];pending=null;clearTimeout(timer);$("session").value="";$("handoff").hidden=true;$("link").replaceChildren();$("revoke").disabled=true;$("approve").disabled=!origin;status("Disconnected. Local source work is preserved.");}
 async function api(data){const r=await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json","X-Studio-Token":token},body:JSON.stringify(data)});const d=await r.json();if(!r.ok)throw Error(d.error||"Local request rejected");return d;}
 async function catalog(){const d=await api({action:"catalog"});rows=d.rows;send("catalog",d);}
 window.addEventListener("message",async e=>{
  const d=e.data;if(e.source!==opener||!d||d.studio!==1||d.nonce!==nonce)return;
  if(d.type==="request"&&!origin){try{const u=new URL(e.origin);if(!(u.protocol==="https:"||(u.protocol==="http:"&&["127.0.0.1","localhost"].includes(u.hostname))))return;origin=e.origin;$("requester").textContent="Requesting origin: "+origin+". Approve only if this is your signed-in Sports Cave OS.";$("approve").disabled=false;}catch{}return;}
  if(e.origin!==origin||!approved)return;
  if(d.type==="disconnect"){revoke();return;}
  if(busy)return;
  try{busy=true;if(d.type==="catalog")await catalog();
   if(d.type==="handoff"){const row=rows.find(r=>r.id===d.draft_id&&r.actionable);if(!row||!["open","edit","preview","changes"].includes(d.intent))throw Error("Draft/action is not authorised.");pending={draft_id:row.id,intent:d.intent};$("selection").textContent=`${d.intent.toUpperCase()} · ${row.name} · ${row.category} · ${row.owner} · ${row.branch} · Task ${row.task_id}`;$("link").replaceChildren();$("handoff").hidden=false;status("Check the selected draft, then confirm locally. Nothing has been edited or started.");}
  }catch(e){if(d.type==="catalog")revoke();send("error",{error:e.message});status(e.message);}finally{busy=false;}
 });
 $("approve").onclick=async()=>{if(busy||!origin)return;try{busy=true;const u=new URL($("session").value);if(u.origin!==location.origin||u.pathname!=="/"||u.search)throw Error("Use this companion's private launcher URL.");const f=u.hash.slice(1);token=f.startsWith("token=")?new URLSearchParams(f).get("token"):f;if(!/^[A-Za-z0-9_-]{40,64}$/.test(token||""))throw Error("Invalid session token.");$("session").value="";await catalog();approved=true;$("approve").disabled=true;$("revoke").disabled=false;status("Connected for 10 minutes. Catalog only; each local handoff requires confirmation.");timer=setTimeout(revoke,600000);}catch(e){token="";status(e.message);}finally{busy=false;}};
 $("revoke").onclick=revoke;
 $("cancel").onclick=()=>{pending=null;$("handoff").hidden=true;};
 $("open").onclick=async()=>{if(!approved||!pending||busy)return;try{busy=true;const result=await api({action:"handoff",...pending});const u=new URL(result.url);if(u.protocol!=="http:"||u.hostname!=="127.0.0.1")throw Error("Unsafe handoff target.");const a=document.createElement("a");a.href=result.url;a.target="_blank";a.rel="noopener noreferrer";a.textContent="Continue to the confirmed local draft";$("link").replaceChildren(a);pending=null;status("Workspace validated. Use the local link below; its private URL stays on this device.");}catch(e){status(e.message);}finally{busy=false;}};
 window.addEventListener("pagehide",()=>send("disconnected"));
 if(opener&&/^[a-f0-9]{48}$/.test(nonce))opener.postMessage({studio:1,type:"ready",nonce},"*");
 else status("Open pairing from the owner-only Developer Studio page. Direct launcher remains available.");
})();