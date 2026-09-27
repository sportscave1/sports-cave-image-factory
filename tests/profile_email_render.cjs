// Repeatable production render-path benchmark with a counting DOM adapter.
// No browser-layout or network latency is claimed. Optional path profiles saved source.
const fs=require('node:fs'),vm=require('node:vm'),{performance}=require('node:perf_hooks');
const source=fs.readFileSync(process.argv[2]||'components/support_email/mail.js','utf8');
let writes=0;
const scroll={scrollTop:123}, pane={querySelector:()=>scroll,set innerHTML(value){writes++;}};
const node={querySelector:()=>scroll,classList:{toggle(){}},scrollTop:0};
const ctx={model:{configured:true,mailbox:'fixture',view:'mail',folder:'INBOX',threads:[],messages:[],settings:{},roles:{}},
 root:{querySelector(s){return s==='.reading'?pane:s==='.reading button:disabled'?{}:node;},querySelectorAll:()=>[],classList:{remove(){}}},
 readingStamp:'',selectionControlsDisabled:false,listStamp:'',folderStamp:'',toolbarStamp:'',
 busy:false,pending:'',pendingAction:'',queued:null,localDraft:null,collapsed:false,mobileReading:false,
 downloaded:'',focusSearch:false,historyTimer:null,views:{clear(){},put(){},get:()=>null},viewKey:()=>'',submitted:new Set(),
 window:{parent:{}},snapshot(){},inboxUnread(){},scheduleSentCheck(){},locked:()=>false,
 messages:()=>'<article><button disabled>Unavailable action</button><p>Fixture</p></article>',
 markSelection(){},wire(){},fit(){},esc:String,button:()=>'',folders:()=>'',conversations:()=>'',
 clearTimeout(){},JSON};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function paintReading('),source.indexOf('function compose(mode)')),ctx);
const next=ctx.model;
ctx.render(next);const initial=writes;
writes=0;const start=performance.now();
for(let i=0;i<1000;i++)ctx.render(next);
const result={initial_reading_replacements:initial,unchanged_renders:1000,
 unchanged_reading_replacements:writes,mean_render_ms:(performance.now()-start)/1000};
// Same cached selection needs one acknowledgement repaint to unlock its controls.
ctx.selectionControlsDisabled=true;writes=0;ctx.render(next);
result.selection_ack_replacements=writes;
vm.runInContext(source.slice(source.indexOf('function optimistic('),source.indexOf('function freeze(')),ctx);
writes=0;ctx.optimistic('open_thread',{thread_key:'uncached'});
result.uncached_selection_replacements=writes;
ctx.views.get=()=>({messages:[],active_message:'cached'});
writes=0;ctx.optimistic('open_thread',{thread_key:'cached'});
result.cached_selection_replacements=writes;
console.log(JSON.stringify(result,null,2));
if(!process.argv[2]){
 require('node:assert/strict').equal(result.initial_reading_replacements,1);
 require('node:assert/strict').equal(result.unchanged_reading_replacements,0);
 require('node:assert/strict').equal(result.selection_ack_replacements,1);
 require('node:assert/strict').equal(result.uncached_selection_replacements,1);
 require('node:assert/strict').equal(result.cached_selection_replacements,1);
}
