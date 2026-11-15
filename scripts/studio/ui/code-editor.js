// Complete source stays text. Application code executes only inside the existing sandbox.
export function patch(a,b){let start=0,end=0;while(start<a.length&&start<b.length&&a[start]===b[start])start++;while(end<a.length-start&&end<b.length-start&&a.at(-1-end)===b.at(-1-end))end++;return {start,removed:a.slice(start,a.length-end),inserted:b.slice(start,b.length-end)};}
export function sourceHasSecret(text){return /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:ghp_|github_pat_|shpat_|shpca_)[A-Za-z0-9_]{20,}|\bAKIA[0-9A-Z]{16}\b|(?:password|secret|api_key|access_token)\s*[:=]\s*['"][A-Za-z0-9/+_-]{8,}['"]/i.test(text);}
export class Buffers {
 constructor(){this.files=new Map();this.active=null;this.revision=null;}
 current(){return this.files.get(this.active);}
 dirty(){return [...this.files.values()].filter(b=>b.value!==b.base);}
 open(m,saved){if(!this.files.has(m.path)){const canonical=m.source.replace(/\r\n/g,'\n'),{source:unusedSource,...metadata}=m,b={...metadata,eol:m.source.includes('\r\n')?'\r\n':'\n',base:canonical,value:canonical,undo:[],redo:[],bytes:0};if(saved){Object.assign(b,{hash:saved.hash,revision:saved.revision,base:saved.base,value:saved.value,conflict:saved.hash!==m.hash||saved.revision!==m.revision});b.undo=[patch(b.base,b.value)];this.revision=saved.revision;}this.files.set(m.path,b);if(this.revision===null)this.revision=m.revision;}this.active=m.path;return this.current();}
 update(value){const b=this.current();if(!b.editable)throw Error('Source is read-only.');if(value===b.value)return;const p=patch(b.value,value);b.undo.push(p);b.bytes+=(p.removed.length+p.inserted.length)*2;b.redo=[];b.value=value;while(b.undo.length>100||b.bytes>4*1024*1024&&b.undo.length>1){const old=b.undo.shift();b.bytes-=(old.removed.length+old.inserted.length)*2;}}
 updateFile(path,value){const active=this.active;this.active=path;try{this.update(value);}finally{this.active=active;}}
 undo(){const b=this.current(),p=b?.undo.pop();if(!p)return false;b.value=b.value.slice(0,p.start)+p.removed+b.value.slice(p.start+p.inserted.length);b.redo.push(p);return true;}
 redo(){const b=this.current(),p=b?.redo.pop();if(!p)return false;b.value=b.value.slice(0,p.start)+p.inserted+b.value.slice(p.start+p.removed.length);b.undo.push(p);return true;}
}
let selectionEpoch=0,sourceContext=null;
let panel,request,showFrame,key='',store=new Buffers(),busy=false,timer,paint,recoveryFailed=false;
const $=id=>panel.querySelector('#'+id),esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const msg=s=>{$('ed-status').textContent=s;},notify=()=>panel.dispatchEvent(new CustomEvent('studio-buffer-change',{bubbles:true,detail:{count:store.dirty().length,path:store.active,paths:store.dirty().map(b=>b.path)}}));
function persist(){if(!key)return true;try{const dirty=store.dirty(),previous=JSON.parse(localStorage.getItem(key)||'null');for(const b of dirty)localStorage.setItem(key+':'+b.path,JSON.stringify({path:b.path,hash:b.hash,revision:b.revision,base:b.base,value:b.value}));for(const path of previous?.dirty||[])if(!dirty.some(b=>b.path===path))localStorage.removeItem(key+':'+path);localStorage.setItem(key,JSON.stringify({version:2,active:store.active,tabs:[...store.files.keys()],dirty:dirty.map(b=>b.path)}));recoveryFailed=false;return true;}catch{recoveryFailed=true;msg('Recovery storage unavailable/full. Keep this tab open and Save Draft. All buffers remain in memory.');return false;}}
function flush(){clearTimeout(timer);timer=0;return persist();}
function schedule(){if(!timer)timer=setTimeout(()=>{timer=0;persist();},300);}
function leaving(e){flush();if(store.dirty().length){e.preventDefault();e.returnValue='';}}
const visibility=()=>{if(document.visibilityState==='hidden')flush();};
// A plain-text mirror measures native wrapping. Only visible lines get syntax
// spans; the textarea is the sole scroll owner for text, caret and selection.
let layoutCache=null,resizeObserver;
function geometry(){
 const field=$('ed-source'),mirror=$('ed-measure'),style=getComputedStyle(field),wrap=$('ed-wrap').checked;
 const fontProperties=['fontFamily','fontSize','fontStyle','fontWeight','fontStretch','lineHeight','tabSize','letterSpacing','fontKerning','fontVariantLigatures'];
 const signature=[field.clientWidth,wrap,...fontProperties.map(p=>style[p])].join('|');
 if(layoutCache?.value===field.value&&layoutCache.signature===signature)return layoutCache;
 mirror.style.width=field.clientWidth+'px';mirror.style.whiteSpace=wrap?'pre-wrap':'pre';
 for(const property of fontProperties)mirror.style[property]=style[property];
 mirror.textContent=field.value+'\u200b';
 const lines=field.value.split('\n'),starts=[];let at=0;for(const line of lines){starts.push(at);at+=line.length+1;}
 const range=document.createRange(),text=mirror.firstChild,scale=mirror.getBoundingClientRect().width/field.clientWidth||1;
 function top(index){range.setStart(text,starts[index]);range.setEnd(text,starts[index]+1);return range.getBoundingClientRect().top/scale;}
 const origin=top(0),padding=parseFloat(style.paddingTop),tops=new Map();
 const lineTop=index=>{if(!tops.has(index))tops.set(index,padding+top(index)-origin);return tops.get(index);};
 return layoutCache={value:field.value,signature,lines,starts,lineTop,lineHeight:parseFloat(style.lineHeight),padding};
}
function highlight(){
 if(!panel||!$('ed-source').clientWidth)return;
 const field=$('ed-source'),{lines,lineTop,lineHeight}=geometry();
 let lo=0,hi=lines.length;while(lo<hi){const mid=(lo+hi)>>1;if(lineTop(mid)<field.scrollTop)lo=mid+1;else hi=mid;}
 const start=Math.max(0,lo-2);let end=start+1;
 while(end<lines.length&&lineTop(end)<field.scrollTop+field.clientHeight+lineHeight*2)end++;
 const layer=$('ed-highlight');layer.style.width=field.clientWidth+'px';layer.style.height=field.clientHeight+'px';
 const content=document.createElement('div');content.className='ed-paint';content.dataset.firstLine=start+1;
 content.style.width=field.clientWidth+'px';content.style.top=(lineTop(start)-field.scrollTop)+'px';content.style.left=-field.scrollLeft+'px';
 content.style.whiteSpace=$('ed-wrap').checked?'pre-wrap':'pre';
 content.innerHTML=esc(lines.slice(start,end).join('\n')).replace(/(&lt;\/?[\w-]+|\b(?:const|let|function|return|if|else|var|class|import|export|async|await|def|from|True|False|None|with|for|in|and|or|not|try|except|raise)\b|#[\da-fA-F]{3,8}\b)/g,'<span class="syntax">$1</span>')+'\u200b';
 layer.replaceChildren(content);
 const gutter=$('ed-lines');gutter.style.height=field.clientHeight+'px';
 gutter.replaceChildren(...lines.slice(start,end).map((_,i)=>{const row=document.createElement('span');row.textContent=start+i+1;row.style.top=(lineTop(start+i)-field.scrollTop)+'px';return row;}));
}
function scrollToLine(index){const g=geometry();$('ed-source').scrollTop=Math.max(0,g.lineTop(Math.max(0,Math.min(index,g.lines.length-1)))-g.lineHeight*3);highlight();}
function repaint(){if(!paint)paint=requestAnimationFrame(()=>{paint=0;highlight();});}
function tabs(){const row=$('ed-tabs');row.replaceChildren();for(const b of store.files.values()){const tab=document.createElement('button');tab.textContent=b.path.split('/').at(-1)+(b.value!==b.base?' ●':'');tab.title=b.path;tab.setAttribute('aria-pressed',String(b.path===store.active));tab.onclick=()=>selectFile(b.path);row.append(tab);}notify();}
function remember(){const b=store.current();if(b){const f=$('ed-source');Object.assign(b,{scrollTop:f.scrollTop,scrollLeft:f.scrollLeft,start:f.selectionStart,end:f.selectionEnd});}}
function render(){const b=store.current();if(!b)return;$('ed-copy').disabled=false;const f=$('ed-source');f.value=b.value;f.readOnly=!b.editable;f.scrollTop=b.scrollTop||0;f.scrollLeft=b.scrollLeft||0;f.setSelectionRange(b.start||0,b.end||0);$('ed-path').textContent=b.path+(b.editable?'':' · READ ONLY');$('ed-language').textContent=b.language.toUpperCase()+' · complete file';$('ed-replace').disabled=$('ed-replace-all').disabled=!b.editable;$('ed-history').replaceChildren();for(const h of [...b.history].reverse())$('ed-history').append(new Option((h.revision?'Revision '+h.revision+' · ':'')+h.operation+' · '+new Date(h.saved_at).toLocaleString(),h.id));$('ed-restore').disabled=!b.editable||!b.history.length;msg(b.conflict?'Recovered source conflicts with current draft. Save is blocked; compare changes.':b.value!==b.base?'Unsaved changes retained.':'Revision '+b.revision+' · '+(b.restriction||'Authorised presentation source'));tabs();highlight();panel.dispatchEvent(new CustomEvent('studio-selection',{bubbles:true,detail:{path:b.path}}));}
function modified(){store.update($('ed-source').value);msg('Unsaved changes · '+store.dirty().length+' files');tabs();schedule();repaint();}
async function load(path,saved){const epoch=++selectionEpoch;remember();if(store.files.has(path)){store.active=path;render();schedule();return true;}const m=await request('/api/action',{action:'source-open',path});if(!m.complete)throw Error('Complete file required; excerpts cannot be edited.');const active=store.active;store.open(m,saved);if(epoch!==selectionEpoch){store.active=active;tabs();return false;}render();schedule();return true;}
async function act(fn){if(busy)return;busy=true;try{await fn();}catch(e){msg(e.message+' · pending buffers retained.');}finally{busy=false;notify();}}
async function saveAll(){const pending=store.dirty();if(!pending.length){msg('All files are saved.');return;}if(pending.some(b=>b.conflict||!b.editable))throw Error('Recovered or read-only buffer requires conflict review.');const snapshots=pending.map(b=>({path:b.path,expected_hash:b.hash,source:b.eol==='\r\n'?b.value.replace(/\n/g,'\r\n'):b.value}));flush();msg('Validating and saving '+snapshots.length+' files…');const result=await request('/api/action',{action:'editor-save-all',expected_revision:store.revision,files:snapshots});
 // New typing during Save remains above the persisted baseline.
 for(const row of snapshots){const b=store.files.get(row.path),opened=await request('/api/action',{action:'source-open',path:row.path});b.base=row.source.replace(/\r\n/g,'\n');b.hash=opened.hash;b.history=opened.history;b.conflict=false;if(b.value===row.source.replace(/\r\n/g,'\n')){b.undo=[];b.redo=[];b.bytes=0;}}store.revision=result.revision;for(const b of store.files.values())b.revision=result.revision;persist();tabs();panel.dispatchEvent(new CustomEvent('studio-saved',{bubbles:true,detail:{revision:result.revision,paths:result.paths}}));if(result.frame)await showFrame(result.frame);msg(result.preview_error||'Saved all files in draft revision '+result.revision+'.');
}
function find(){const f=$('ed-source'),term=$('ed-search').value;if(!term)return;let at=f.value.indexOf(term,f.selectionEnd);if(at<0)at=f.value.indexOf(term);if(at<0){msg('No match.');return;}f.focus();f.setSelectionRange(at,at+term.length);scrollToLine(f.value.slice(0,at).split('\n').length-1);repaint();}
export async function mount(target,transport,frameCallback,options={}){panel=target;panel.dataset.sourceEditor='true';layoutCache=null;sourceContext=null;request=transport;showFrame=frameCallback;key=options.recoveryKey?'studio-code-buffers:'+options.recoveryKey:'';store=new Buffers();panel.innerHTML=`<nav id="ed-tabs" class="ed-tabs" aria-label="Open source files"></nav><div class="ed-path"><b id="ed-path"></b><small id="ed-language"></small></div><div class="ed-tools"><button id="ed-copy-section" disabled>Copy Section</button><button id="ed-copy">Copy Full File</button><button id="ed-copy-related" disabled>Copy Related Source</button><button id="ed-select-all">Select All</button><label><input type="checkbox" id="ed-wrap">Wrap</label></div><div class="ed-find"><input id="ed-search" aria-label="Search source" placeholder="Find"><button id="ed-find">Find next</button><input id="ed-replacement" aria-label="Replacement source text" placeholder="Replace"><button id="ed-replace">Replace</button><button id="ed-replace-all">Replace all</button></div><p id="ed-status" role="status"></p><div id="ed-code"><div class="code-wrap"><pre id="ed-lines" aria-hidden="true"></pre><div class="code-stack"><pre id="ed-measure" aria-hidden="true"></pre><pre id="ed-highlight" aria-hidden="true"></pre><textarea id="ed-source" aria-label="Authorised source code" wrap="off" spellcheck="false"></textarea></div></div></div><section id="ed-history-panel" hidden><label>File-specific history<select id="ed-history"></select></label><button id="ed-restore">Load saved revision into buffer</button></section><pre id="ed-diff" hidden aria-label="Source changes"></pre>`;
 $('ed-copy-section').onclick=()=>act(()=>copyMapped('section'));$('ed-copy-related').onclick=()=>act(()=>copyMapped('related'));
 $('ed-source').oninput=modified;$('ed-source').onscroll=()=>{remember();highlight();};$('ed-source').onkeydown=e=>{if(e.key==='Tab'&&store.current()?.editable){e.preventDefault();e.currentTarget.setRangeText('  ',e.currentTarget.selectionStart,e.currentTarget.selectionEnd,'end');modified();}if((e.ctrlKey||e.metaKey)&&['z','y','s'].includes(e.key.toLowerCase())){e.preventDefault();command(e.key.toLowerCase()==='s'?'save':e.key.toLowerCase()==='y'||e.shiftKey?'redo':'undo').catch(error=>msg(error.message+' · buffers retained.'));}};
 $('ed-wrap').onchange=()=>{const on=$('ed-wrap').checked;$('ed-source').wrap=on?'soft':'off';$('ed-source').style.whiteSpace=$('ed-highlight').style.whiteSpace=on?'pre-wrap':'pre';repaint();};$('ed-find').onclick=find;$('ed-replace').onclick=()=>{const f=$('ed-source'),term=$('ed-search').value;if(!term)return;if(f.value.slice(f.selectionStart,f.selectionEnd)!==term)find();if(f.value.slice(f.selectionStart,f.selectionEnd)===term){f.setRangeText($('ed-replacement').value,f.selectionStart,f.selectionEnd,'end');modified();}};$('ed-replace-all').onclick=()=>{const term=$('ed-search').value;if(term){$('ed-source').value=$('ed-source').value.split(term).join($('ed-replacement').value);modified();}};
 $('ed-select-all').onclick=()=>{$('ed-source').focus();$('ed-source').select();};$('ed-copy').onclick=async()=>{if(sourceHasSecret(store.current().value)){msg('Potential credential detected. Copy Source export is blocked until it is removed.');return;}try{await navigator.clipboard.writeText(store.current().value);msg('Complete source copied. Review it before sharing.');}catch{$('ed-source').focus();$('ed-source').select();msg('Clipboard permission requires your gesture. Press Ctrl+C to copy the selected complete file.');}};
 $('ed-restore').onclick=()=>act(async()=>{const b=store.current(),result=await request('/api/action',{action:'source-history',path:b.path,id:$('ed-history').value,side:'after'});store.updateFile(b.path,result.source.replace(/\r\n/g,'\n'));render();schedule();});
 window.addEventListener('beforeunload',leaving);window.addEventListener('pagehide',flush);document.addEventListener('visibilitychange',visibility);
 let recovery;try{recovery=JSON.parse(localStorage.getItem(key)||'null');}catch{}for(const path of recovery?.dirty||[]){let saved;try{saved=JSON.parse(localStorage.getItem(key+':'+path)||'null');}catch{}if(saved){try{await load(path,saved);}catch(e){store.open({...saved,source:saved.base,editable:false,history:[],language:path.split('.').at(-1)},saved);store.current().conflict=true;msg('Recovered permission changed: '+e.message);}}}
 const listing=options.files||[],preferred=options.path||recovery?.active;
 if(preferred&&listing.some(f=>f.available&&f.path===preferred))await load(preferred);
 else if(store.current())render();
 else{msg('Select a verified source file.');$('ed-source').readOnly=true;$('ed-copy').disabled=true;}
 panel.hidden=false;resizeObserver=new ResizeObserver(()=>{layoutCache=null;repaint();});resizeObserver.observe($('ed-source'));notify();repaint();
 // Recovery tabs stay available, without loading unrelated files before navigation.
 for(const path of recovery?.tabs||[]){if(store.files.has(path)||!listing.some(f=>f.available&&f.path===path))continue;
  try{const m=await request('/api/action',{action:'source-open',path}),active=store.active;store.open(m);store.active=active;tabs();}catch{}}

}
export async function selectFile(path){try{return await load(path);}catch(e){msg(e.message);return false;}}
export async function selectComponent(name,location){
 if(!location?.path)return false;
 if(!await selectFile(location.path))return false;
 const b=store.current();
 if(b.value!==b.base){msg('Unsaved source retained. Mapping refers to the saved file; save before highlighting.');return true;}
 const f=$('ed-source'),lines=f.value.split('\n'),start=Math.max(1,location.line||1),end=Math.max(start,location.end_line||start);
 const at=lines.slice(0,start-1).reduce((n,line)=>n+line.length+1,0),length=lines.slice(start-1,end).join('\n').length;
 f.focus();f.setSelectionRange(at,at+length);scrollToLine(start-1);remember();repaint();
 msg(name+' · '+location.path+':'+start+(end!==start?'–'+end:'')+' · actual source');
 return true;
}
export function setContext(value){sourceContext=value;$('ed-copy-section').disabled=$('ed-copy-related').disabled=!value?.location;}
async function copyMapped(mode){
 if(!sourceContext?.location)throw Error('Inspect an element to select verified source.');
 if(store.dirty().some(b=>(sourceContext.related||[]).some(r=>r.path===b.path)))throw Error('Save related pending files before copying a mapped package, or use Copy Full File for the current buffer.');
 const result=await request('/api/action',{action:'source-copy',page:sourceContext.page,revision:sourceContext.revision,inspection:sourceContext,mode});
 const text=['Mapping: '+result.mapping,...result.sections.map(s=>'File: '+s.path+' ('+s.language+'; '+(s.complete_file?'complete file':'verified section')+')\n'+s.source)].join('\n\n');
 if(sourceHasSecret(text))throw Error('Potential credential detected; source copy blocked.');
 try{await navigator.clipboard.writeText(text);msg(mode==='section'?'Verified section copied with its file path.':'Complete related files copied with paths and languages.');}
 catch{let d=panel.querySelector('#ed-copy-package');if(!d){d=document.createElement('textarea');d.id='ed-copy-package';d.setAttribute('aria-label','Verified source package');d.readOnly=true;panel.append(d);}d.value=text;d.focus();d.select();msg('Press Ctrl+C to copy the selected verified package.');}
}
export async function canLeave(){return !busy&&(!store.dirty().length||flush());}
export async function command(name){if(name==='save')return act(saveAll);if(name==='history'){$('ed-history-panel').hidden=false;return;}if(name==='undo'||name==='redo'){if(store[name]()){render();schedule();}else if(name==='undo'&&store.current().editable&&store.current().value===store.current().base){const b=store.current(),undone=new Set(b.history.filter(h=>h.undo_of).map(h=>h.undo_of)),last=[...b.history].reverse().find(h=>h.operation!=='undo'&&!undone.has(h.id));if(last){const result=await request('/api/action',{action:'source-history',path:b.path,id:last.id,side:'before'});store.updateFile(b.path,result.source.replace(/\r\n/g,'\n'));render();schedule();msg('Saved file revision loaded into the buffer. Save Draft persists it with all pending files.');}else msg('No saved changes to undo.');}else msg('No local '+name+' history. Use file-specific saved History.');return;}if(name==='changes'){$('ed-diff').textContent=store.dirty().map(b=>{const p=patch(b.base,b.value);return '--- '+b.path+' (saved)\n+++ '+b.path+' (pending)\n-'+p.removed+'\n+'+p.inserted;}).join('\n').slice(0,100000)||'No pending source changes.';$('ed-diff').hidden=false;return;}
 if(name==='discard'){const d=document.createElement('dialog');d.innerHTML='<p>Discard all unsaved files in this draft?</p><button data-keep>Keep editing</button><button data-discard>Discard changes</button>';document.body.append(d);d.querySelector('[data-keep]').onclick=()=>d.remove();d.oncancel=e=>{e.preventDefault();d.remove();};d.querySelector('[data-discard]').onclick=()=>{for(const b of store.files.values()){b.value=b.base;b.undo=[];b.redo=[];}persist();render();d.remove();};d.showModal();return;}throw Error('Unsupported editor command');
}
export function dispose(){flush();resizeObserver?.disconnect();resizeObserver=null;layoutCache=null;cancelAnimationFrame(paint);paint=0;window.removeEventListener('beforeunload',leaving);window.removeEventListener('pagehide',flush);document.removeEventListener('visibilitychange',visibility);panel=null;store=new Buffers();}
