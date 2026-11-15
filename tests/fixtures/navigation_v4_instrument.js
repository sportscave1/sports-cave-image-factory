// Test-only browser timing, installed before production controller listeners.
// Results are exposed as DOM data; no production instrumentation is added.
(function () {
  const w=window.parent, d=w.document;
  w.SCNavigationBenchmark?.destroy();
  let output=d.getElementById('navigation-v4-metrics');
  if(!output){
    output=d.createElement('div');output.id='navigation-v4-metrics';output.hidden=true;
    output.dataset.samples='[]';d.body.appendChild(output);
  }
  const samples=JSON.parse(output.dataset.samples||'[]');
  let pending=JSON.parse(output.dataset.pending||'null');
  const listeners=new w.AbortController();
  const flush=()=>{output.dataset.samples=JSON.stringify(samples);output.dataset.pending=JSON.stringify(pending);};
  d.addEventListener('click', e=>{
    const button=e.target.closest?.('section[data-testid="stSidebar"] button');
    if (!button) return;
    if(pending) {pending.superseded=true; samples.push(pending);flush();}
    pending={label:button.textContent.trim(),started:w.performance.now(),
      expected:button.dataset.scRouteKey||'',
      initial_route:d.getElementById('sports-cave-os-top-bar')?.dataset.currentRouteKey||'',
      initial_renders:Number(d.getElementById('navigation-v4-content')?.dataset.renders||0),
      initial_epoch:Number(d.getElementById('sports-cave-os-top-bar')?.dataset.navigationEpoch||0)};
    let group=button, match=null;
    while(group && !(match=String(group.className).match(/st-key-sidebar-disclosure-([a-z]+)-(open|closed)/)))group=group.parentElement;
    if(match){pending.group=match[1];pending.initial_group_class=group.className;}
    flush();
  },{capture:true,signal:listeners.signal});
  const observe=()=>{
    if(!pending)return;
    const root=d.getElementById('sports-cave-os-top-bar');
    const content=d.getElementById('navigation-v4-content');
    const now=w.performance.now();
    if(pending.group && pending.expected===pending.initial_route){
      const group=d.querySelector('[class*="st-key-sidebar-disclosure-'+pending.group+'-"]');
      if(group && group.className!==pending.initial_group_class && Number(content?.dataset.renders||0)===pending.initial_renders){
        pending.disclosure_ms=now-pending.started;samples.push(pending);pending=null;flush();return;
      }
    }
    if(d.body.classList.contains('sc-navigation-pending') && pending.feedback_ms===undefined){
      pending.feedback_ms=now-pending.started;
      w.requestAnimationFrame(()=>{if(pending){pending.feedback_frame_ms=w.performance.now()-pending.started;flush();}});
    }
    const accepted=root?.dataset.currentRouteKey;
    if(accepted && accepted===pending.expected &&
       Number(root?.dataset.navigationEpoch||0)>pending.initial_epoch && pending.accepted_ms===undefined)
      pending.accepted_ms=now-pending.started;
    if(content && content.dataset.route===root?.dataset.currentRouteKey){
      const renders=Number(content.dataset.renders||0);
      if(renders>pending.initial_renders && (!pending.expected || content.dataset.route===pending.expected)){
        pending.first_content_ms=now-pending.started;
        pending.server_ms=Number(content.dataset.serverMs);
        pending.sidebar_ms=Number(content.dataset.sidebarMs);
        pending.route=content.dataset.route;
        output.dataset.lastRenders=String(renders);
      }
    }
    if(pending.first_content_ms!==undefined && root?.dataset.lastNavigationStatus==='ready'
       && !d.body.classList.contains('sc-navigation-pending')){
      pending.ready_ms=now-pending.started;
      samples.push(pending);pending=null;flush();
    }
    flush();
  };
  const observer=new w.MutationObserver(observe);
  observer.observe(d.body,{subtree:true,childList:true,attributes:true,
    attributeFilter:['class','data-current-route-key','data-accepted-route-key',
      'data-last-navigation-status','data-navigation-epoch','data-pending-route-key','data-route','data-renders']});
  w.SCNavigationBenchmark={destroy(){listeners.abort();observer.disconnect();}};
})();
