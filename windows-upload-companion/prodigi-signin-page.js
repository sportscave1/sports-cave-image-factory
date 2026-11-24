'use strict';
(()=>{
  if(window.top!==window)return;
  const email='hello@sportscave.com.au';
  let attempted=false,running=false;
  const visible=e=>Boolean(e&&e.getClientRects().length&&!e.disabled);
  function loginMatches(expected){
    try{const here=new URL(location.href),order=new URL(expected);
      return order.origin==='https://dashboard.prodigi.com'&&/^\/orders\/[A-Za-z0-9-]{1,100}\/detail$/.test(order.pathname)&&
        !order.search&&!order.hash&&!order.username&&!order.password&&here.origin===order.origin&&here.pathname==='/login'&&
        !here.hash&&!here.username&&!here.password&&here.searchParams.getAll('redirect').length===1&&
        Array.from(here.searchParams.keys()).every(k=>k==='redirect')&&here.searchParams.get('redirect')===order.pathname;
    }catch{return false;}
  }
  function controls(){
    // Refuse registration, MFA and changed/ambiguous forms. Never click Reset,
    // Show, a CAPTCHA or any button outside the canonical existing-account form.
    const main=document.querySelector('main');
    if(!main||document.querySelector('iframe[src*="captcha" i],iframe[title*="captcha" i],[data-sitekey],input[autocomplete="one-time-code"]')||
      /create (?:an )?account|register your|verification code|one.time (?:code|password)|captcha/i.test(main.innerText))return {step:'manual'};
    const inputs=Array.from(main.querySelectorAll('input')).filter(visible);
    const passwords=inputs.filter(e=>e.type==='password'&&e.id==='password'&&e.name==='password');
    const emails=inputs.filter(e=>e.type==='email'&&e.id==='email'&&e.name==='email');
    const field=passwords.length===1&&emails.length===0?passwords[0]:emails.length===1&&passwords.length===0?emails[0]:null;
    if(!field||inputs.some(e=>e!==field&&e.type!=='hidden'&&e.type!=='checkbox'))return {step:'manual'};
    const form=field.form;
    if(!form||form.target&&form.target!=='_self')return {step:'manual'};
    const action=new URL(form.getAttribute('action')||location.href,location.href);
    if(action.href!==location.href)return {step:'manual'};
    const buttons=Array.from(form.querySelectorAll('button[type="submit"]')).filter(e=>e.getClientRects().length&&e.textContent.trim()==='Continue');
    if(buttons.length!==1)return {step:'manual'};
    if(passwords.length&&!Array.from(main.querySelectorAll('[title]')).some(e=>e.getAttribute('title')===email)&&
      !main.innerText.includes(email))return {step:'manual'};
    return {step:passwords.length?'password':'email',field,button:buttons[0]};
  }
  function notice(){
    let banner=document.getElementById('sports-cave-signin-alert');
    if(!banner){banner=document.createElement('div');banner.id='sports-cave-signin-alert';banner.setAttribute('role','alert');
      banner.style.cssText='position:fixed;top:8px;left:8px;right:8px;z-index:2147483647;padding:14px 18px;background:#fff3cd;color:#533f03;border:2px solid #b45309;border-radius:8px;font:15px/1.5 system-ui;';
      banner.textContent='Sports Cave: Prodigi sign-in needed. Use hello@sportscave.com.au. Waiting orders will resume automatically after sign-in. If Prodigi asks for a code or verification, complete it here.';
      document.body.appendChild(banner);
    }
  }
  function fill(field,value){
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,value);
    field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}));
  }
  async function signIn(message){
    if(running||attempted||!loginMatches(message.order_url)||message.username!==email||typeof message.password!=='string'||!message.password)return {submitted:false};
    running=true;attempted=true;
    try{
      notice();
      let control=controls();
      if(control.step==='email'){
        // Do not overwrite a different account or partially completed manual login.
        if(control.field.value&&control.field.value.trim().toLowerCase()!==email)return {manual:true};
        fill(control.field,email);
        await new Promise(r=>setTimeout(r,100));control=controls();
        if(!loginMatches(message.order_url)||control.step!=='email'||!visible(control.button))return {manual:true};
        control.button.click();
        const until=Date.now()+15000;
        do{await new Promise(r=>setTimeout(r,200));control=controls();if(control.step==='password')break;}while(Date.now()<until&&loginMatches(message.order_url));
      }
      if(!loginMatches(message.order_url)||control.step!=='password'||control.field.value)return {manual:true};
      fill(control.field,message.password);
      await new Promise(r=>setTimeout(r,100));control=controls();
      if(!loginMatches(message.order_url)||control.step!=='password'||!visible(control.button))return {manual:true};
      control.button.click();
      return {submitted:true};
    }finally{message.password='';running=false;}
  }
  chrome.runtime.onMessage.addListener((message,sender,reply)=>{
    if(sender.id!==chrome.runtime.id||!loginMatches(message?.order_url))return;
    if(message.type==='prodigi:signin:notice'){notice();reply({step:controls().step});return;}
    if(message.type==='prodigi:signin:fill'){
      signIn(message).then(reply,()=>reply({manual:true}));return true;
    }
  });
  if(location.origin==='https://dashboard.prodigi.com'&&/^\/orders\/[A-Za-z0-9-]{1,100}\/detail$/.test(location.pathname)){
    let probes=0;
    const timer=setInterval(()=>{
      if(++probes>60){clearInterval(timer);return;}
      if(typeof prodigiOrderPageReady==='function'&&prodigiOrderPageReady(document.readyState,location.pathname,
        Array.from(document.querySelectorAll('main h1')).map(e=>(e.textContent||'').trim()))){
        clearInterval(timer);void chrome.runtime.sendMessage({type:'prodigi:signin:ready'}).catch(()=>{});
      }
    },1000);
  }
})();
