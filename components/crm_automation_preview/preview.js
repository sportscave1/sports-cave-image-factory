// Keep the physical iframe mounted across Streamlit fragment/app reruns.
const email=document.getElementById('email');
let digest=null,timer=null,tick=0;
let scope=null,meter=null;
const size=document.createElement('div');document.body.append(size);
const updateSize=event=>{
 if(scope===event.detail.scope&&meter!==event.detail.html){size.innerHTML=event.detail.html;meter=event.detail.html;}
};
parent.addEventListener('sc-automation-preview-size',updateSize);
addEventListener('pagehide',()=>{clearTimeout(timer);parent.removeEventListener('sc-automation-preview-size',updateSize);});
window.previewUpdates=0;window.previewLoads=0;
const send=(type,data={})=>parent.postMessage({isStreamlitMessage:true,type,...data},'*');
email.addEventListener('load',()=>window.previewLoads++);
addEventListener('message',event=>{
 if(event.source!==parent||event.data.type!=='streamlit:render')return;
 const args=event.data.args;clearTimeout(timer);
 if(args.kind==='size'){
  scope=args.scope;email.style.display='none';
  if(meter!==args.meter){size.innerHTML=args.meter;meter=args.meter;}
  send('streamlit:setFrameHeight',{height:36});return;
 }
 parent.dispatchEvent(new CustomEvent('sc-automation-preview-size',{detail:{scope:args.scope,html:args.meter}}));
 const height=Math.max(340,Math.min(680,parent.innerHeight-240));
 document.body.style.height=height+'px';email.style.width=args.width+'px';
 send('streamlit:setFrameHeight',{height});
 if(digest!==args.digest){
  const scroll=email.contentWindow?.scrollY||0;
  email.addEventListener('load',()=>email.contentWindow?.scrollTo(0,scroll),{once:true});
  email.srcdoc=args.html;digest=args.digest;window.previewUpdates++;
 }
 if(args.pending)timer=setTimeout(function poll(){
  send('streamlit:setComponentValue',{value:++tick,dataType:'json'});
  timer=setTimeout(poll,1000);
 },1000);
});
send('streamlit:componentReady',{apiVersion:1});
