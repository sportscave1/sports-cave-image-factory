"use strict";
(() => {
 const $=id=>document.getElementById(id); let popup=null, origin="", nonce="", connected=false, rows=[], expiry;
 const message=s=>$("message").textContent=s;
 function send(type,extra={}){if(popup&&!popup.closed)popup.postMessage({studio:1,type,nonce,...extra},origin);else offline("Local window closed. Reconnect when needed.");}
 function offline(text){connected=false;clearTimeout(expiry);rows=[];$("connection").textContent="Local device offline";$("refresh").disabled=$("disconnect").disabled=true;$("list").replaceChildren();$("evidence").replaceChildren();$("selected").textContent="Select a registered draft";message(text);}
 function tab(id){for(const n of ["live","drafts","editor","releases"])$(n).hidden=n!==id;document.querySelectorAll("[data-tab]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.tab===id)));}
 document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>tab(b.dataset.tab));
 function line(parent,tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;parent.append(e);return e;}
 function draw(){ $("list").replaceChildren();$("evidence").replaceChildren();
  for(const d of rows){if(!$("category").value||d.category===$("category").value){const c=line($("list"),"article","","card");line(c,"h3",d.name);line(c,"div",`${d.category} · ${d.owner} · ${d.status}
Updated ${d.updated_at||"not recorded"}
${d.branch}
Draft ${d.id} · checkpoint ${d.revision}`,"facts");line(c,"p",`Recorded tests: ${d.test?.passed===true?"Passed":d.test?.passed===false?"Failed":"Not recorded"} · ${d.test?.verified_at||"—"}`);
    for(const [intent,label] of [["open","Open"],["edit","Edit"],["preview","Preview"],["changes","View Changes"]]){const b=line(c,"button",label);b.disabled=!d.actionable;b.onclick=()=>{send("handoff",{draft_id:d.id,intent});$("selected").textContent=`${d.name} · ${d.category} · ${d.owner}`;tab("editor");message("Confirm this draft and action in the local approval window.");popup.focus();};}}
   const e=line($("evidence"),"article","","card");line(e,"h3",d.name);line(e,"p",`Recorded review: ${d.review_status} · ${d.status==="Approved"||d.status==="Integrated"?"Approved task":"Unfinished / awaiting approval"}`);line(e,"p",d.test?.evidence||"No test evidence recorded.");line(e,"p",`Tested snapshot: ${d.test?.snapshot?.files_hash||"unavailable"}`);line(e,"p","Release eligibility: unavailable; publishing disabled.");
  }if(!$("list").children.length)line($("list"),"p","No registered drafts in this category.");}
 $("category").onchange=draw;
 $("connect").onclick=()=>{try{const u=new URL($("origin").value);if(u.protocol!=="http:"||u.hostname!=="127.0.0.1"||!u.port||u.username||u.password||u.search||u.hash||u.pathname!=="/")throw Error("Enter only http://127.0.0.1:port. Never paste a private token here.");if(connected)send("disconnect");offline("Approve this connection in the localhost window.");origin=u.origin;nonce=Array.from(crypto.getRandomValues(new Uint8Array(24)),x=>x.toString(16).padStart(2,"0")).join("");popup=window.open(origin+"/pair#"+nonce,"_blank");if(!popup)throw Error("Popup blocked. Allow this popup or use the private local launcher directly.");}catch(e){message(e.message);}};
 $("disconnect").onclick=()=>{send("disconnect");offline("Disconnected. Local editor work is preserved.");};
 $("refresh").onclick=()=>send("catalog");
 window.addEventListener("message",e=>{const d=e.data;if(e.source!==popup||e.origin!==origin||!d||d.studio!==1||d.nonce!==nonce)return;
  if(d.type==="ready")send("request");
  if(d.type==="catalog"){if(!Array.isArray(d.rows)||!Array.isArray(d.categories))return;connected=true;rows=d.rows;$("connection").textContent="Local device connected · read-only catalog";$("refresh").disabled=$("disconnect").disabled=false;$("category").replaceChildren(new Option("All categories",""));d.categories.forEach(c=>$("category").append(new Option(c,c)));draw();message("Connected. Local confirmation is required before opening an editor or preview.");clearTimeout(expiry);expiry=setTimeout(()=>{send("disconnect");offline("Pairing expired. Reconnect to refresh local metadata.");},600000);}
  if(d.type==="disconnected")offline("Local device disconnected.");
  if(d.type==="error")message(d.error||"Local operation unavailable.");
 });
 window.addEventListener("pagehide",()=>{if(connected)send("disconnect");});
})();