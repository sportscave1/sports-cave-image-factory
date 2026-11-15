/* Mapping opens the existing Edition Ops workspace; no PSD side effects. */
'use strict';
window.ProductUploadMapping = ({request, getRow}) => {
  const $ = id => document.getElementById(id);
  let key='', visible=false, serial=0, busy=false;
  function paint(){ $('map').textContent='Mapping'; $('map').disabled=!visible||busy; $('mapping-refresh').disabled=!visible||busy; }
  async function lookup(navigate=false){
    if(!key||!visible||busy)return;
    const id=key, version=serial; busy=true; paint();
    $('mapping-status').textContent='Checking Edition Ops…';
    try{
      const result=await request('mapping-status?id='+encodeURIComponent(id));
      if(id!==key||version!==serial)return;
      $('mapping-status').textContent=result.mapping.state;
      $('mapping-reason').textContent=result.mapping.reason;
      if(navigate){
        const url=new URL(result.mapping.url,window.location.origin);
        if(url.origin!==window.location.origin||url.searchParams.get('page')!=='edition_ops')throw new Error('Edition Ops navigation unavailable.');
        // Same top-level route pattern as the existing manual mapping link.
        const link=document.createElement('a');link.href=url.href;link.target='_top';link.click();
      }
    }catch(error){if(id===key&&version===serial){$('mapping-status').textContent='Status unavailable';$('mapping-reason').textContent=error.message;}}
    finally{if(version===serial){busy=false;paint();}}
  }
  function reset(){serial++;busy=false;key='';visible=false;$('mapping-status').textContent='Open Edition Ops to attach a PSD';$('mapping-reason').textContent='';paint();}
  $('map').onclick=()=>lookup(true);$('mapping-refresh').onclick=()=>lookup(false);
  return {reset,dispose:reset,clearRecoveryURL(){},sync(row,enabled){
    if(row?.id!==key){reset();key=row?.id||'';}
    visible=!!enabled&&!!key;paint();
  }};
};
