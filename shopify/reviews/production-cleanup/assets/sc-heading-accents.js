(() => {
 const targets=[
 ['.sc-legacy--desktop .sc-legacy__story p:first-child strong',null],
 ['#sc-collector-videos-title','motion'],
 ['#sc-collector-faq-title','Questions']
 ];
 const decorate=()=>{
  targets.forEach(([selector,keyword])=>{
   const heading=document.querySelector(selector);
   if(!heading || heading.querySelector('.sc-heading-keyword')) return;
   const words=heading.textContent.match(/[\p{L}\p{N}’'-]+/gu);
   const word=keyword || words?.at(-1);
   if(!word) return;
   const walker=document.createTreeWalker(heading,NodeFilter.SHOW_TEXT);
   let node;
   while(node=walker.nextNode()){
    const index=node.textContent.toLowerCase().lastIndexOf(word.toLowerCase());
    if(index<0) continue;
    const range=document.createRange();range.setStart(node,index);range.setEnd(node,index+word.length);
    const span=document.createElement('span');span.className='sc-heading-keyword';range.surroundContents(span);break;
   }
  });
 };
 let timer;
 const observer=new MutationObserver(records=>{
   if(!records.some(record=>[...record.addedNodes].some(node=>node.nodeType===1 &&
     targets.some(([selector])=>node.matches?.(selector)||node.querySelector?.(selector)))))return;
   clearTimeout(timer);timer=setTimeout(decorate,80);
 });
 observer.observe(document.getElementById('content')||document.body,{childList:true,subtree:true});
 decorate();
})();
/* Share measured desktop gallery bounds with the floating header. */
(() => {
 const form=document.querySelector('product-form.js-product');
 if(!form)return;
 const root=document.documentElement;
 let frame;
 const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(update);};
 const set=(name,value)=>{if(root.style.getPropertyValue(name)!==value)root.style.setProperty(name,value);};
 function update(){
  if(innerWidth<990)return;
  const top=form.getBoundingClientRect().top+scrollY;
  const preview=document.getElementById('PBarNextFrameWrapper')?.getBoundingClientRect();
  const inset=preview?.height && preview.top>root.clientHeight/2?Math.max(0,root.clientHeight-preview.top):0;
  set('--sc-product-available-height',Math.max(1,root.clientHeight-top-inset-24).toFixed(2)+'px');
  set('--sc-product-edge',getComputedStyle(form).paddingLeft);
 }
 const observer=new ResizeObserver(schedule);
 observer.observe(form);
 document.querySelectorAll('.shopify-section-group-header-group,.scx-left:has(.scx-breadcrumbs)').forEach(e=>observer.observe(e));
 addEventListener('resize',schedule,{passive:true});
 addEventListener('load',schedule,{once:true});
 document.fonts?.ready.then(schedule);
 schedule();
})();
