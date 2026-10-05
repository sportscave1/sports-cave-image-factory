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
    const emit = name => window.dispatchEvent(new CustomEvent(name, {detail: {
      client_preview_id: clientId, preview_id: saved ? saved.preview_id : null,
      product_id: String(hooks.metadata().product_id || '')
    }}));
    const event = async name => {
      emit(name);
      if (!saved) return;
      try {
        await fetch(`${API}/${saved.preview_id}/events`, {method:'POST', headers:{
          'Content-Type':'application/json', 'X-Wall-Preview-Token':saved.preview_token
        }, body:JSON.stringify({event_name:name, event_id:crypto.randomUUID()})});
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
      clientId=crypto.randomUUID(); saved=null; current=null; revision++;
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
    return {newWallPhoto,placementChanged,confirm,emailPreview,download,share,cartProperties,
      addedToCart:()=>event('WallPreviewAddedToCart')};
  };
})();
