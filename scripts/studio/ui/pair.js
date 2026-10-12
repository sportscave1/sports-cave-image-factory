"use strict";
(() => {
 const $=id=>document.getElementById(id), nonce=location.hash.slice(1), opener=window.opener;
 const setupTicket=/^\/pair\/setup\/([A-Za-z0-9_-]{43})$/.exec(location.pathname)?.[1]||"";
 history.replaceState(null,"",setupTicket?"/pair":location.pathname);
 const bootstrap=nonce.startsWith("bootstrap=")?nonce.slice(10):"";
 let trusted=false, workspaceGrant=null, workspaceQueue=Promise.resolve(), applicationPlan=null;
 const applicationDialog=$('application-confirm');
 let origin="", token="", approved=false, rows=[], pending=null, timer, busy=false, releasePending=null, releaseCatalog=null;
 const status=s=>$("status").textContent=s;
 function exactOrigin(value){let u;try{u=new URL(value);}catch{throw Error("Enter the exact HTTPS OS origin or localhost origin, without a path, query or fragment.");}if(u.origin!==value||u.username||u.password||!(u.protocol==="https:"||(u.protocol==="http:"&&["127.0.0.1","localhost"].includes(u.hostname))))throw Error("Enter the exact HTTPS OS origin or localhost origin, without a path, query or fragment.");return value;}
 const send=(type,extra={})=>{if(origin&&opener)opener.postMessage({studio:1,nonce,type,...extra},origin);};
 function revoke(){if(workspaceGrant){api({action:"workspace-revoke",capability:workspaceGrant.capability}).catch(()=>{});workspaceGrant=null;}send("disconnected");approved=false;token="";rows=[];pending=null;releasePending=null;releaseCatalog=null;$("release-confirm").hidden=true;$("release-confirmation").value="";clearTimeout(timer);$("session").value="";$("handoff").hidden=true;$("link").replaceChildren();$("revoke").disabled=true;$("approve").disabled=!origin;status("Disconnected. Local source work is preserved.");}
 async function api(data){const r=await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json","X-Studio-Token":token},body:JSON.stringify(data)});const d=await r.json();if(!r.ok){if(r.status===401&&trusted){const renewed=await device("renew");token=renewed.token;renewal();const retry=await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json","X-Studio-Token":token},body:JSON.stringify(data)});const result=await retry.json();if(!retry.ok)throw Error(result.error||"Local request rejected");return result;}throw Error(d.error||"Local request rejected");}return d;}
 async function catalog(){const d=await api({action:"catalog"});rows=d.rows;send("catalog",{...d,trusted});}
 window.addEventListener("message",async e=>{
  const d=e.data;if(e.source!==opener||!d||d.studio!==1||d.nonce!==nonce)return;
  if(d.type==="request"&&!origin){try{origin=exactOrigin(e.origin);$("trusted-origin").value=origin;$("trusted-origin").disabled=true;$("requester").textContent="Requesting origin: "+origin+". Approve only if this is your signed-in Sports Cave OS.";$("approve").disabled=false;await resume();}catch{}return;}
  if(e.origin!==origin||!approved)return;
  if(d.type==="disconnect"){revoke();return;}
  if(d.type==="ping"){try{const r=await fetch("/api/ping",{headers:{"X-Studio-Token":token}});if(!r.ok){if(trusted)await renewSession();else revoke();}else send("pong");}catch{send("reconnecting");if(trusted){clearTimeout(timer);timer=setTimeout(renewSession,30000);}else revoke();}return;}
  if(d.type==="workspace-close"){
   if(workspaceGrant){await api({action:"workspace-revoke",capability:workspaceGrant.capability});workspaceGrant=null;}return;
  }
  if(d.type==="workspace-call"){
   if(!/^[a-f0-9]{24}$/.test(d.request_id||""))return;
   const grant=workspaceGrant;
   workspaceQueue=workspaceQueue.then(async()=>{
    try{
     if(!grant||workspaceGrant!==grant||d.draft_id!==grant.draft_id)throw Error("Confirm this selected draft locally before editing.");
     const result=await api({action:"workspace-request",capability:grant.capability,command:d.command});
     send("workspace-result",{request_id:d.request_id,draft_id:grant.draft_id,result});
    }catch(e){send("workspace-result",{request_id:d.request_id,draft_id:d.draft_id,error:e.message});}
   });return;
  }
  if(busy)return;
  try{busy=true;
   if(d.type==="application-request"){
    const q=d.request||{};applicationPlan=await api({action:'application-prepare',operation:q.operation,draft_id:q.draft_id,name:q.name});
    $('application-detail').textContent=JSON.stringify(applicationPlan.detail,null,2)+'\n'+applicationPlan.operation.toUpperCase()+(applicationPlan.name?' · '+applicationPlan.name:'')+'\nArchiving preserves all source and recovery records. No production changes.';
    $('application-confirmation').value='';applicationDialog.hidden=false;status('Review this application draft operation locally.');
   }
   if(d.type==='technical-catalog')send('technical-catalog',{result:await api({action:'technical-catalog'})});
   if(d.type==="workspace-begin"){
    const row=rows.find(r=>r.id===d.draft_id&&r.actionable);if(!row)throw Error("Draft is locked to another owner.");
    pending={draft_id:row.id,intent:"edit",kind:"workspace"};
    $("selection").textContent=`Allow this OS window to edit the explicit frontend files and mapped properties of ${row.name}? Owner ${row.owner}; branch ${row.branch}; task ${row.task_id}. Preview stays isolated; publishing is disabled. Permission expires after 15 minutes of editor inactivity or Disconnect.`;
    $("open").textContent="Allow editing this selected draft";$("handoff").hidden=false;$("link").replaceChildren();status("Review the exact draft, then grant its editor session locally.");
   }
   if(d.type==="catalog")await catalog();
   if(d.type==="release-catalog"){releaseCatalog=await api({action:"release-catalog"});send("release-catalog",{result:releaseCatalog});}
   if(d.type==="release-frame"){
    if(!releaseCatalog?.records.some(r=>r.id===d.id))throw Error("Unknown selected candidate.");
    const ev=d.event;if(!ev||!["frame","size"].includes(ev.action)||(ev.action==="size"&&!["desktop","mobile"].includes(ev.mode)))throw Error("Preview event rejected.");
    send("release-result",{result:await api({action:"release-preview",operation:"event",id:d.id,event:ev})});
   }
   if(d.type==="release-request"){
    const q=d.request;if(!q||!["prepare","test","review","approve","simulate","recover","preview-start","preview-stop"].includes(q.operation)||!releaseCatalog)throw Error("Refresh the RELEASE catalog first.");
    if(q.operation==="prepare"){
     if(!Array.isArray(q.task_ids)||!q.task_ids.length||q.task_ids.some(id=>!releaseCatalog.options.some(t=>t.id===id&&t.eligible)))throw Error("Select approved revisions only.");
     releasePending={operation:q.operation,task_ids:q.task_ids};
     $("release-detail").textContent="PREPARE on "+releaseCatalog.base.commit+"\n"+releaseCatalog.options.filter(t=>q.task_ids.includes(t.id)).map(t=>t.name+"  -  "+t.commit).join("\n");
    }else{
     const r=releaseCatalog.records.find(r=>r.id===q.id);if(!r||r.version!==q.version)throw Error("Stale candidate. Refresh first.");
     releasePending={operation:q.operation,id:r.id,version:r.version};
     $("release-detail").textContent=q.operation.toUpperCase()+"  -  MOCK / LOCAL ONLY\n"+JSON.stringify({candidate:r.id,commit:r.candidate_commit,fingerprint:r.fingerprint,checks:r.checks,risks:r.risks,previous:r.previous_verified_simulation?.github?.revision},null,2);
    }
    $("release-confirmation").value="";$("release-confirm").hidden=false;status("Confirm locally. Production publishing is unavailable.");
   }
   if(d.type==="handoff"){const row=rows.find(r=>r.id===d.draft_id&&r.actionable);if(!row||!["open","edit","preview","changes"].includes(d.intent))throw Error("Draft/action is not authorised.");pending={draft_id:row.id,intent:d.intent};$("open").textContent="Open selected local workspace";$("selection").textContent=`${d.intent.toUpperCase()}  -  ${row.name}  -  ${row.category}  -  ${row.owner}  -  ${row.branch}  -  Task ${row.task_id}`;$("link").replaceChildren();$("handoff").hidden=false;status("Check the selected draft, then confirm locally. Nothing has been edited or started.");}
  }catch(e){if(d.type==="catalog")revoke();send("error",{error:e.message});status(e.message);}finally{busy=false;}
 });
 async function deviceRequest(operation){const r=await fetch("/api/device",{method:"POST",headers:{"Content-Type":"application/json","X-Studio-Local":"1","X-Studio-Token":token},body:JSON.stringify({operation,origin,...(setupTicket&&operation==="trust"?{setup_ticket:setupTicket}:{})})});const d=await r.json();if(!r.ok){const e=Error(d.error||"Device trust unavailable");e.status=r.status;throw e;}return d;}
 async function device(operation){const run=()=>deviceRequest(operation);return globalThis.navigator?.locks? navigator.locks.request("studio-device-renewal",run):run();}
 async function renewSession(){try{const d=await device("renew");token=d.token;approved=true;await catalog();status("Connected  -  trusted computer  -  session renewed");renewal();}catch(e){if(e.status){revoke();status(e.message);}else{send("reconnecting");status("Reconnecting to this computer -  source work is preserved.");clearTimeout(timer);timer=setTimeout(renewSession,30000);}}}
 function renewal(){clearTimeout(timer);timer=setTimeout(renewSession,240000);}
 async function resume(){try{const d=await device("renew");token=d.token;trusted=true;approved=true;$("approve").disabled=true;$("session").disabled=true;$("trust").checked=true;$("trusted-origin").value=origin;try{localStorage.setItem("studio-approved-origin",origin);}catch{}$("revoke").disabled=false;$("forget").disabled=false;$("stop-companion").disabled=false;await catalog();renewal();status("Connected  -  trusted computer. Sensitive actions still require local confirmation.");}catch(e){
    if(!e.status){send("reconnecting");status("Local companion is temporarily unavailable. Reconnecting; saved trust and source are preserved.");clearTimeout(timer);timer=setTimeout(resume,30000);return;}
    send("disconnected");$("approve").disabled=false;$("approve").textContent="Check saved trust / Connect";status("No usable saved trust. Run Companion.ps1 Open in this browser once, approve Trust This Computer for "+origin+", then return here and click Check saved trust / Connect. Leave the private URL blank; no copying is required. "+e.message);}}
 $("approve").onclick=async()=>{if(busy)return;try{busy=true;
  if(setupTicket){origin=exactOrigin($("trusted-origin").value.trim());token="";}
  else if(bootstrap){origin=exactOrigin($("trusted-origin").value.trim());if(origin===location.origin)throw Error("Enter the Sports Cave OS website origin, not this localhost companion address.");token=bootstrap;}
  else {if(!origin)return;if(!$("session").value.trim()){await resume();return;}const u=new URL($("session").value.trim());if(u.origin!==location.origin||u.pathname!=="/"||u.search)throw Error("Use this companion's private launcher URL.");const f=u.hash.slice(1);token=f.startsWith("token=")?new URLSearchParams(f).get("token"):f;}
  if(!setupTicket&&!/^[A-Za-z0-9_-]{40,64}$/.test(token||""))throw Error("Invalid session token.");$("session").value="";
  if($("trust").checked){const d=await device("trust");token=d.token;if(setupTicket){const verified=await device("renew");token=verified.token;}trusted=true;try{localStorage.setItem("studio-approved-origin",origin);}catch{}renewal();$("forget").disabled=false;$("stop-companion").disabled=false;}
  await catalog();approved=true;if(trusted)trustChannel?.postMessage({type:"trust-ready",origin});$("approve").disabled=true;$("revoke").disabled=false;status(trusted?"Computer trusted. Return to Sports Cave OS and Connect; no private URL is needed.":"Connected for 10 minutes. Select Trust This Computer in the local launcher for renewal.");if(!trusted)timer=setTimeout(revoke,600000);
 }catch(e){token="";status(e.message);}finally{busy=false;}};
 $("forget").onclick=async()=>{if(!window.confirm("Revoke this computer's saved trust and active trusted sessions? Unsaved source stays open."))return;try{await device("revoke");revoke();status("Computer revoked. Fresh local approval required.");}catch(e){status(e.message);}};
 $("stop-companion").onclick=async()=>{if(!window.confirm("Stop this companion and its previews? Save editor work first. It will stay stopped until you start it or sign in again."))return;try{await device("stop");revoke();status("Companion stopped.");}catch(e){status(e.message);}};
 $("release-cancel").onclick=()=>{releasePending=null;$("release-confirm").hidden=true;};
 $("release-run").onclick=async()=>{
  if(!approved||!releasePending||busy)return;
  const q=releasePending;releasePending=null;busy=true;$("release-confirm").hidden=true;status("Running local operation - ");
  try{let result;if(q.operation.startsWith("preview-"))result=await api({action:"release-preview",operation:q.operation==="preview-start"?"start":"stop",id:q.id});
   else result=await api({action:"release-operation",...q,confirmation:$("release-confirmation").value,scenario:$("release-scenario").value});
   send("release-result",{result});status("Local operation complete. No production changes.");
  }catch(e){send("error",{error:e.message});status(e.message);}finally{busy=false;$("release-confirmation").value="";}
 };
 $("revoke").onclick=revoke;
 $('application-cancel').onclick=()=>{applicationPlan=null;applicationDialog.hidden=true;};
 $('application-run').onclick=async()=>{
  if(!approved||!applicationPlan||busy)return;
  const plan=applicationPlan;applicationPlan=null;busy=true;
  try{const result=await api({action:'application-run',ticket:plan.ticket,confirmation:$('application-confirmation').value});await catalog();send('application-result',{result});applicationDialog.hidden=true;status('Application draft updated locally. Worktree identity and production are preserved.');}
  catch(e){send('error',{error:e.message});status(e.message);}finally{busy=false;}
 };
 $("cancel").onclick=()=>{pending=null;$("handoff").hidden=true;};
 $("open").onclick=async()=>{
  if(!approved||!pending||busy)return;
  if(pending.kind==="workspace"){
   busy=true;try{
    if(workspaceGrant)await api({action:"workspace-revoke",capability:workspaceGrant.capability});
    workspaceGrant=await api({action:"workspace-grant",draft_id:pending.draft_id});
    send("workspace-approved",{draft_id:workspaceGrant.draft_id});pending=null;$("handoff").hidden=true;
    status("Selected draft editor enabled in Sports Cave OS. Keep this bridge open. Disconnect revokes the editing session.");
   }catch(e){status(e.message);}finally{busy=false;}return;
  }
  // Reserve the window during the explicit local click, before asynchronous validation.
  const selection={...pending};let workspace=null;
  try{
   workspace=window.open("about:blank","_blank");if(workspace)workspace.opener=null;
   busy=true;const result=await api({action:"handoff",...selection}),u=new URL(result.url);
   if(u.protocol!=="http:"||u.hostname!=="127.0.0.1"||!u.port||u.username||u.password||u.pathname!=="/workspace"||u.search||result.draft_id!==selection.draft_id)throw Error("Unsafe handoff target.");
   const a=document.createElement("a");a.href=result.url;a.target="_blank";a.rel="noopener noreferrer";a.textContent="Open the confirmed local draft";$("link").replaceChildren(a);
   if(workspace)workspace.location.replace(result.url);
   pending=null;$("handoff").hidden=!!workspace;
   send("workspace-opened",{draft_id:result.draft_id,intent:selection.intent});
   status(workspace?"Selected draft opened on this computer. Keep this connection window open; edit and preview in the draft workspace.":"Browser blocked the draft window. Use the confirmed local link below; no new pairing is required.");
  }catch(e){workspace?.close();status(e.message);}finally{busy=false;}
 };
 let trustChannel=null;
 if(typeof BroadcastChannel!=="undefined"){
  trustChannel=new BroadcastChannel("studio-trust-ready");
  trustChannel.onmessage=e=>{if(e.data?.type==="trust-ready"&&e.data.origin===origin&&opener&&!approved&&!busy)resume();};
 }
 window.addEventListener("pagehide",()=>{trustChannel?.close();send("disconnected");});
 if(setupTicket){
  origin=exactOrigin($("trusted-origin").value.trim());$("trusted-origin").disabled=true;
  $("session-label").hidden=true;$("session").disabled=true;$("trust").checked=true;$("trust").disabled=true;
  $("approve").disabled=false;$("approve").textContent="Trust this Edge profile and connect";
  $("requester").textContent="Authenticated launcher session for: "+origin;
  status("Ready for your approval. This one-use setup expires in 5 minutes. No saved cookie or private URL is required.");
 }
 else if(opener&&/^[a-f0-9]{48}$/.test(nonce))opener.postMessage({studio:1,type:"ready",nonce},"*");
 else if(bootstrap){$("approve").disabled=false;$("session").disabled=true;$("session-label").hidden=true;$("trust").checked=true;status("Check the exact OS origin, then approve Trust This Computer. No private URL copying is required.");try{origin=exactOrigin($("trusted-origin").value.trim());if(origin!==location.origin)resume();}catch{}}
 else {let saved="";try{saved=localStorage.getItem("studio-approved-origin")||"";}catch{}if(saved&&saved!==location.origin){try{origin=exactOrigin(saved);$("trusted-origin").value=origin;$("trusted-origin").disabled=true;resume();}catch{status("Open pairing from the owner-only Developer Studio page.");}}else status("Open Developer Studio and click Connect once. This restored local page will not open more windows.");}
})();
