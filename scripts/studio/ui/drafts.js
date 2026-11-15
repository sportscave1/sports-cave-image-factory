"use strict";
const fragment = location.hash.slice(1);
const params = new URLSearchParams(fragment);
let token = fragment.startsWith("token=") ? params.get("token") : fragment;
const intent = fragment.startsWith("token=") ? params.get("intent") : "open";
history.replaceState(null, "", location.pathname);
const $ = id => document.getElementById(id);
let state, busy = false, dirty = false, activeTab = "draft", hasFrame = false;
let editorModule;
function message(text) { $("message").textContent = text; }
async function request(path, data, retried = false) {
  const response = await fetch(path, {method: data ? "POST" : "GET", headers: {
    "X-Studio-Token": token, ...(data ? {"Content-Type": "application/json"} : {})
  }, ...(data ? {body: JSON.stringify(data)} : {})});
  const result = await response.json();
  if (response.status === 401 && !retried) {
    // Restore authentication without reloading the editor or replacing unsaved source.
    let approvedOrigin;try { approvedOrigin = localStorage.getItem("studio-approved-origin"); } catch {}
    if (approvedOrigin) {
      const renew = () => fetch("/api/device", {method:"POST",headers:{"Content-Type":"application/json","X-Studio-Local":"1"},body:JSON.stringify({operation:"renew",origin:approvedOrigin})});
      const renewed = globalThis.navigator?.locks ? await navigator.locks.request("studio-device-renewal",renew) : await renew();
      if (renewed.ok) {token=(await renewed.json()).token;return request(path,data,true);}
    }
  }
  if (!response.ok) throw new Error(result.error || "Request failed");
  return result;
}
function render() {
  const d = state.draft;
  $("selected-draft").textContent=(d?d.name+" · ":"")+state.task.id+" · "+state.task.owner;
  $("test-evidence").textContent=JSON.stringify({task_id:state.task.id,draft_id:d?.id,status:state.task_status,recorded_test:state.test||"No test result recorded",current_files_verified:false,note:"Recorded evidence only. Re-run focused tests before review after editing."},null,2);
  $("workspace-category").textContent = "DEVELOPER STUDIO / " + state.task.category;
  $("name").textContent = d ? d.name : "Name your draft";
  $("identity").replaceChildren();
  for (const [key, value] of Object.entries(state.task)) {
    const term = document.createElement("dt"), detail = document.createElement("dd");
    term.textContent = key.replaceAll("_", " "); detail.textContent = value;
    $("identity").append(term, detail);
  }
  $("create").hidden = !!d; $("checkpoint").hidden = !d;
  $("recover").disabled = !d || !d.revision;
  $("revision").replaceChildren(); $("changes").replaceChildren();
  if (!d) return;
  $("files").value = (d.selected_revision?.files || []).map(f => f.path).join("\n");
  for (const rev of [...d.revisions].reverse()) {
    const option = document.createElement("option"); option.value = rev.number;
    option.textContent = "Revision " + rev.number + " · " + new Date(rev.saved_at).toLocaleString();
    $("revision").append(option);
  }
  for (const path of d.changed_since_checkpoint.length ? d.changed_since_checkpoint : ["No selected-file changes detected."]) {
    const item = document.createElement("li"); item.textContent = path; $("changes").append(item);
  }
}
async function refresh() { state = await request("/api/state"); render(); dirty = false; }
async function run(action) {
  if (busy) return;
  busy = true;
  try { await action(); } catch (error) { message(error.message); }
  finally { busy = false; }
}
$("files").addEventListener("input", () => { dirty = true; });
window.addEventListener("beforeunload", event => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
$("refresh").onclick = () => run(async () => {
  if (dirty && !confirm("Discard your unsaved checkpoint file selection? Source files will not change.")) return;
  await refresh(); message("Draft reopened. Source files preserved.");
});
$("new").onclick = () => run(async () => {
  await request("/api/action", {action: "new", name: $("draft-name").value});
  await refresh(); message("Draft created in the assigned task.");
});
$("save").onclick = () => run(async () => {
  await request("/api/action", {action: "save", expected_revision: state.draft.revision,
    files: $("files").value.split("\n").map(s => s.trim()).filter(Boolean)});
  await refresh(); message("Revision " + state.draft.revision + " saved. No source files or Git commits changed.");
});
$("recover").onclick = () => run(async () => {
  const result = await request("/api/action", {action: "recover", revision: Number($("revision").value)});
  message("Recovery copy: " + result.recovery_path);
});
$("close").onclick = () => run(async () => {
  if (dirty && !confirm("Stop with an unsaved checkpoint file selection?")) return;
  await request("/api/action", {action: "close"}); dirty = false;
  document.querySelectorAll("button").forEach(b => { b.disabled = true; });
  message("Draft Studio stopped. Reopen with the task launcher.");
});
async function selectTab(tab) {
  activeTab=tab;
  $("draft-panel").hidden=tab!=="draft";$("tests-panel").hidden=tab!=="tests";
  $("editor-panel").hidden=tab!=="editor";
  $("preview-panel").hidden=tab!=="preview"||!hasFrame;
  $("preview-empty").hidden=tab!=="preview"||hasFrame;
  document.querySelectorAll("[data-workspace-tab]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.workspaceTab===tab)));
  if(tab==="editor"){
    editorModule=editorModule||await import("/editor.js");
    await editorModule.mount($("editor-panel"),request,showFrame);
  }
}
document.querySelectorAll("[data-workspace-tab]").forEach(b=>b.onclick=()=>run(()=>selectTab(b.dataset.workspaceTab)));
$("editor-panel").addEventListener("studio-saved",()=>run(async()=>{
  state=await request("/api/state");if(!dirty)render();
}));
run(async () => {
  await refresh();message("Connected to the selected draft. Editor changes remain on this computer.");
  if(intent==="edit"||intent==="changes"){
    await selectTab("editor");
    if(intent==="changes")document.getElementById("ed-changes").click();
  }else if(intent==="preview"){
    await selectTab("preview");await previewAction("start-preview");
  }
});


let frameSize = {width:1280,height:900};
function showFrame(frame) {
  hasFrame=true;$("preview-panel").hidden=activeTab!=="preview";$("preview-empty").hidden=true;
  $("preview-image").src="data:image/jpeg;base64,"+frame.image;
  frameSize=frame;
  $("preview-status").textContent="Running · "+frame.width+" × "+frame.height+" · synthetic data only";
}
async function previewAction(action,event) {
  message("Working in the isolated preview…");
  const result=await request("/api/action",{action,event});
  if (result.image) showFrame(result);
  else { hasFrame=false;$("preview-panel").hidden=true;$("preview-empty").hidden=activeTab!=="preview"; }
  message(action==="stop-preview" ? "Preview stopped. Draft source preserved." : "Preview ready. No production connections.");
}
$("start-preview").onclick=()=>run(async()=>{await selectTab("preview");await previewAction("start-preview");});
$("stop-preview").onclick=()=>run(()=>previewAction("stop-preview"));
$("restart-preview").onclick=()=>run(()=>previewAction("restart-preview"));
const sendEvent=event=>run(()=>previewAction("preview-event",event));
$("preview-refresh").onclick=()=>sendEvent({action:"frame"});
$("synthetic-login").onclick=()=>sendEvent({action:"login-synthetic"});
$("desktop").onclick=()=>sendEvent({action:"size",mode:"desktop"});
$("mobile").onclick=()=>sendEvent({action:"size",mode:"mobile"});
$("scroll-up").onclick=()=>sendEvent({action:"scroll",delta:-700});
$("scroll-down").onclick=()=>sendEvent({action:"scroll",delta:700});
$("send-text").onclick=()=>sendEvent({action:"text",text:$("preview-text").value});
$("preview-tab").onclick=()=>sendEvent({action:"key",key:"Tab"});
$("preview-enter").onclick=()=>sendEvent({action:"key",key:"Enter"});
$("preview-image").onclick=event=>{
  const box=event.currentTarget.getBoundingClientRect();
  sendEvent({action:"click",x:Math.floor((event.clientX-box.left)*frameSize.width/box.width),
    y:Math.floor((event.clientY-box.top)*frameSize.height/box.height)});
};

$("edit-draft").onclick=()=>run(()=>selectTab("editor"));
