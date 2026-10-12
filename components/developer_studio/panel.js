"use strict";
(() => {
 const $=id=>document.getElementById(id); let popup=null, origin="", nonce="", connected=false, rows=[], expiry, releaseData=null, activeCandidate=null, lastSeen=0, trusted=false, selectedDraft="", heartbeatTimer;
 const message=s=>$("message").textContent=s;
 function send(type,extra={}){if(popup&&!popup.closed)popup.postMessage({studio:1,type,nonce,...extra},origin);else offline("Local window closed. Reconnect when needed.");}
 function offline(text){clearTimeout(heartbeatTimer);releaseData=null;activeCandidate=null;$("release-refresh").disabled=$("prepare").disabled=true;for(const id of ["release-options","release-candidates","release-checks","release-history"])$(id).replaceChildren();$("release-image").hidden=true;$("release-preview-controls").hidden=true;connected=false;clearTimeout(expiry);rows=[];$("connection").textContent="Local device offline";$("refresh").disabled=$("disconnect").disabled=true;$("list").replaceChildren();$("evidence").replaceChildren();$("selected").textContent="Select a registered draft";message(text);}
 function tab(id){for(const n of ["live","drafts","editor","preview","tests","releases","history"])$(n).hidden=n!==id;document.querySelectorAll("[data-tab]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.tab===id)));}
 document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>tab(b.dataset.tab));
 function line(parent,tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;parent.append(e);return e;}
 function draw(){ $("list").replaceChildren();$("evidence").replaceChildren();
  for(const d of rows){if(!$("category").value||d.category===$("category").value){const c=line($("list"),"article","","card");line(c,"h3",d.name);line(c,"div",`${d.category} · ${d.owner} · ${d.status}
Updated ${d.updated_at||"not recorded"}
${d.branch}
Draft ${d.id} · checkpoint ${d.revision}`,"facts");line(c,"p",`Recorded tests: ${d.test?.passed===true?"Passed":d.test?.passed===false?"Failed":"Not recorded"} · ${d.test?.verified_at||"—"}`);
    for(const [intent,label] of [["open","Open"],["edit","Edit"],["preview","Preview"],["changes","View Changes"]]){const b=line(c,"button",label);b.disabled=!d.actionable;b.onclick=()=>{send("handoff",{draft_id:d.id,intent});$("selected").textContent=`${d.name} · ${d.category} · ${d.owner}`;tab("editor");message("Confirm this draft and action in the local approval window.");popup.focus();};}}
   const e=line($("evidence"),"article","","card");line(e,"h3",d.name);line(e,"p",`Recorded review: ${d.review_status} · ${d.status==="Approved"||d.status==="Integrated"?"Approved task":"Unfinished / awaiting approval"}`);line(e,"p",d.test?.evidence||"No test evidence recorded.");line(e,"p",`Tested snapshot: ${d.test?.snapshot?.files_hash||"unavailable"}`);line(e,"p","Use Check approved revisions in Releases to revalidate immutable task eligibility. Production publishing disabled.");
  }if(!$("list").children.length)line($("list"),"p","No registered drafts in this category.");}
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
 $("category").onchange=draw;
 $("connect").onclick=()=>{try{const u=new URL($("origin").value);if(u.protocol!=="http:"||u.hostname!=="127.0.0.1"||!u.port||u.username||u.password||u.search||u.hash||u.pathname!=="/")throw Error("Enter only http://127.0.0.1:port. Never paste a private token here.");if(connected)send("disconnect");offline("Approve this connection in the localhost window.");origin=u.origin;try{localStorage.setItem("studio-companion-origin",origin);}catch{}$("connection").textContent="Reconnecting · awaiting localhost";nonce=Array.from(crypto.getRandomValues(new Uint8Array(24)),x=>x.toString(16).padStart(2,"0")).join("");popup=window.open(origin+"/pair#"+nonce,"_blank");clearTimeout(expiry);expiry=setTimeout(()=>{if(!connected)offline("Local device offline. Check that the Windows companion is running, then reconnect.");},15000);if(!popup)throw Error("Popup blocked. Allow this popup or use the private local launcher directly.");}catch(e){message(e.message);}};
 $("disconnect").onclick=()=>{send("disconnect");offline("Disconnected. Local editor work is preserved.");};
 $("refresh").onclick=()=>send("catalog");
 window.addEventListener("message",e=>{const d=e.data;if(e.source!==popup||e.origin!==origin||!d||d.studio!==1||d.nonce!==nonce)return;
  lastSeen=Date.now();
  if(d.type==="ready")send("request");
  if(d.type==="reconnecting")$("connection").textContent="Reconnecting";
  if(d.type==="pong")$("connection").textContent="Local device connected";
  if(d.type==="catalog"){if(!Array.isArray(d.rows)||!Array.isArray(d.categories))return;connected=true;$("selected").textContent=selectedDraft||"Select a registered draft";heartbeat();trusted=d.trusted===true;lastSeen=Date.now();rows=d.rows;$("connection").textContent="Local device connected · read-only catalog";$("refresh").disabled=$("disconnect").disabled=$("release-refresh").disabled=false;$("category").replaceChildren(new Option("All categories",""));d.categories.forEach(c=>$("category").append(new Option(c,c)));draw();message("Connected. Local confirmation is required before opening an editor or preview.");clearTimeout(expiry);if(!trusted)expiry=setTimeout(()=>{send("disconnect");offline("Pairing expired. Reconnect to refresh local metadata.");},600000);}
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