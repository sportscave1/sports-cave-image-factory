/* Published projections only. No identity cookies, provider tokens, or third-party dependencies. */
(()=>{
 if(customElements.get('sports-cave-reviews'))return;
 const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n};
 const safeUrl=value=>{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password?u.href:''}catch{return ''}};
 class Reviews extends HTMLElement{
  connectedCallback(){
   if(this.started)return;this.started=true;this.sequence=0;this.next=null;
   const endpoint=safeUrl(this.dataset.endpoint);if(!endpoint||new URL(endpoint).pathname!='/reviews/public')return;
   this.endpoint=endpoint;this.summary=this.querySelector('[data-summary]');this.error=this.querySelector('[data-error]');this.list=this.querySelector('[data-list]');this.more=this.querySelector('[data-more]');
   if(this.more)this.more.addEventListener('click',()=>this.load(true));
   if(this.dataset.mode!=='stars')this.controls();
   if('IntersectionObserver' in window){this.observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){this.observer.disconnect();this.load(false)}});this.observer.observe(this)}else this.load(false);
  }
  disconnectedCallback(){this.observer?.disconnect();this.controller?.abort();clearTimeout(this.debounce)}
  controls(){
   const host=this.querySelector('[data-controls]');this.sort=node('select');this.sort.setAttribute('aria-label','Sort reviews');
   for(const [value,label] of [['newest','Newest'],['highest','Highest rating'],['lowest','Lowest rating']]){const option=node('option',label);option.value=value;this.sort.append(option)}
   this.rating=node('select');this.rating.setAttribute('aria-label','Filter reviews by rating');
   for(let i=0;i<=5;i++){const o=node('option',i?i+' stars':'All ratings');o.value=i;this.rating.append(o)}
   host.append(this.sort,this.rating);this.sort.addEventListener('change',()=>{this.sortResolved=true;this.load(false)});this.rating.addEventListener('change',()=>this.load(false));
   if(this.dataset.mode==='all'){
    this.search=node('input');this.search.type='search';this.search.placeholder='Search reviews';this.search.maxLength=150;this.search.setAttribute('aria-label','Search reviews');host.prepend(this.search);
    this.search.addEventListener('input',()=>{clearTimeout(this.debounce);this.debounce=setTimeout(()=>this.load(false),300)});
    this.product=node('select');this.product.setAttribute('aria-label','Filter by product');const option=node('option','All products');option.value='';this.product.append(option);host.append(this.product);this.product.addEventListener('change',()=>this.load(false));
   }
  }
  async load(append){
   if(append&&this.next===null)return;
   const sequence=++this.sequence;this.controller?.abort();this.controller=new AbortController();
   const url=new URL(this.endpoint);if(this.dataset.product)url.searchParams.set('product',this.dataset.product);
   if(this.dataset.mode==='stars')url.searchParams.set('summary','1');
   if(this.sort&&this.sortResolved)url.searchParams.set('sort',this.sort.value);if(this.rating)url.searchParams.set('rating',this.rating.value);
   if(this.search)url.searchParams.set('search',this.search.value);if(this.product?.value)url.searchParams.set('product',this.product.value);
   url.searchParams.set('offset',append?this.next:0);if(this.more)this.more.disabled=true;
   try{
    const response=await fetch(url,{signal:this.controller.signal,credentials:'omit',referrerPolicy:'no-referrer'});if(!response.ok)throw Error('unavailable');const data=await response.json();
    if(sequence!==this.sequence||!this.isConnected)return;
    if(!data.summary||!Array.isArray(data.reviews))throw Error('incomplete');
    this.summary.textContent=data.summary.count?'★★★★★ '+Number(data.summary.average).toFixed(1)+' · '+data.summary.count+' reviews':'No published reviews yet';
    if(data.appearance&&/^#[0-9a-f]{6}$/i.test(data.appearance.accent))this.style.setProperty('--sc-review-accent',data.appearance.accent);
    this.dataset.density=data.appearance?.density==='comfortable'?'comfortable':'compact';
    if(this.sort&&!this.sortResolved){if(['newest','highest','lowest'].includes(data.appearance?.sort))this.sort.value=data.appearance.sort;this.sortResolved=true}
    if(this.list){if(!append)this.list.replaceChildren();for(const r of data.reviews)this.list.append(this.card(r))}
    if(this.product&&this.product.options.length===1)for(const p of data.products||[]){const option=node('option',p.product_title);option.value=p.product_id;this.product.append(option)}
    this.next=data.next_offset;if(this.more){this.more.hidden=this.next===null;this.more.disabled=false}this.error.replaceChildren();
   }catch(error){if(error.name==='AbortError'||sequence!==this.sequence)return;this.error.replaceChildren(node('span','Reviews could not refresh. '));const retry=node('button','Retry');retry.type='button';retry.addEventListener('click',()=>this.load(append));this.error.append(retry);if(this.more)this.more.disabled=false}
  }
  card(r){
   const article=node('article');
   if(this.dataset.mode==='all'){
    const product=node('div','', 'sc-review-product');const target=safeUrl(r.product_url);const label=node(target?'a':'span',r.product_title);if(target)label.href=target;
    const image=safeUrl(r.product_image);if(image){const img=node('img');img.src=image;img.alt=r.product_title||'';img.loading='lazy';img.width=48;img.height=48;product.append(img)}product.append(label);article.append(product);
   }
   const rating=Math.max(1,Math.min(5,Number(r.rating)||1));const stars=node('div','★'.repeat(rating)+'☆'.repeat(5-rating),'sc-review-stars');stars.setAttribute('aria-label',rating+' out of 5 stars');article.append(stars);
   if(r.title)article.append(node('h3',r.title));article.append(node('p',r.body));article.append(node('small',r.reviewer_name+(r.verified_purchase?' · Verified purchase':'')+(r.created_at?' · '+String(r.created_at).slice(0,10):'')));
   if(r.merchant_reply){const reply=node('blockquote');reply.append(node('strong','Sports Cave reply'),node('p',r.merchant_reply));article.append(reply)}return article;
  }
 }
 customElements.define('sports-cave-reviews',Reviews);
})();
