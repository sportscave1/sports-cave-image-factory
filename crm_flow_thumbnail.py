"""Lazy, inert email miniatures. No recipient/provider lookups or editor mounts."""
from functools import lru_cache
from html import escape
from html.parser import HTMLParser
import json,re,hashlib
from urllib.parse import urlsplit
import streamlit as st

class InertEmail(HTMLParser):
    tags={'div','span','p','table','tbody','thead','tr','td','th','img','br','strong','b','em','i','h1','h2','h3','hr','ul','ol','li','a','center'}
    styles={'color','background','background-color','font-family','font-size','font-weight','font-style','line-height','text-align','text-decoration','width','height','max-width','min-width','padding','padding-top','padding-bottom','padding-left','padding-right','margin','margin-top','margin-bottom','border','border-top','border-bottom','border-radius','border-collapse','vertical-align','display','letter-spacing'}
    def __init__(self):super().__init__(convert_charrefs=True);self.out=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','iframe','object','svg','form','head'):self.skip+=1;return
        if self.skip or tag not in self.tags:return
        clean=[]
        for k,v in attrs:
            if not v:continue
            if k=='style':
                declarations=[]
                for part in v.split(';'):
                    name,_,value=part.partition(':')
                    if name.strip().lower() in self.styles and not re.search(r'url|expression|@|[<>\\]',value,re.I):declarations.append(name+':'+value)
                clean.append(('style',';'.join(declarations)))
            elif k in ('width','height','colspan','cellpadding','cellspacing','align','valign','bgcolor','alt'):clean.append((k,v))
            elif tag=='img' and k=='src':
                # Only a CDN that supports bounded image transforms. Never load
                # tracking pixels or full-resolution arbitrary remote artwork.
                if urlsplit(v).hostname=='cdn.shopify.com':
                    from crm_catalogue import picker_thumbnail
                    clean.extend([('src',picker_thumbnail(v)),('loading','lazy'),('referrerpolicy','no-referrer')])
        self.out.append('<'+tag+''.join(' '+k+'="'+escape(v,quote=True)+'"' for k,v in clean)+'>')
    def handle_endtag(self,tag):
        if tag in ('script','style','iframe','object','svg','form','head'):
            self.skip=max(0,self.skip-1);return
        if not self.skip and tag in self.tags and tag not in ('img','br','hr'):self.out.append('</'+tag+'>')
    def handle_data(self,data):
        if not self.skip:self.out.append(escape(data))

@lru_cache(maxsize=64)
def miniature(source,settings):
    doc=json.loads(source);cfg=json.loads(settings)
    from crm_checkout_preview import needs_checkout,document,sample
    if needs_checkout(doc):doc,_=document(doc,sample(doc))
    from crm_email_size import render_production
    html=render_production(doc,cfg)['html']
    parser=InertEmail();parser.feed(html)
    return ''.join(parser.out)

@st.fragment
def thumbnail(store,step,row):
    import base64
    from crm_thumbnail_cache import selection,request,source_loader
    from crm_thumbnail_store import private_store
    digest,label,live=selection(row,step)
    key='flow-thumb-'+step['step_id']+'-'+digest[:20]
    with st.container(key=key):
        wake=st.button('Load email thumbnail',key=key+'load')
        phase='DEFERRED';data=None
        if wake or st.session_state.get(key):
            st.session_state[key]=True
            phase,data=request(digest,source_loader(store,row,step,live),private_store(store))
        if data:
            body='<img width="76" height="100" loading="lazy" decoding="async" alt="'+escape(label+' email preview')+'" src="data:image/webp;base64,'+base64.b64encode(data).decode()+'">'
        else:
            text={'DEFERRED':'Preview','LOADING':'Preparing preview?','BUSY':'Preview queued?','ERROR':'Preview unavailable. Click to open email.'}[phase]
            body='<span role="status">'+text+'</span>'
        st.html('<div id="'+key+'" class="sc-flow-thumbnail" role="button" tabindex="0" data-phase="'+phase+'" data-key="'+key+'" data-preview="flow-preview-'+step['step_id']+'" aria-label="Open '+escape(label)+' email preview" style="width:76px;height:100px;overflow:hidden;background:#fff;font-size:10px;display:flex;align-items:center;justify-content:center">'+body+'</div><small style="font-size:10px">'+escape(label)+'</small>')

SCRIPT='''<script>(()=>{
 if(window.scFlowThumbController){window.scFlowThumbController.scan();return;}
 const visible=new Set(), attempts=new Map();let observed=new WeakSet(),nextWake=0;
 const root=()=>document.querySelector('.st-key-flow-workspace');
 const preview=e=>{const host=e.target.closest?.('.sc-flow-thumbnail');if(host&&(e.type==='click'||['Enter',' '].includes(e.key))){e.preventDefault();document.querySelector('.st-key-'+host.dataset.preview+' button')?.click();}};
 document.addEventListener('click',preview);document.addEventListener('keydown',preview);
 const observer=new IntersectionObserver(entries=>{for(const e of entries){if(e.isIntersecting)visible.add(e.target);else visible.delete(e.target);}pump();},{rootMargin:'80px'});
 const pump=()=>{
   if(!root()){observer.disconnect();observed=new WeakSet();visible.clear();attempts.clear();return;}
   if(nextWake>Date.now())return;
   for(const e of visible){
     if(!e.isConnected){observer.unobserve(e);visible.delete(e);continue;}
     if(!['DEFERRED','LOADING','BUSY'].includes(e.dataset.phase))continue;
     const key=e.dataset.key,now=Date.now(),last=attempts.get(key)||{at:0,start:now};
     if(now-last.start>90000){e.dataset.phase='ERROR';e.textContent='Preview unavailable. Click to open email.';continue;}
     if(1200>now-last.at)continue;
     const button=document.querySelector('.st-key-'+key+'load button');
     // Missing controls are retried after mount; never mark them loaded early.
     if(button){attempts.set(key,{at:now,start:last.start});nextWake=now+200;button.click();break;}
   }
 };
 const scan=()=>{
   root()?.querySelectorAll('.sc-flow-thumbnail').forEach(e=>{
     if(!observed.has(e)){observed.add(e);observer.observe(e);}
     const img=e.querySelector('img');
     if(img&&!img.dataset.guarded){img.dataset.guarded='1';const failed=()=>{e.dataset.phase='ERROR';e.textContent='Preview unavailable. Click to open email.';};img.addEventListener('error',failed);if(img.complete&&!img.naturalWidth)failed();}
   });pump();
 };
 let queued=false;new MutationObserver(()=>{if(!queued){queued=true;requestAnimationFrame(()=>{queued=false;scan();});}}).observe(document.body,{childList:true,subtree:true});
 setInterval(()=>{if(root())scan();},300);
 window.scFlowThumbController={scan};scan();
})()</script>'''
