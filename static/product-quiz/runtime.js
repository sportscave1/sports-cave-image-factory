/* Customer component. All HTML is built with textContent inside a shadow root. */
(() => {
  'use strict';
  const key=v=>String(v||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  function ranked(products,answers,rules){
    const sport=products.filter(p=>!answers.sport||p.sports.some(s=>key(s)===key(answers.sport)));
    const exact=sport.filter(p=>!answers.subject||p.subjects.some(s=>key(s)===key(answers.subject)));
    const preferred=exact.filter(p=>!answers.preference||p.preferences.some(s=>key(s)===key(answers.preference)));
    // Broader alternatives only relax the optional preference, never explicit identities.
    const rows=preferred.length?preferred:(rules.allow_broader?exact:[]);
    return [...new Map(rows.map(p=>[p.id,p])).values()].sort((a,b)=>(b.featured||0)-(a.featured||0)||a.id.localeCompare(b.id)).slice(0,12).map(p=>({...p,broader:!!answers.preference&&!p.preferences.some(s=>key(s)===key(answers.preference))}));
  }
  window.SportsCaveQuizRuntime={ranked,async mount({host,shadow,base,mode,launcher,manifest,config,preview}){
    const json=async(url,commerce=false)=>{const r=await fetch(url,{credentials:commerce?'same-origin':'omit',cache:'no-cache',signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error('Unavailable');return r.json();};
    const catalogue=preview?.catalogue||await json(base+'catalogue.json');
    if(!catalogue.sports||!Object.keys(catalogue.sports).length)throw Error('No eligible editions');
    if(!preview&&(!catalogue.generated_at||Date.now()-Date.parse(catalogue.generated_at)>7200000))throw Error('Catalogue freshness unavailable');
    const session=crypto.randomUUID();let seq=0,answers={},products=[],step=0,shown=new Set(),generation=0,round=0;
    const recorded=new Set();
    const source=mode==='button'?'collection':(/[?&]utm_(?:source|campaign)=/.test(location.search)?'campaign':'page');
    const browse=()=>{
      const collection=host.dataset.collection||Object.keys(config.collections).find(h=>config.collections[h]===answers.sport)||'all';
      return (window.Shopify?.routes?.root||'/')+'collections/'+(/^[a-z0-9-]+$/.test(collection)?collection:'all');
    };
    function event(type,question='',product=''){
      if(preview||window.Shopify?.customerPrivacy?.analyticsProcessingAllowed?.()!==true)return;
      const identity=round+':'+type+':'+question+':'+product+':'+JSON.stringify(answers);
      if(recorded.has(identity))return;
      recorded.add(identity);
      const payload={event_id:crypto.randomUUID(),session_id:session,version:manifest.version,type,step:question,source,product_id:product};
      const endpoint=manifest.analytics_endpoint;
      if(!endpoint)return;
      try{fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),credentials:'omit',keepalive:true}).catch(()=>{});}catch{}
    }
    const el=(tag,text,props={})=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;Object.assign(n,props);return n;};
    const css=el('style');css.textContent=`
      :host{--gold:${config.appearance.accent};--bg:${config.appearance.background};--ink:${config.appearance.text};display:block;color:var(--ink);font:15px/1.5 system-ui,sans-serif}
      *{box-sizing:border-box}dialog,.inline{color:var(--ink);background:var(--bg);border:1px solid #3b3428;border-radius:12px;padding:clamp(20px,4vw,40px);width:min(760px,calc(100vw - 24px));max-height:88dvh;overflow:auto;margin:auto}
      dialog::backdrop{background:#000b}.inline{width:100%;margin:20px auto;max-height:none}header{display:flex;align-items:start;justify-content:space-between;gap:16px}h1{font:500 clamp(26px,4vw,36px)/1.15 Georgia,serif;margin:10px 0}h2{font:500 25px/1.3 Georgia,serif;margin:24px 0 18px}p{color:#c6c0b6;margin:8px 0 18px}.eyebrow{color:var(--gold);font-size:10px;letter-spacing:.24em;text-transform:uppercase}button,a,input{font:inherit}button,a.action{border:1px solid #615136;border-radius:6px;padding:12px 16px;color:var(--ink);background:#181716;cursor:pointer;text-decoration:none}button:hover,a.action:hover{border-color:var(--gold);background:#272219}button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid var(--gold);outline-offset:3px}button:disabled{opacity:.5;cursor:wait}.close{padding:6px 10px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.grid button{text-align:left;min-height:54px}.tools{display:flex;gap:12px;margin-top:22px;flex-wrap:wrap}.tools button{border-color:transparent;background:transparent;padding:8px}.progress{height:2px;background:#383027;margin:22px 0}.progress span{display:block;height:100%;background:var(--gold)}input{width:100%;background:#161615;border:1px solid #615136;color:var(--ink);padding:12px;border-radius:6px;margin-bottom:12px}.results{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.card{min-width:0;border:1px solid #373127;border-radius:7px;padding:12px}.card img{width:100%;height:auto;align-self:start;aspect-ratio:4/5;object-fit:contain;background:#171615}.card h3{font-size:15px;font-weight:500;margin:12px 0 6px}.card p{font-size:12px;margin:6px 0 12px}.card a{display:block;text-align:center;padding:9px}.match{color:var(--gold);font-size:10px;text-transform:uppercase;letter-spacing:.1em}a{color:var(--gold)}.notice{font-size:12px}.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}@media(max-width:520px){.results{grid-template-columns:1fr}.card{display:grid;grid-template-columns:100px 1fr;gap:12px}.card img{grid-row:1/7}.grid{grid-template-columns:1fr 1fr}dialog{padding:22px 18px}h2{font-size:23px}}
    `;shadow.append(css);
    const panel=el(mode==='button'?'dialog':'section',undefined,{className:mode==='button'?'':'inline'});
    const headingId='quiz-'+crypto.randomUUID();panel.setAttribute('aria-labelledby',headingId);shadow.append(panel);
    const header=el('header'),intro=el('div');intro.append(el('div',preview?'Sports Cave · Local preview':'Sports Cave · The collection',{className:'eyebrow'}),el('h1',config.appearance.title,{id:headingId}),el('p',config.appearance.intro));header.append(intro);panel.append(header);
    if(mode==='button'){const close=el('button','✕',{type:'button',className:'close'});close.setAttribute('aria-label','Close quiz');close.onclick=()=>panel.close();header.append(close);panel.addEventListener('close',()=>{generation++;event('closed');launcher.focus();});}
    const progress=el('div',undefined,{className:'progress'}),bar=el('span');progress.setAttribute('role','progressbar');progress.setAttribute('aria-label','Quiz progress');progress.setAttribute('aria-valuemin','0');progress.setAttribute('aria-valuemax','100');progress.append(bar);panel.append(progress);
    const content=el('div');content.setAttribute('aria-live','polite');panel.append(content);
    let questions=[];
    const enabled=config.questions.filter(q=>q.enabled);
    function choices(q){
      let list=q.id==='sport'?Object.keys(catalogue.sports):[...new Set(products.filter(p=>!answers.subject||q.id==='subject'||p.subjects.some(s=>key(s)===key(answers.subject))).flatMap(p=>q.id==='subject'?p.subjects:p.preferences))];
      list=[...new Map(list.map(v=>[key(v),v])).values()].sort((a,b)=>a.localeCompare(b));
      const overrides=new Map(q.answers.map(a=>[key(a.value),a]));
      return list.map(v=>({value:v,label:overrides.get(key(v))?.label||v,enabled:overrides.get(key(v))?.enabled!==false})).filter(a=>a.enabled);
    }
    function activeQuestions(){return enabled.filter(q=>{
      if(q.id==='sport'||Object.hasOwn(answers,q.id))return true;
      const options=choices(q);if(options.length<2)return false;
      const pool=products.filter(p=>q.id==='subject'||!answers.subject||p.subjects.some(s=>key(s)===key(answers.subject)));
      const buckets=options.map(a=>pool.filter(p=>(q.id==='subject'?p.subjects:p.preferences).some(v=>key(v)===key(a.value))).map(p=>p.id).sort().join(','));
      return new Set(buckets).size>1;
    });}
    function controls(){const tools=el('div',undefined,{className:'tools'});
      if(step>0){const back=el('button','← Back',{type:'button'});back.onclick=()=>{generation++;step--;const q=questions[step];for(const later of enabled.slice(enabled.indexOf(q)))delete answers[later.id];render();};tools.append(back);}
      const restart=el('button','Start again',{type:'button'});restart.onclick=()=>{generation++;round++;answers={};step=0;products=[];shown=new Set();event('started');render();};tools.append(restart);content.append(tools);}
    function focus(){content.querySelector('h2')?.focus({preventScroll:true});}
    function render(){questions=activeQuestions();content.replaceChildren();const pct=Math.round(step/questions.length*100);bar.style.width=Math.min(100,pct)+'%';progress.setAttribute('aria-valuenow',String(Math.min(100,pct)));
      if(step>=questions.length){results();return;}
      const q=questions[step];const token=seq+':'+q.id;if(!shown.has(token)){shown.add(token);event('question',q.id);}
      content.append(el('div',`Question ${step+1} of ${questions.length}`,{className:'eyebrow'}),el('h2',q.label,{tabIndex:-1}));
      const grid=el('div',undefined,{className:'grid'}),options=choices(q);
      function draw(filter=''){grid.replaceChildren();const visible=options.filter(a=>key(a.label).includes(key(filter)));for(const a of visible){const b=el('button',a.label,{type:'button'});b.onclick=()=>select(q,a.value,b);grid.append(b);}if(q.id!=='sport'){const all=el('button','Show me all',{type:'button'});all.onclick=()=>select(q,'',all);grid.append(all);}if(!visible.length)grid.append(el('p','No choices match your search.'));}
      if(options.length>8){const search=el('input',undefined,{type:'search',placeholder:'Search choices'});search.setAttribute('aria-label','Search answer choices');search.oninput=()=>draw(search.value);content.append(search);}
      draw();content.append(grid);controls();focus();
    }
    async function select(q,value,button){const turn=++generation;button.disabled=true;answers[q.id]=value;for(const later of enabled.slice(enabled.indexOf(q)+1))delete answers[later.id];event('answered',q.id);
      try{if(q.id==='sport'){
        const path=catalogue.sports[value];if(!/^catalogue\/[a-f0-9]{24}\.json$/.test(path)&&!preview)throw Error('Invalid catalogue');
        products=preview?preview.products.filter(p=>p.sports.includes(value)):(await json(base+path)).products;
      }if(turn!==generation)return;seq++;step++;render();}catch{if(turn===generation){content.replaceChildren(el('h2','The quiz is temporarily unavailable',{tabIndex:-1}),el('a','Browse this collection',{href:browse()}));controls();focus();}}
    }
    async function results(){const turn=++generation;content.append(el('h2','Finding your editions…',{tabIndex:-1}));focus();
      try{
        const candidates=ranked(products,answers,config.rules);let valid=[];
        const root=window.Shopify?.routes?.root||'/';
        const currency=preview?'AUD':(await json(root+'cart.js',true)).currency;
        if(!/^[A-Z]{3}$/.test(currency))throw Error('Market unavailable');
        // At most twelve small same-origin product reads; three cards maximum.
        for(let offset=0;offset<candidates.length&&valid.length<config.rules.max_results;offset+=3){
          const batch=await Promise.all(candidates.slice(offset,offset+3).map(async p=>{try{
            const live=preview?{id:p.id.split('/').pop(),available:true,price:14900,featured_image:p.image,handle:p.handle}:await json(root+'products/'+encodeURIComponent(p.handle)+'.js',true);
            if(!preview){const prices=(live.variants||[]).filter(v=>v.available===true&&Number.isFinite(v.price)&&v.price>=0).map(v=>v.price);if(!prices.length)return null;live.price=Math.min(...prices);}
            if(String(live.id)!==p.id.split('/').pop()||live.available!==true||!Number.isFinite(live.price)||live.price<0)return null;
            return {...p,live,currency,url:root+'products/'+encodeURIComponent(p.handle)};
          }catch{return null;}}));valid.push(...batch.filter(Boolean));
        }
        if(turn!==generation)return;
        content.replaceChildren(el('h2',valid.length?'Your editions':'No exact match right now',{tabIndex:-1}));
        if(!valid.length)content.append(el('p','Try another selection, or explore the collection. We won’t fill your results with unrelated editions.'),el('a','Browse editions',{href:browse()}));
        const grid=el('div',undefined,{className:'results'});
        valid.slice(0,config.rules.max_results).forEach((p,i)=>{const card=el('article',undefined,{className:'card'});card.append(el('span',p.broader?'Broader preference':i?'Another edition':'Top match',{className:'match'}));
          let image=p.live.featured_image||p.image;if(image?.startsWith('//'))image='https:'+image;
          if(image){const u=new URL(image,location.origin);if(u.hostname==='cdn.shopify.com'||preview){if(u.hostname==='cdn.shopify.com')u.searchParams.set('width','400');card.append(el('img',undefined,{src:u.href,alt:p.title,loading:'lazy',width:200,height:250}));}}
          card.append(el('h3',p.title),el('p',[answers.sport,answers.subject,p.broader?'A different story within your selection':answers.preference].filter(Boolean).join(' · ')),el('div','From '+new Intl.NumberFormat(undefined,{style:'currency',currency:p.currency}).format(p.live.price/100)));
          const link=el('a',preview?'Preview edition':'View edition',{href:preview?'#':p.url,className:'action'});link.onclick=e=>{if(preview)e.preventDefault();else event('product_click','',p.id);};card.append(link);grid.append(card);
        });content.append(grid);if(preview)content.append(el('p','Synthetic preview prices and availability. No purchase or customer tracking.',{className:'notice'}));event('completed');controls();focus();
      }catch{if(turn===generation){content.replaceChildren(el('h2','Availability could not be verified',{tabIndex:-1}),el('p','Please browse the collection for current editions.'),el('a','Browse editions',{href:browse()}));controls();focus();}}
    }
    let hasOpened=false;
    function open(){if(mode==='button'&&!panel.open){panel.showModal();if(hasOpened)render();hasOpened=true;}}
    if(mode==='inline')launcher.hidden=true;
    open();event('started');
    const context=config.collections[host.dataset.collection];
    render();
    if(context&&catalogue.sports[context]){const q=questions[0];select(q,context,content.querySelector('button'));}
    return {open};
  }};
})();
