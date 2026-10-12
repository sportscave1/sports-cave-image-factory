"use strict";
(() => {
 const $=id=>document.getElementById(id); let popup=null, origin="", nonce="", connected=false, rows=[], expiry, releaseData=null, activeCandidate=null, lastSeen=0, trusted=false, selectedDraft="", heartbeatTimer;
 let workspace=null,workspaceId=null,workspaceIntent="edit",workspaceModule=null,workspaceSupported=false;const workspaceRequests=new Map();
 const message=s=>$("message").textContent=s;
 function send(type,extra={}){if(popup&&!popup.closed)popup.postMessage({studio:1,type,nonce,...extra},origin);else offline("Local window closed. Reconnect when needed.");}
 function offline(text){for(const r of workspaceRequests.values()){clearTimeout(r.timer);r.reject(Error("Local companion disconnected; unsaved editor text is preserved."));}workspaceRequests.clear();clearTimeout(heartbeatTimer);releaseData=null;activeCandidate=null;$("release-refresh").disabled=$("prepare").disabled=true;for(const id of ["release-options","release-candidates","release-checks","release-history"])$(id).replaceChildren();$("release-image").hidden=true;$("release-preview-controls").hidden=true;connected=false;clearTimeout(expiry);rows=[];$("connection").textContent="Local device offline";$("refresh").disabled=$("disconnect").disabled=$("resume-editor").disabled=true;$("list").replaceChildren();$("evidence").replaceChildren();syncSelection();message(text);}
 function tab(id){document.body?.classList.remove("editing");$("workspace-v6").hidden=true;for(const n of ["live","drafts","editor","preview","tests","releases","history"])$(n).hidden=n!==id;document.querySelectorAll("[data-tab]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.tab===id)));}
 document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>tab(b.dataset.tab));
 function line(parent,tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;parent.append(e);return e;}
 function syncSelection(){
  const draft=rows.find(d=>d.id===selectedDraft),label=draft?`${draft.name} · ${draft.category} · ${draft.owner}`:"Select a registered draft";
  $("selected").textContent=$("preview-selected").textContent=label;
  $("tests-selected").textContent=draft?label:"All registered drafts";
  for(const id of ["selected-open","selected-edit","selected-preview","selected-changes"])$(id).disabled=!connected||!draft?.actionable;
 }
 async function openSelected(intent){
  const draft=rows.find(d=>d.id===selectedDraft);if(!connected||!draft?.actionable)return;
  if(workspaceSupported&&["edit","preview","open","changes"].includes(intent)){
   if(workspace&&workspaceId!==draft.id&&!await workspace.canLeave()){selectedDraft=workspaceId;syncSelection();draw();return;}
   workspaceIntent=intent;
   send("workspace-begin",{draft_id:draft.id});message("Confirm the selected draft editor once in the local window.");popup.focus();return;
  }
  send("handoff",{draft_id:draft.id,intent});tab(intent==="preview"?"preview":"editor");
  $("handoff-status").textContent="Confirm the selected draft in the local window. Its private editor link stays on your computer.";
  message("Confirm this draft and action on your local device.");popup.focus();
 }
 for(const [id,intent] of [["selected-open","open"],["selected-edit","edit"],["selected-preview","preview"],["selected-changes","changes"]])$(id).onclick=()=>openSelected(intent);
 function draw(){ $("list").replaceChildren();$("evidence").replaceChildren();
  for(const d of rows){if(!$("category").value||d.category===$("category").value){const c=line($("list"),"article","","card");line(c,"h3",d.name);line(c,"div",`${d.category} · ${d.owner} · ${d.status}
Updated ${d.updated_at||"not recorded"}
${d.branch}
Draft ${d.id} · checkpoint ${d.revision}`,"facts");line(c,"p",`Recorded tests: ${d.test?.passed===true?"Passed":d.test?.passed===false?"Failed":"Not recorded"} · ${d.test?.verified_at||"—"}`);
    for(const [intent,label] of [["open","Open"],["edit","Edit"],["preview","Preview"],["changes","View Changes"]]){const b=line(c,"button",label);b.disabled=!d.actionable;b.onclick=()=>{selectedDraft=d.id;syncSelection();draw();openSelected(intent);};}if(!d.actionable)line(c,"p",d.action_reason||"This draft requires its assigned owner companion.");}
   if(selectedDraft&&d.id!==selectedDraft)continue;
   const e=line($("evidence"),"article","","card");line(e,"h3",d.name);line(e,"p",`Recorded review: ${d.review_status} · ${d.status==="Approved"||d.status==="Integrated"?"Approved task":"Unfinished / awaiting approval"}`);line(e,"p",d.test?.evidence||"No test evidence recorded.");line(e,"p",`Tested snapshot: ${d.test?.snapshot?.files_hash||"unavailable"}`);line(e,"p","Use Check approved revisions in Releases to revalidate immutable task eligibility. Production publishing disabled.");
  }if(!$("list").children.length)line($("list"),"p","No registered drafts in this category.");}
 async function moduleFrom(source){const url=URL.createObjectURL(new Blob([source],{type:"text/javascript"}));try{return await import(url);}finally{URL.revokeObjectURL(url);}}
 async function showWorkspace(draftId){
  if(draftId!==selectedDraft)return;
  if(workspace&&workspaceId===draftId){tab("editor");$("editor").hidden=true;$("workspace-v6").hidden=false;document.body.classList.add("editing");await workspace.resume();await workspace.intent(workspaceIntent);message("Local editor connected · selected draft permission restored");return;}
  if(workspace)workspace.dispose();workspace=null;workspaceId=draftId;
  const bundle=window.STUDIO_V6_BUNDLE;
  if(!workspaceModule){const css=document.createElement("style");css.dataset.studioEditorCss="true";css.textContent=bundle["editor.css"]+bundle["workspace.css"];document.head.append(css);workspaceModule=await moduleFrom(bundle["workspace.js"]);}
  for(const id of ["live","drafts","editor","preview","tests","releases","history"])$(id).hidden=true;
  $("workspace-v6").hidden=false;document.body.classList.add("editing");
  const transport=(_path,command)=>new Promise((resolve,reject)=>{
   if(!connected)return reject(Error("Local companion offline. Unsaved work is preserved; reconnect before saving."));
   const request_id=Array.from(crypto.getRandomValues(new Uint8Array(12)),x=>x.toString(16).padStart(2,"0")).join("");
   const timer=setTimeout(()=>{workspaceRequests.delete(request_id);reject(Error("Local operation timed out. Reopen and compare before retrying a save."));},120000);
   workspaceRequests.set(request_id,{resolve,reject,timer,draftId});send("workspace-call",{request_id,draft_id:draftId,command});
  });
  workspace=await workspaceModule.mount($("workspace-v6"),transport,{loadEditor:()=>moduleFrom(bundle["editor.js"]),drafts:()=>rows,
   selectDraft:id=>{selectedDraft=id;syncSelection();openSelected("edit");},back:()=>{send("workspace-close");workspace=null;workspaceId=null;tab("drafts");send("catalog");}});
  await workspace.intent(workspaceIntent);message("Local editor connected · changes stay in the selected draft");
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
 $("local-fallback").onclick=()=>{if(connected&&selectedDraft){send("handoff",{draft_id:selectedDraft,intent:"edit"});popup.focus();}};
 $("release-refresh").onclick=()=>send("release-catalog");
 $("prepare").onclick=()=>releaseRequest("prepare",null,{task_ids:[...document.querySelectorAll("#release-options input:checked")].map(e=>e.value)});
 for(const [id,event] of [["release-desktop",{action:"size",mode:"desktop"}],["release-mobile",{action:"size",mode:"mobile"}],["release-frame",{action:"frame"}]])$(id).onclick=()=>{if(activeCandidate)send("release-frame",{id:activeCandidate.id,event});};
 $("release-stop").onclick=()=>{if(activeCandidate)releaseRequest("preview-stop",activeCandidate);};
 $("category").onchange=draw;
 $("connect").onclick=()=>{try{const u=new URL($("origin").value);if(u.protocol!=="http:"||u.hostname!=="127.0.0.1"||!u.port||u.username||u.password||u.search||u.hash||u.pathname!=="/")throw Error("Enter only http://127.0.0.1:port. Never paste a private token here.");if(connected)send("disconnect");offline("Approve this connection in the localhost window.");origin=u.origin;try{localStorage.setItem("studio-companion-origin",origin);}catch{}$("connection").textContent="Reconnecting · awaiting localhost";nonce=Array.from(crypto.getRandomValues(new Uint8Array(24)),x=>x.toString(16).padStart(2,"0")).join("");popup=window.open(origin+"/pair#"+nonce,"_blank");clearTimeout(expiry);expiry=setTimeout(()=>{if(!connected)offline("Local device offline. Check that the Windows companion is running, then reconnect.");},15000);if(!popup)throw Error("Popup blocked. Allow this popup or use the private local launcher directly.");}catch(e){message(e.message);}};
 $("resume-editor").onclick=()=>openSelected("edit");
 $("disconnect").onclick=()=>{send("disconnect");offline("Disconnected. Local editor work is preserved.");};
 $("refresh").onclick=()=>send("catalog");
 window.addEventListener("message",e=>{const d=e.data;if(e.source!==popup||e.origin!==origin||!d||d.studio!==1||d.nonce!==nonce)return;
  lastSeen=Date.now();
  if(d.type==="ready")send("request");
  if(d.type==="reconnecting")$("connection").textContent="Reconnecting";
  if(d.type==="pong")$("connection").textContent="Local device connected";
  if(d.type==="catalog"){workspaceSupported=d.workspace_v6===true;if(!Array.isArray(d.rows)||!Array.isArray(d.categories))return;connected=true;heartbeat();trusted=d.trusted===true;lastSeen=Date.now();rows=d.rows;$("connection").textContent="Local device connected · secure local workspace";$("refresh").disabled=$("disconnect").disabled=$("release-refresh").disabled=$("resume-editor").disabled=false;$("category").replaceChildren(new Option("All categories",""));d.categories.forEach(c=>$("category").append(new Option(c,c)));if(selectedDraft&&!rows.some(r=>r.id===selectedDraft))selectedDraft="";syncSelection();draw();message("Connected. Local confirmation is required before opening an editor or preview.");clearTimeout(expiry);if(!trusted)expiry=setTimeout(()=>{send("disconnect");offline("Pairing expired. Reconnect to refresh local metadata.");},600000);}
  if(d.type==="workspace-approved")showWorkspace(d.draft_id).catch(e=>{tab("editor");message("Embedded editor unavailable: "+e.message+". Use Open secure local workspace below; authentication remains required.");$("local-fallback").hidden=false;});
  if(d.type==="workspace-result"){
   const request=workspaceRequests.get(d.request_id);if(!request||request.draftId!==d.draft_id)return;
   workspaceRequests.delete(d.request_id);clearTimeout(request.timer);d.error?request.reject(Error(d.error)):request.resolve(d.result);
  }
  if(d.type==="workspace-opened"&&d.draft_id===selectedDraft)$("handoff-status").textContent="Selected local workspace opened. Save, Undo, Preview and revision recovery operate only on that draft.";
  if(d.type==="release-catalog"){releaseData=d.result;showRelease();message("Approved revisions revalidated. Live remains unverified; publishing is mock-only.");}
  if(d.type==="release-result"){if(d.result?.frame){$("release-image").src="data:image/jpeg;base64,"+d.result.frame.image;$("release-image").hidden=false;$("release-preview-controls").hidden=false;$("release-preview-status").textContent="Running · synthetic combined candidate · "+d.result.frame.width+" × "+d.result.frame.height;}if(d.result?.stopped){$("release-image").hidden=true;$("release-preview-controls").hidden=true;$("release-preview-status").textContent="Stopped. Candidate source preserved.";}send("release-catalog");}
  if(d.type==="disconnected")offline("Local device disconnected.");
  if(d.type==="error"){message(d.error||"Local operation unavailable.");$("release-preview-status").textContent=d.error||"Local operation unavailable.";}
 });
 // Only remember an address, never credentials. Browsers require a user gesture for the local popup.
 try{const saved=localStorage.getItem("studio-companion-origin");if(saved){const u=new URL(saved);if(u.protocol==="http:"&&u.hostname==="127.0.0.1"&&u.port&&!u.username&&!u.password&&!u.search&&!u.hash&&u.pathname==="/"){$("origin").value=u.origin;message("Trusted address remembered. Click Connect to reopen the secure localhost window; approval resumes automatically where permitted.");}}}catch{}
 function heartbeat(){clearTimeout(heartbeatTimer);heartbeatTimer=setTimeout(()=>{if(!connected)return;if(!popup||popup.closed){offline("Local approval window closed. Click Connect; unsaved local editors are preserved.");return;}if(Date.now()-lastSeen>90000)$("connection").textContent="Reconnecting";send("ping");heartbeat();},60000);}
 window.addEventListener("pagehide",()=>{if(connected)send("disconnect");});
})();