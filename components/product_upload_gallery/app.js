/* Preview-only rendering; original retrieval requires an explicit user action. */
(() => {
  'use strict';
  const root=document.getElementById('root');
  let signature='',epoch=0,controller=new AbortController(),height=0;
  const post=(type,extra={})=>parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
  const resize=()=>requestAnimationFrame(()=>{const next=Math.ceil(root.getBoundingClientRect().height);if(next!==height){height=next;post('streamlit:setFrameHeight',{height:next});}});
  const url=value=>value?new URL(value,location.origin).href:'';
  const active=version=>{if(version!==epoch||controller.signal.aborted)throw new Error('Selection changed. Reopen the current image.');};
  const button=(label,id)=>{const b=document.createElement('button');b.textContent=label;b.id=id;return b;};
  function link(original,label){const a=document.createElement('a');a.href=url(original);a.target='_blank';a.rel='noopener';a.setAttribute('aria-label','Open '+label+' full-resolution original');return a;}
  function image(item,compact){
    const wrapper=document.createElement('div');wrapper.className=compact?'preview':'single';
    if(item.preview){
      const a=item.original?link(item.original,item.label):document.createElement('span');
      const img=document.createElement('img');img.src=item.preview;img.alt=item.label;img.addEventListener('load',resize);a.append(img);wrapper.append(a);
    }
    const label=document.createElement(compact?'span':'small');label.className='label';label.textContent=compact?item.label:'Preview shown · click to open original';wrapper.append(label);return wrapper;
  }
  async function png(original,version){
    const response=await fetch(url(original),{credentials:'same-origin',cache:'no-store',signal:controller.signal});
    if(!response.ok)throw new Error('Original unavailable.');
    const blob=await response.blob();active(version);
    if(blob.type==='image/png')return blob;
    if(!blob.type.startsWith('image/'))throw new Error('Original unavailable.');
    const bitmap=await createImageBitmap(blob);
    try{
      active(version);const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;
      canvas.getContext('2d').drawImage(bitmap,0,0);
      const result=await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error('PNG conversion failed.')),'image/png'));
      active(version);return result;
    }finally{bitmap.close();}
  }
  function actions(args){
    const row=document.createElement('div');row.className='actions';
    const copyImage=button('Copy black frame','copyImage'),copyPrompt=button('Copy prompt','copyPrompt');
    copyImage.disabled=!args.original;row.append(copyImage,copyPrompt);root.append(row);
    const status=document.createElement('div');status.id='status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');root.append(status);
    copyPrompt.onclick=async()=>{
      const version=epoch;copyPrompt.textContent='Copying…';copyPrompt.disabled=true;status.textContent='';resize();
      try{if(!navigator.clipboard?.writeText)throw new Error();await navigator.clipboard.writeText(args.prompt);active(version);copyPrompt.textContent='Copied';}
      catch{if(version===epoch){copyPrompt.textContent='Copy prompt';status.textContent='Could not copy prompt. Allow clipboard access and retry.';}}
      finally{if(version===epoch){copyPrompt.disabled=false;resize();}}
    };
    copyImage.onclick=async()=>{
      if(copyImage.disabled)return;
      const version=epoch;copyImage.disabled=true;copyImage.textContent='Copying…';status.textContent='';resize();
      try{
        if(!navigator.clipboard?.write||!window.ClipboardItem)throw new Error();
        await navigator.clipboard.write([new ClipboardItem({'image/png':png(args.original,version)})]);active(version);copyImage.textContent='Copied';
      }catch{if(version===epoch){copyImage.textContent='Copy black frame';status.textContent='Could not copy image. Allow clipboard access or open the original.';const a=link(args.original,'Black Framed');a.textContent='Open original';status.append(a);}}
      finally{if(version===epoch){copyImage.disabled=false;resize();}}
    };
  }
  addEventListener('message',event=>{
    if(event.source!==parent||event.data.type!=='streamlit:render')return;
    const args=event.data.args||{},theme=event.data.theme||{};
    if(theme.textColor)document.body.style.setProperty('--text',theme.textColor);
    if(theme.backgroundColor)document.body.style.setProperty('--background',theme.backgroundColor);
    if(theme.font)document.body.style.setProperty('--font',theme.font);
    const next=JSON.stringify(args);if(signature===next){resize();return;}
    signature=next;epoch++;controller.abort();controller=new AbortController();root.replaceChildren();
    if(args.mode==='actions')actions(args);
    else{const container=document.createElement('div');container.className=args.mode==='gallery'?'gallery':'single-preview';container.setAttribute('aria-label',args.mode==='gallery'?'Generated mockup previews':'Lifestyle mockup preview');
      for(const item of args.items||[])container.append(image(item,args.mode==='gallery'));root.append(container);}
    resize();
  });
  addEventListener('pagehide',()=>{epoch++;controller.abort();});
  new ResizeObserver(resize).observe(root);
  post('streamlit:componentReady',{apiVersion:1});
})();
