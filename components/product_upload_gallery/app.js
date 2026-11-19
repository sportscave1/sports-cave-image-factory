/* Preview-only rendering; original retrieval requires an explicit user action. */
(() => {
  'use strict';
  const root=document.getElementById('root');
  let signature='',epoch=0,controller=new AbortController(),height=0;
  const post=(type,extra={})=>parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
  const resize=()=>requestAnimationFrame(()=>{const next=Math.ceil(root.getBoundingClientRect().height);if(next!==height){height=next;post('streamlit:setFrameHeight',{height:next});}});
  const url=value=>value?new URL(value,location.origin).href:'';
  const active=version=>{if(version!==epoch||controller.signal.aborted)throw new Error('Selection changed. Reopen the current image.');};
  const button=(label,id)=>{const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-label',label);b.title=label+' to clipboard';b.id=id;return b;};
  const feedbackTimers=new Map();
  const feedbackTitle=(b,text)=>{b.title=text+(b.recorderPromptProof?'\nSports Cave prompt v1: '+b.recorderPromptProof:'');};
  const clearFeedback=b=>{clearTimeout(feedbackTimers.get(b));feedbackTimers.delete(b);};
  const clearAllFeedback=()=>{for(const timer of feedbackTimers.values())clearTimeout(timer);feedbackTimers.clear();};
  function copyFeedback(b,successMessage){
    const original=b.innerHTML,originalTitle=b.title,originalMinWidth=b.style.minWidth||'';
    return {
      begin(){clearFeedback(b);const width=b.getBoundingClientRect().width;if(width>0)b.style.minWidth=width+'px';b.textContent='Copying…';feedbackTitle(b,'Copying…');b.disabled=true;resize();},
      restore(){clearFeedback(b);b.innerHTML=original;feedbackTitle(b,originalTitle);b.style.minWidth=originalMinWidth;resize();},
      success(){clearFeedback(b);b.textContent='Copied';feedbackTitle(b,successMessage);feedbackTimers.set(b,setTimeout(()=>{feedbackTimers.delete(b);b.innerHTML=original;feedbackTitle(b,originalTitle);b.style.minWidth=originalMinWidth;resize();},2000));}
    };
  }
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
  const project='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project';
  const companionChannel='sports-cave-upload-companion-v1';
  const automaticAttempts=new Set();
  async function referenceFile(reference,version){
    if(!reference)return undefined;
    const address=new URL(reference.url,location.origin);
    if(address.origin!==location.origin || address.pathname!=='/api/product-uploads/asset' ||
       !reference.name?.endsWith('.webp') || /[/\\]/.test(reference.name) ||
       !Number.isInteger(reference.size) || reference.size<1 || reference.size>16*1024*1024 ||
       !/^[a-f0-9]{64}$/.test(reference.sha256||''))throw Error('Invalid original image attachment.');
    let response;
    for(let attempt=0;attempt<2;attempt++){
      try{
        response=await fetch(address.href,{credentials:'same-origin',cache:'no-store',signal:controller.signal});
        if(response.ok)break;
        if(response.status<500)break;
      }catch(error){if(controller.signal.aborted || attempt===1)throw error;}
    }
    if(!response?.ok)throw Error('The original image is unavailable. Reopen the saved mockups.');
    const bytes=new Uint8Array(await response.arrayBuffer());active(version);
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    if(bytes.length!==reference.size || hash!==reference.sha256)throw Error('The original image attachment failed verification.');
    const chunks=[];
    for(let i=0;i<bytes.length;i+=8192)chunks.push(String.fromCharCode(...bytes.subarray(i,i+8192)));
    const {url:unused,...metadata}=reference;
    return {...metadata,data:btoa(chunks.join(''))};
  }
  const supportsReference=version=>{
    const parts=String(version||'').split('.').map(Number);
    return parts[0]>1 || (parts[0]===1 && (parts[1]>3 || (parts[1]===3 && parts[2]>=3)));
  };
  function companionRequest(action, payload={}, timeout=1000){
    if(!globalThis.crypto?.randomUUID)return Promise.resolve(null);
    const id=crypto.randomUUID();
    return new Promise(resolve=>{
      const timer=setTimeout(()=>finish(null),timeout);
      function finish(result){
        clearTimeout(timer);
        window.removeEventListener('message',reply);
        resolve(result);
      }
      function reply(event){
        const message=event.data;
        if(event.source===window && event.origin===location.origin && message?.channel===companionChannel &&
           message.direction==='response' && message.id===id)finish(message.result);
      }
      window.addEventListener('message',reply);
      window.postMessage({channel:companionChannel,direction:'request',action,id,...payload},location.origin);
    });
  }
  function companionHealth(){
    if(window.frameElement)window.frameElement.id='sc-upload-companion-health';
    const status=document.createElement('div');
    status.setAttribute('role','status');
    status.textContent='Checking this Edge profile…';
    root.append(status);
    const pair=button('Pair this Edge profile','pairStaffQueue');
    pair.hidden=true;
    root.append(pair);
    pair.onclick=async()=>{
      pair.disabled=true;
      try{
        const response=await fetch('/api/staff-product-uploads/pair',{method:'POST',credentials:'same-origin'});
        const payload=await response.json();
        if(!response.ok)throw new Error(payload.error);
        const result=await companionRequest('pair',{token:payload.token},3000);
        if(!result?.paired)throw new Error('The companion did not accept pairing. Reload it in Edge and try again.');
        pair.textContent='Paired for staff uploads';
      }catch(error){
        status.textContent=error.message;
        pair.disabled=false;
      }
      resize();
    };
    const states={ready:'Connected · ready',opening:'Opening the ChatGPT project',sending:'Sending the prompt',
      submitted:'Submitted · ChatGPT accepted the prompt',failed:'Stopped before submission',uncertain:'Submission could not be verified'};
    const signal=controller.signal;
    async function refresh(){
      const report=await companionRequest('health');
      if(signal.aborted)return;
      pair.hidden=!(report?.version && (Number(report.version.split('.')[0])>1 ||
        Number(report.version.split('.')[1])>=1));
      const label=states[report?.state] || 'Upload Companion is not connected in this Edge profile.';
      const time=report?.time ? ' · '+new Date(report.time).toLocaleString() : '';
      status.textContent=label+(report?.version ? ' · '+report.version : '')+time+(report?.reason ? ' · '+report.reason : '');
      resize();
      setTimeout(()=>{if(!signal.aborted)void refresh();},5000);
    }
    void refresh();
  }
  function uploadAction(row,status,handoff,progress=null){
    if(!handoff)return;
    const upload=button('Upload','uploadToChat');
    upload.title=handoff.error || (handoff.prompt ? 'Copy the upload workflow and open ChatGPT' : 'Available once the five WebPs are saved in Dropbox');
    upload.disabled=!handoff.prompt || handoff.project!==project;
    row.append(upload);
    if(upload.disabled)return;
    const version=epoch;
    const signal=controller.signal;
    const autoKey=handoff.automatic && /^[a-f0-9]{64}$/.test(handoff.companion_id||'')
      ? 'sc-product-upload-saved:'+handoff.companion_id : '';
    function stage(value,label){
      if(progress)progress.value=value;
      status.textContent=label;
      resize();
    }
    function markDispatched(){
      if(autoKey){try{sessionStorage.setItem(autoKey,'dispatched');}catch{}}
    }
    async function watchSubmission(receipt,attempts=26){
      const result=await companionRequest('health',{receipt});
      if(signal.aborted || !result?.version)return;
      if(result.state==='submitted')stage(100,'ChatGPT accepted the full upload prompt in SC Mockups/Uploads.');
      else if(result.state==='failed' || result.state==='uncertain'){
        if(autoKey && result.state==='failed'){try{sessionStorage.removeItem(autoKey);}catch{}}
        stage(95,result.reason || 'ChatGPT submission needs attention.');
      }else if(attempts>1)setTimeout(()=>{if(!signal.aborted)void watchSubmission(receipt,attempts-1);},2500);
    }
    function projectLink(){
      const anchor=document.createElement('a');
      anchor.href=project;
      anchor.target='_blank';
      anchor.rel='noopener noreferrer';
      anchor.textContent='Open SC Mockups/Uploads';
      return anchor;
    }
    async function copyUploadPrompt(automatic){
      try{
        if(automatic && !parent.document.hasFocus())return false;
        const clipboard=automatic ? parent.navigator.clipboard : navigator.clipboard;
        await clipboard.writeText(handoff.prompt);
        return true;
      }catch{return false;}
    }
    async function start(automatic){
      if(upload.disabled || signal.aborted || !root.isConnected)return;
      upload.disabled=true;
      stage(90,'Mockups saved to Dropbox · Copying the prompt and opening ChatGPT…');
      try{
        const copying=copyUploadPrompt(automatic);
        if(handoff.companion_id){
          if(handoff.reference){
            const companion=await companionRequest('health');
            if(!supportsReference(companion?.version)){
              stage(95,'Update Edge Companion to 1.3.3 to attach the verified original image. The saved mockups are retained.');
              return;
            }
          }
          let receipt=handoff.companion_id;
          const reference=handoff.reference_companion_id;
          const savedAt=Date.parse(handoff.reference_saved_at);
          if(automatic && reference && reference!==receipt && Number.isFinite(savedAt)){
            const previous=await companionRequest('health',{receipt});
            active(version);
            if(previous?.state==='submitted' && previous.time>0 && previous.time<savedAt)receipt=reference;
          }
          const referenceFilePayload=await referenceFile(handoff.reference,version);
          const payload={receipt,prompt:handoff.prompt,staffJob:handoff.staff_job,reference:referenceFilePayload};
          let result=await companionRequest('start',payload,2200);
          if(automatic && !signal.aborted && !result)result=await companionRequest('start',payload,2200);
          if(result?.accepted && !result.busy)markDispatched();
          active(version);
          if(result?.accepted){
            if(result.busy)stage(95,'Edge Companion is busy. Use Upload when it finishes.');
            else{
              stage(100,'Upload sent to the Edge companion. Opening SC Mockups/Uploads.');
              void copying.then(copied=>{
                if(copied && !signal.aborted && status.textContent.startsWith('Upload sent')){
                  stage(100,'Full upload prompt copied. Edge Companion is opening SC Mockups/Uploads.');
                }
              });
              if(result.version)void watchSubmission(receipt);
            }
            return;
          }
        }
        if(handoff.staff_job){
          stage(95,'Waiting for the paired desktop to open the ChatGPT project.');
          return;
        }
        const popup=(!automatic || parent.document.hasFocus()) && window.open('about:blank','_blank');
        if(popup){
          popup.opener=null;
          popup.location.replace(project);
          markDispatched();
        }
        const copied=await copying;
        active(version);
        stage(popup ? 100 : 95,copied ? 'Upload prompt copied. ' : 'Use Upload to copy the prompt. ');
        if(popup && copied)status.textContent+='Paste it into the new project chat.';
        if(!popup){
          if(automatic)status.textContent+=handoff.prompt.length>131072
            ? 'Reload Upload Companion 1.0.6 in Personal Edge to send the full prompt to the ChatGPT Work composer. '
            : 'Edge did not open the project automatically. Check Developer → Upload Companion. ';
          status.append(projectLink());
          resize();
        }
      }catch(error){
        if(signal.aborted)return;
        status.textContent=handoff.reference && error?.message ? error.message : automatic ? 'Click Upload to copy the prompt and open ChatGPT.' :
          'Could not copy the upload prompt. Click Upload again to retry.';
      }finally{
        if(!signal.aborted){upload.disabled=false;resize();}
      }
    }
    upload.onclick=()=>start(false);
    if(!autoKey)return;
    queueMicrotask(()=>{
      if(signal.aborted || upload.disabled || automaticAttempts.has(autoKey))return;
      try{
        if(sessionStorage.getItem(autoKey)){
          if(progress)stage(100,'Mockups saved to Dropbox · ChatGPT handoff already started.');
          return;
        }
      }catch{}
      automaticAttempts.add(autoKey);
      void start(true);
    });
  }
  function actions(args){
    // Stable frame identity for the recorder across Streamlit reruns.
    if(window.frameElement)window.frameElement.id='sc-product-upload-copy';
    const progress=args.mode==='handoff' ? document.createElement('progress') : null;
    if(progress){
      progress.className='handoff-progress';progress.max=100;progress.value=85;
      progress.setAttribute('aria-label','Product upload progress');
      root.append(progress);
    }
    const row=document.createElement('div');row.className='actions';
    const copyImage=button('Copy black frame','copyImage'),copyPrompt=button('Copy prompt','copyPrompt');
    copyPrompt.setAttribute('aria-label','Copy Black Frame Prompt');
    copyPrompt.dataset.scCopy=String(args.prompt||'');
    copyPrompt.dataset.scCopyStatus='ready';
    const imageFeedback=copyFeedback(copyImage,'Image copied'),promptFeedback=copyFeedback(copyPrompt,'Prompt copied');
    copyImage.disabled=!args.original;row.append(copyImage,copyPrompt);root.append(row);
    // Prove the complete application-owned payload without exposing its text.
    // A stale digest must never annotate a newer product's button.
    if(typeof args.prompt==='string'&&args.prompt.length>0&&args.prompt.length<=1048576&&globalThis.crypto?.subtle){
      const version=epoch,bytes=new TextEncoder().encode(args.prompt);
      if(bytes.length<=1048576)crypto.subtle.digest('SHA-256',bytes).then(digest=>{
        if(version!==epoch||controller.signal.aborted)return;
        copyPrompt.recorderPromptProof=JSON.stringify({sha256:Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join(''),utf16_length:args.prompt.length,utf8_length:bytes.length});
        copyPrompt.setAttribute('aria-label','Copy Black Frame Prompt');
        feedbackTitle(copyPrompt,copyPrompt.title.split('\n')[0]);
      }).catch(()=>{}); // Manual Copy remains available; recorder refuses missing proof.
    }
    const status=document.createElement('div');status.id='status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');root.append(status);
    uploadAction(row,status,args.handoff,progress);
    copyPrompt.onclick=async()=>{
      if(copyPrompt.disabled)return;
      const version=epoch;copyPrompt.dataset.scCopyStatus='copying';promptFeedback.begin();status.textContent='';resize();
      try{if(!navigator.clipboard?.writeText)throw new Error();await navigator.clipboard.writeText(args.prompt);active(version);copyPrompt.dataset.scCopyStatus='copied';promptFeedback.success();}
      catch{if(version===epoch){copyPrompt.dataset.scCopyStatus='failed';promptFeedback.restore();status.textContent='Could not copy prompt. Allow clipboard access and retry.';}}
      finally{if(version===epoch){copyPrompt.disabled=false;resize();}}
    };
    copyImage.onclick=async()=>{
      if(copyImage.disabled)return;
      const version=epoch;imageFeedback.begin();status.textContent='';resize();
      try{
        if(!navigator.clipboard?.write||!window.ClipboardItem)throw new Error();
        await navigator.clipboard.write([new ClipboardItem({'image/png':png(args.original,version)})]);active(version);imageFeedback.success();
      }catch{if(version===epoch){imageFeedback.restore();status.textContent='Could not copy image. Allow clipboard access or open the original.';const a=link(args.original,'Black Framed');a.textContent='Open original';status.append(a);}}
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
    signature=next;epoch++;controller.abort();clearAllFeedback();controller=new AbortController();root.replaceChildren();
    if(args.mode==='actions' || args.mode==='handoff')actions(args);
    else if(args.mode==='companion-health')companionHealth();
    else if(args.mode==='queue-wake'){
      if(window.frameElement)window.frameElement.id='sc-upload-queue-wake';
      const status=document.createElement('div');status.id='status';status.role='status';root.append(status);
      status.textContent='Upload saved. Notifying the paired desktop…';
      const version=epoch;
      void companionRequest('wake',{},2000).then(result=>{
        if(version!==epoch)return;
        status.textContent=result?.paired
          ? 'Desktop notified. Starts when the upload queue is playing and its current upload finishes.'
          : 'Upload saved. The paired desktop will pick it up on its next check. If it stays waiting, check Upload Companion is connected and the upload queue is playing.';
        resize();
      });
    }
    else{const container=document.createElement('div');container.className=args.mode==='gallery'?'gallery':'single-preview';container.setAttribute('aria-label',args.mode==='gallery'?'Generated mockup previews':'Lifestyle mockup preview');
      for(const item of args.items||[])container.append(image(item,args.mode==='gallery'));root.append(container);
    }
    resize();
  });
  addEventListener('pagehide',()=>{epoch++;controller.abort();clearAllFeedback();});
  new ResizeObserver(resize).observe(root);
  post('streamlit:componentReady',{apiVersion:1});
})();
