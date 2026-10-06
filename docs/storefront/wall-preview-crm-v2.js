/* Theme integration adapter, NOT a replacement visualizer. No pixels, gates or raw-photo uploads. */
(function () {
  'use strict';
  const API = 'https://sports-cave-image-factory.onrender.com/api/wall-previews';
  const sessionKey = 'sc-wall-preview-session-v2';
  let session = sessionStorage.getItem(sessionKey);
  if (!session) { session = crypto.randomUUID(); sessionStorage.setItem(sessionKey, session); }
  // This random session is a write capability. Never put it in dataLayer/share URLs/logs.
  window.SportsCaveWallPreviewCRM = function (hooks) {
    let clientId, saved = null, inFlight = null, current = null, revision = 0;
    let started=0,furthest=0,capture='',hasPhoto=false,lastFrame='',lastSize='';
    const once=new Set(),eventIds=new Map();
    const stages=['Started','PhotoReady','ArtworkDragged','Confirmed','AddedToCart','CheckoutStarted','Purchased'];
    function ensureJourney() {
      if(clientId)return;
      clientId=crypto.randomUUID();started=Date.now();
      const meta=hooks.metadata();lastFrame=String(meta.frame || '');lastSize=String(meta.size || '');
    }
    function track(name) {
      try {
        ensureJourney();
        if(['Started','ArtworkDragged','PhotoReady','Closed','CheckoutStarted'].includes(name.replace('WallPreview',''))) {
          if(once.has(name))return;once.add(name);
        }
        const stage=stages.indexOf(name.replace('WallPreview',''));furthest=Math.max(furthest,stage);
        const meta=hooks.metadata(), page=typeof location!=='undefined'?new URL(location.href):null;
        const allowed=['product_id','variant_id','product_handle','product_title','frame','size','unit'];
        const payload={event:name,event_id:crypto.randomUUID(),occurred_at:new Date().toISOString(),
          session_id:session,client_preview_id:clientId,preview_id:saved?saved.preview_id:null,
          elapsed_ms:Math.min(86400000,Math.max(0,Date.now()-started)),furthest_stage:stages[furthest],
          capture_source:capture,device_type:typeof matchMedia==='function'&&matchMedia('(pointer: coarse)').matches?'mobile':'desktop'};
        for(const key of allowed)payload[key]=String(meta[key] || '').slice(0,500);
        if(name==='WallPreviewConfirmed') {
          const key=name+':'+revision;
          if(eventIds.has(key))return;eventIds.set(key,payload.event_id);
        }
        if(page) {
          payload.page_url=page.origin+page.pathname;
          for(const key of ['utm_source','utm_medium','utm_campaign','utm_content','utm_term'])payload[key]=(page.searchParams.get(key)||'').slice(0,160);
        }
        if(typeof document!=='undefined' && document.referrer) {
          const ref=new URL(document.referrer);payload.referrer=ref.origin+ref.pathname;
        }
        // No session capability in DOM events/dataLayer. No photo or customer fields.
        const body=JSON.stringify(payload);
        if(name==='WallPreviewClosed' && typeof navigator!=='undefined' && navigator.sendBeacon) {
          if(navigator.sendBeacon(API+'/analytics/events',new Blob([body],{type:'application/json'})))return;
        }
        Promise.resolve(fetch(API+'/analytics/events',{method:'POST',headers:{'Content-Type':'application/json'},
          body,keepalive:true})).catch(()=>{});
      } catch (_) { /* Analytics cannot interrupt any visualizer action. */ }
    }
    const emit = name => { track(name); window.dispatchEvent(new CustomEvent(name, {detail: {
      client_preview_id: clientId, preview_id: saved ? saved.preview_id : null,
      product_id: String(hooks.metadata().product_id || '')
    }})); };
    const event = name => {
      emit(name);
      if (!saved) return;
      try {
        Promise.resolve(fetch(`${API}/${saved.preview_id}/events`, {method:'POST', headers:{
          'Content-Type':'application/json', 'X-Wall-Preview-Token':saved.preview_token
        }, body:JSON.stringify({event_name:name, event_id:crypto.randomUUID()})})).catch(()=>{});
      } catch (_) { /* Local download/share/ATC must remain usable. */ }
    };
    async function upload(blob, params) {
      for (let attempt=0; attempt<3; attempt++) {
        const controller=new AbortController(); const timeout=setTimeout(()=>controller.abort(),30000);
        try {
          const response=await fetch(API+'?'+params.toString(), {method:'POST',
            headers:{'Content-Type':'image/jpeg'},body:blob,signal:controller.signal});
          const body=await response.json();
          if (response.ok && body.ok) return body;
          if (response.status<500 && response.status!==429) throw Object.assign(new Error(body.error || 'Preview rejected'),{permanent:true});
        } catch (error) { if(error.permanent || attempt===2) throw error; }
        finally { clearTimeout(timeout); }
        await new Promise(resolve=>setTimeout(resolve,500*2**attempt));
      }
      throw new Error('Server archive unavailable');
    }
    function newWallPhoto() {
      if(hasPhoto){clientId=null;once.clear();eventIds.clear();furthest=0;}
      ensureJourney();hasPhoto=true;saved=null;current=null;revision++;
      hooks.showActions(false); hooks.showConfirm(true); emit('WallPreviewStarted');
    }
    function placementChanged() {
      revision++; hooks.showConfirm(true);
      // Called on drag end/size/frame change ONLY. Never uploads from this hook.
    }
    function confirm() {
      if(inFlight) return inFlight;
      const confirmedRevision=revision;
      const confirmedClient=clientId, previous=saved, meta=hooks.metadata();
      inFlight=(async()=>{
        // Both callbacks must canvas-reencode the FINISHED composite. Never pass the source photo.
        const archive=await hooks.compositeBlob(false);
        const branded=await hooks.compositeBlob(true);
        if(clientId!==confirmedClient || revision!==confirmedRevision) return null;
        current={archive,branded}; hooks.showActions(true); hooks.showConfirm(false);
        emit('WallPreviewConfirmed');
        const params=new URLSearchParams(Object.entries({...meta,client_preview_id:confirmedClient,session_id:session})
          .filter(([,value])=>value!==undefined && value!==null && value!==''));
        if(previous) params.set('preview_id',previous.preview_id);
        try {
          const result=await upload(archive,params);
          if(clientId!==confirmedClient) return null;
          saved=result;
          hooks.archiveStatus('Saved to Sports Cave');
        } catch (_) {
          if(clientId!==confirmedClient) return null;
          hooks.archiveStatus('Preview ready locally · server save failed. Confirm again to retry.');
          hooks.showConfirm(true); // Same client ID: retries never flood the inbox.
        }
        if(revision!==confirmedRevision) hooks.showConfirm(true);
        return saved;
      })().finally(()=>{inFlight=null;});
      return inFlight;
    }
    async function emailPreview(address) {
      if(!saved) throw new Error('Confirm and archive this preview first.');
      const email=address || hooks.metadata().customer_email; // ONE email field only if absent.
      const response=await fetch(`${API}/${saved.preview_id}/email`,{method:'POST',headers:{
        'Content-Type':'application/json','X-Wall-Preview-Token':saved.preview_token
      },body:JSON.stringify({email})});
      const body=await response.json();
      if(!response.ok || !body.ok) throw new Error(body.error || 'Email request unavailable');
      emit('WallPreviewEmailCaptured');
      return body.email_status; // queued != sent; UI must display the truthful state.
    }
    async function download() {
      if(!current) return;
      hooks.downloadBlob(current.branded); await event('WallPreviewDownloaded');
    }
    async function share() {
      if(!current) return;
      const url=saved && saved.share_url || hooks.metadata().product_url;
      const file=new File([current.branded],'sports-cave-wall-preview.jpg',{type:'image/jpeg'});
      if(navigator.canShare && navigator.canShare({files:[file]})) await navigator.share({files:[file],url});
      else if(navigator.share) await navigator.share({url});
      else await navigator.clipboard.writeText(url);
      await event('WallPreviewShared');
    }
    function cartProperties(existing={}) {
      return {...existing,_wall_preview_client_id:clientId,...(saved ? {_wall_preview_id:saved.preview_id} : {})};
    }
    // Call at existing action completion points. No pointermove listeners or UX changes.
    const opened=()=>{ensureJourney();if(!once.has('WallPreviewStarted'))emit('WallPreviewStarted');};
    const action=name=>{opened();emit('WallPreview'+name);};
    function changed(kind,value) {
      opened();value=String(value || '');
      if(kind==='Frame'){if(value===lastFrame)return;lastFrame=value;}
      else {if(value===lastSize)return;lastSize=value;}
      emit('WallPreview'+kind+'Changed');
    }
    return {newWallPhoto,placementChanged,confirm,emailPreview,download,share,cartProperties,opened,
      cameraOpened:()=>{capture='camera';action('CameraOpened');},
      galleryOpened:()=>{capture='upload';action('GalleryOpened');},
      photoCaptured:()=>{capture='camera';action('PhotoCaptured');},
      photoUploaded:()=>{capture='upload';action('PhotoUploaded');},
      photoReady:()=>action('PhotoReady'),
      dragCompleted:distance=>{if(Number(distance)>=3)action('ArtworkDragged');},
      frameChanged:value=>changed('Frame',value),sizeChanged:value=>changed('Size',value),
      scaleStarted:()=>action('ScaleStarted'),scaleCompleted:()=>action('ScaleCompleted'),
      quickPreviewUsed:()=>action('QuickPreviewUsed'),closed:()=>{if(clientId)emit('WallPreviewClosed');},
      // Call only after a verified checkout-start signal, never from a guessed button click.
      checkoutStarted:()=>action('CheckoutStarted'),
      addedToCart:()=>event('WallPreviewAddedToCart')};
  };
})();
