"use strict";
(() => {
 const $=id=>document.getElementById(id); let popup=null, origin="", nonce="", connected=false, rows=[], expiry, releaseData=null, activeCandidate=null, lastSeen=0, trusted=false, selectedDraft="", heartbeatTimer;
 let workspace=null,workspaceId=null,workspaceIntent="edit",workspaceModule=null,workspaceSupported=false,workspaceApproved=false,pendingDraft="",restoreAttempted=false,workspaceLoading=null,applicationSupported=false;const workspaceRequests=new Map();
 const message=s=>$("message").textContent=s;
 const selectionKey=()=>"studio-v6-last-draft:"+origin;
 function rememberDraft(id){try{localStorage.setItem(selectionKey(),id);}catch{}}
 function rememberedDraft(){try{return localStorage.getItem(selectionKey())||"";}catch{return "";}}
 function send(type,extra={}){if(popup&&!popup.closed)popup.postMessage({studio:1,type,nonce,...extra},origin);else offline("Local window closed. Reconnect when needed.");}
 function offline(text){for(const r of workspaceRequests.values()){clearTimeout(r.timer);r.reject(Error("Local companion disconnected; unsaved editor text is preserved."));}workspaceRequests.clear();clearTimeout(heartbeatTimer);releaseData=null;activeCandidate=null;$("release-refresh").disabled=$("prepare").disabled=true;for(const id of ["release-options","release-candidates","release-checks","release-history"])$(id).replaceChildren();$("release-image").hidden=true;$("release-preview-controls").hidden=true;connected=false;workspaceApproved=false;pendingDraft="";restoreAttempted=false;clearTimeout(expiry);rows=[];$("connection").textContent="Local device offline";$("connect").hidden=false;$("refresh").disabled=$("disconnect").disabled=$("resume-editor").disabled=true;$("evidence").replaceChildren();syncSelection();workspace?.refreshCatalog();message(text);}
 function tab(id){const editing=["editor","drafts"].includes(id);document.body?.classList.toggle("editing",editing);$("workspace-v6").hidden=!editing;for(const n of ["live","preview","tests","releases","history"])$(n).hidden=n!==id;document.querySelectorAll("[data-tab]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.tab===id)));$("studio-menu").open=false;if(id==="drafts")workspace?.selectTab("drafts");}
 document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>tab(b.dataset.tab));
 function line(parent,tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;parent.append(e);return e;}
 function syncSelection(){
  const draft=rows.find(d=>d.id===selectedDraft),label=draft?`${draft.name} · ${draft.category} · ${draft.owner}`:"Select a registered draft";
  $("preview-selected").textContent=label;$("tests-selected").textContent=draft?label:"All registered drafts";
  $("selected-preview").disabled=$("resume-editor").disabled=!connected||!draft?.actionable;
 }
 async function openSelected(intent,renew=false){
  const draft=rows.find(d=>d.id===selectedDraft);if(!connected||!draft?.actionable)return;
  tab("editor");
  if(!workspaceSupported){message("This companion needs the V6 workspace update. Your drafts and ownership are preserved.");return;}
  if(workspace&&workspaceId&&workspaceId!==draft.id&&!await workspace.canLeave()){selectedDraft=workspaceId;syncSelection();draw();return;}
  workspaceIntent=intent;
  if(!renew&&workspaceApproved&&workspaceId===draft.id){await workspace.intent(intent);return;}
  workspaceApproved=false;workspace?.refreshCatalog();pendingDraft=draft.id;send("workspace-begin",{draft_id:draft.id});message("Confirm this draft in the secure local window; its Editor opens here.");popup.focus();
 }
 $("selected-preview").onclick=()=>openSelected("preview");
 function draw(){ $("evidence").replaceChildren();
  for(const d of rows){if(selectedDraft&&d.id!==selectedDraft)continue;
   const e=line($("evidence"),"article","","card");line(e,"h3",d.name);line(e,"p",`Recorded review: ${d.review_status} · ${d.status==="Approved"||d.status==="Integrated"?"Approved task":"Unfinished / awaiting approval"}`);line(e,"p",d.test?.evidence||"No test evidence recorded.");line(e,"p",`Tested snapshot: ${d.test?.snapshot?.files_hash||"unavailable"}`);line(e,"p","Use Check approved revisions in Releases to revalidate immutable task eligibility. Production publishing disabled.");
  }workspace?.refreshCatalog();}
 async function moduleFrom(source){const url=URL.createObjectURL(new Blob([source],{type:"text/javascript"}));try{return await import(url);}finally{URL.revokeObjectURL(url);}}
 async function mountWorkspace(draftId){
  const bundle=window.STUDIO_V6_BUNDLE;
  if(!workspaceModule){const css=document.createElement("style");css.dataset.studioEditorCss="true";css.textContent=bundle["editor.css"]+bundle["workspace.css"];document.head.append(css);workspaceModule=await moduleFrom(bundle["workspace.js"]);}
  const transport=(_path,command)=>new Promise((resolve,reject)=>{
   if(!connected||!workspaceApproved||workspaceId!==draftId||!rows.some(r=>r.id===draftId&&r.actionable))return reject(Error("Local draft permission unavailable. Reconnect and confirm this draft; unsaved work is preserved."));
   const request_id=Array.from(crypto.getRandomValues(new Uint8Array(12)),x=>x.toString(16).padStart(2,"0")).join("");
   const timer=setTimeout(()=>{workspaceRequests.delete(request_id);reject(Error("Local operation timed out. Reopen and compare before retrying a save."));},120000);
   workspaceRequests.set(request_id,{resolve,reject,timer,draftId});send("workspace-call",{request_id,draft_id:draftId,command});
  });
  workspace=await workspaceModule.mount($("workspace-v6"),transport,{empty:!draftId,connected:()=>connected&&(!draftId||workspaceApproved),selectedDraft:()=>selectedDraft,loadEditor:()=>moduleFrom(bundle["editor.js"]),drafts:()=>rows,storageKey:()=>origin+':'+draftId,applications:()=>applicationSupported,
   manage:async(operation,name)=>{if(workspace&&!await workspace.canLeave())return;send('application-request',{request:{operation,name,draft_id:selectedDraft}});message('Review this draft operation in the secure local window.');popup.focus();},
   selectDraft:async id=>{if(!rows.some(r=>r.id===id&&r.actionable))return;selectedDraft=id;syncSelection();draw();await openSelected("edit");}});
 }
 async function showWorkspace(draftId){
  if(!connected||!workspaceSupported||draftId!==selectedDraft||draftId!==pendingDraft||!rows.some(r=>r.id===draftId&&r.actionable))return;
  if(workspaceLoading)await workspaceLoading;
  if(!connected||pendingDraft!==draftId||selectedDraft!==draftId)return;
  workspaceApproved=true;pendingDraft="";tab("editor");
  if(workspace&&workspaceId===draftId){await workspace.resume();workspace.refreshCatalog();}
  else{workspace?.dispose();workspace=null;workspaceId=draftId;await mountWorkspace(draftId);}
  rememberDraft(draftId);await workspace.intent(workspaceIntent);message("Local editor connected · changes stay in the selected draft");
 }
 function releaseRequest(operation,record,extra={}){
  if(!connected)return message("Connect the assigned RELEASE companion first.");
  send("release-request",{request:{operation,...(record?{id:record.id,version:record.version}:{}),...extra}});
  message("Review and confirm this release operation in the local approval window.");popup.focus();
 }
 function showRelease(){
  for(const id of ["release-options","release-candidates","release-checks","release-history"])$(id).replaceChildren();
  if(!releaseData)return;
  if(activeCandidate)activeCandidate=releaseData.records.find(r=>r.id===activeCandidate.id)||null;
  let live=document.getElementById("live-services");if(!live){live=document.createElement("pre");live.id="live-services";$("live").append(live);}live.textContent=JSON.stringify(releaseData.live,null,2);
  $("release-base").textContent="Approved development base · "+releaseData.base.commit+" · not a verified Live revision";
  const excluded=line($("release-options"),"details","");line(excluded,"summary",releaseData.options.filter(d=>!d.eligible).length+" unfinished or unapproved tasks excluded");
  for(const d of releaseData.options){const card=line(d.eligible?$("release-options"):excluded,"article","","card"),label=line(card,"label","");const cb=document.createElement("input");cb.type="checkbox";cb.value=d.id;cb.disabled=!d.eligible;label.append(cb);line(label,"span",d.name+" · "+d.category+" · "+d.owner);line(card,"p",d.eligible?d.commit:d.reason);}
  $("prepare").disabled=false;
  for(const r of releaseData.records){const c=line($("release-candidates"),"article","","card");line(c,"h3",r.status);line(c,"p","Candidate "+r.id);line(c,"p","Exact SHA: "+(r.candidate_commit||"Pending separately authorised commit"));line(c,"p","Selected: "+r.selections.map(s=>s.name).join(", "));line(c,"p","Risks: "+(r.risks.join(", ")||"No migration/worker file trigger detected; review still required"));if(r.failure)line(c,"p",r.failure);
   const details=line(c,"details",""),sum=line(details,"summary","Review changes and identity");line(details,"pre",JSON.stringify({base:r.base_commit,fingerprint:r.fingerprint,changed_files:r.changed_files,already_in_base:r.already_in_base},null,2));
   for(const [op,label] of [["preview-start","Preview"],["test","Run focused checks"],["review","Review candidate"],["approve","Approve simulation"],["simulate","Simulate Publish"],["recover","Simulate recovery"]]){const b=line(c,"button",label);b.onclick=()=>{activeCandidate=r;if(op==="preview-start")tab("preview");releaseRequest(op,r);};if(["approve","simulate"].includes(op)&&!r.candidate_commit)b.disabled=true;}
   const test=line($("release-checks"),"article","","card");line(test,"h3",r.id);line(test,"pre",JSON.stringify(r.checks,null,2));
   const history=line($("release-history"),"article","","card");line(history,"h3","SIMULATION · "+r.id);line(history,"pre",JSON.stringify(r.history,null,2));
  }
 }
 $("release-refresh").onclick=()=>send("release-catalog");
 $("prepare").onclick=()=>releaseRequest("prepare",null,{task_ids:[...document.querySelectorAll("#release-options input:checked")].map(e=>e.value)});
 for(const [id,event] of [["release-desktop",{action:"size",mode:"desktop"}],["release-mobile",{action:"size",mode:"mobile"}],["release-frame",{action:"frame"}]])$(id).onclick=()=>{if(activeCandidate)send("release-frame",{id:activeCandidate.id,event});};
 $("release-stop").onclick=()=>{if(activeCandidate)releaseRequest("preview-stop",activeCandidate);};
 $("connect").onclick=()=>{try{const u=new URL($("origin").value);if(u.protocol!=="http:"||u.hostname!=="127.0.0.1"||!u.port||u.username||u.password||u.search||u.hash||u.pathname!=="/")throw Error("Enter only http://127.0.0.1:port. Never paste a private token here.");if(connected)send("disconnect");offline("Approve this connection in the localhost window.");origin=u.origin;try{localStorage.setItem("studio-companion-origin",origin);}catch{}$("connection").textContent="Reconnecting · awaiting localhost";nonce=Array.from(crypto.getRandomValues(new Uint8Array(24)),x=>x.toString(16).padStart(2,"0")).join("");popup=window.open(origin+"/pair#"+nonce,"_blank");clearTimeout(expiry);expiry=setTimeout(()=>{if(!connected)offline("Local device offline. Check that the Windows companion is running, then reconnect.");},15000);if(!popup)throw Error("Popup blocked. Allow this popup or use the private local launcher directly.");}catch(e){message(e.message);}};
 $("resume-editor").onclick=()=>openSelected("edit",true);
 $("disconnect").onclick=()=>{send("disconnect");offline("Disconnected. Local editor work is preserved.");};
 $("refresh").onclick=()=>send("catalog");
 window.addEventListener("message",e=>{const d=e.data;if(e.source!==popup||e.origin!==origin||!d||d.studio!==1||d.nonce!==nonce)return;
  lastSeen=Date.now();
  if(d.type==="ready")send("request");
  if(d.type==="reconnecting")$("connection").textContent="Reconnecting";
  if(d.type==="pong")$("connection").textContent="Local device connected";
  if(d.type==="catalog"){
   if(!Array.isArray(d.rows)||!Array.isArray(d.categories))return;
   workspaceSupported=d.workspace_v6===true;applicationSupported=d.application_drafts===true;connected=true;heartbeat();trusted=d.trusted===true;lastSeen=Date.now();rows=applicationSupported?d.rows.filter(r=>r.kind==='application'&&!r.archived_at):[];
   $('live-source').replaceChildren();line($('live-source'),'b',d.live?'Verified production source':'Production source verification required');if(d.live){line($('live-source'),'p',d.live.revision);line($('live-source'),'p','GitHub main and running Render deployment checked '+d.live.verified_at+'. Runtime health is not continuously monitored.');}else line($('live-source'),'p',d.live_error||'Refresh provider verification locally. No revision will be guessed.');line($('live-source'),'p','Production unchanged');
   $("connection").textContent="Local device connected";$("connect").hidden=true;$("connection-settings").open=false;$("refresh").disabled=$("disconnect").disabled=$("release-refresh").disabled=false;
   if(workspaceId&&!rows.some(r=>r.id===workspaceId&&r.actionable)){workspaceApproved=false;pendingDraft="";}
   if(selectedDraft&&!rows.some(r=>r.id===selectedDraft&&r.actionable))selectedDraft="";
   if(!selectedDraft){const saved=rememberedDraft();if(rows.some(r=>r.id===saved&&r.actionable))selectedDraft=saved;}
   if(!selectedDraft)selectedDraft=rows.find(r=>r.actionable)?.id||'';
   syncSelection();draw();message(applicationSupported?"Connected · choose an authorised OS copy to open its Editor here.":"This local companion needs the application-draft update. Existing worktrees and permissions are preserved.");clearTimeout(expiry);
   if(!trusted)expiry=setTimeout(()=>{send("disconnect");offline("Pairing expired. Reconnect to refresh local metadata.");},600000);
   if(!restoreAttempted){restoreAttempted=true;if(selectedDraft)openSelected("edit").catch(e=>message(e.message));}
  }
  if(d.type==="workspace-approved")showWorkspace(d.draft_id).catch(e=>{workspaceApproved=false;pendingDraft="";workspace?.refreshCatalog();tab("editor");message("Editor could not open: "+e.message+". Reconnect and confirm the draft to retry.");});
  if(d.type==='application-result'){
   const r=d.result;
   if(r.archived){send('workspace-close');workspace?.dispose();workspace=null;workspaceId=null;workspaceApproved=false;selectedDraft='';workspaceLoading=mountWorkspace(null);}
   else if(r.operation){selectedDraft=r.id;syncSelection();draw();openSelected('edit').catch(e=>message(e.message));}
   else if(workspaceApproved)workspace?.resume().catch(e=>message(e.message));
   // The local bridge sends its refreshed catalog before the operation result.
   // Another refresh here can race the selected draft's confirmation request.
  }
  if(d.type==='technical-catalog')$('technical-records').textContent=JSON.stringify(d.result.rows,null,2);
  if(d.type==="workspace-result"){
   const request=workspaceRequests.get(d.request_id);if(!request||request.draftId!==d.draft_id)return;
   workspaceRequests.delete(d.request_id);clearTimeout(request.timer);
   if(d.error){if(/permission expired|Confirm this selected draft/.test(d.error)){workspaceApproved=false;workspace?.refreshCatalog();message("Local draft permission expired. Use Connection → Resume editor to confirm again; unsaved text is preserved.");}request.reject(Error(d.error));}else request.resolve(d.result);
  }
  if(d.type==="release-catalog"){releaseData=d.result;showRelease();message("Approved revisions revalidated. Live remains unverified; publishing is mock-only.");}
  if(d.type==="release-result"){if(d.result?.frame){$("release-image").src="data:image/jpeg;base64,"+d.result.frame.image;$("release-image").hidden=false;$("release-preview-controls").hidden=false;$("release-preview-status").textContent="Running · synthetic combined candidate · "+d.result.frame.width+" × "+d.result.frame.height;}if(d.result?.stopped){$("release-image").hidden=true;$("release-preview-controls").hidden=true;$("release-preview-status").textContent="Stopped. Candidate source preserved.";}send("release-catalog");}
  if(d.type==="disconnected")offline("Local device disconnected.");
  if(d.type==="error"){pendingDraft="";message(d.error||"Local operation unavailable.");$("release-preview-status").textContent=d.error||"Local operation unavailable.";}
 });
 // Only remember an address, never credentials. Browsers require a user gesture for the local popup.
 try{const saved=localStorage.getItem("studio-companion-origin");if(saved){const u=new URL(saved);if(u.protocol==="http:"&&u.hostname==="127.0.0.1"&&u.port&&!u.username&&!u.password&&!u.search&&!u.hash&&u.pathname==="/"){$("origin").value=u.origin;message("Trusted address remembered. Click Connect to reopen the secure localhost window; approval resumes automatically where permitted.");}}}catch{}
 function heartbeat(){clearTimeout(heartbeatTimer);heartbeatTimer=setTimeout(()=>{if(!connected)return;if(!popup||popup.closed){offline("Local approval window closed. Click Connect; unsaved local editors are preserved.");return;}if(Date.now()-lastSeen>90000)$("connection").textContent="Reconnecting";send("ping");heartbeat();},60000);}
 const advanced=document.createElement('details');advanced.innerHTML='<summary>Advanced · technical task history</summary><p>Internal tasks and archived application drafts. Worktrees, ownership, tests and recovery records are retained.</p><button id="technical-refresh">Load technical records</button><pre id="technical-records"></pre>';$('history').append(advanced);$('technical-refresh').onclick=()=>send('technical-catalog');
 tab("editor");workspaceLoading=mountWorkspace(null).catch(e=>message("Editor could not load: "+e.message));
 window.addEventListener("pagehide",()=>{if(connected)send("disconnect");});
})();
