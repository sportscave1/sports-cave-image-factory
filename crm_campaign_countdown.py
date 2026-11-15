"""Display-only countdown to a verified persisted UTC instant; no network calls."""
from html import escape

def markup(instant,server_now=None):
    from crm_logic import date
    from crm_logic import now
    stamp=date(server_now) if server_now else now()
    return '<small data-sc-campaign-now="'+escape(stamp.isoformat(),quote=True)+'" data-sc-campaign-due="'+escape(date(instant).isoformat(),quote=True)+'" aria-live="off"></small>' if instant else ''

def local_markup(instant):
    from crm_logic import date
    return '<small data-sc-campaign-local="'+escape(date(instant).isoformat(),quote=True)+'">Next dispatch · loading your local time</small>' if instant else ''


def arm():
    import streamlit as st
    import uuid
    st.html('''<script>/* '''+uuid.uuid4().hex+''' */(()=>{
      clearInterval(window.scCampaignCountdown);
      const anchors=window.scCampaignCountdownAnchors ||= new WeakMap();
      const localLabels=window.scCampaignLocalLabels ||= new WeakMap();
      const formatter=new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'});
      const update=()=>{const nodes=document.querySelectorAll('[data-sc-campaign-due]');
        if(!nodes.length&&!document.querySelector('[data-sc-campaign-local]')){clearInterval(window.scCampaignCountdown);return;}
        if(document.hidden)return;
        document.querySelectorAll('[data-sc-campaign-local]').forEach(n=>{if(localLabels.get(n)!==n.dataset.scCampaignLocal){n.textContent='Next dispatch · '+formatter.format(new Date(n.dataset.scCampaignLocal))+' · your local time';localLabels.set(n,n.dataset.scCampaignLocal);}});
        nodes.forEach(n=>{if(!anchors.has(n)||anchors.get(n).stamp!==n.dataset.scCampaignNow)anchors.set(n,{stamp:n.dataset.scCampaignNow,server:Date.parse(n.dataset.scCampaignNow),tick:performance.now()});
          const anchor=anchors.get(n);const seconds=Math.ceil((Date.parse(n.dataset.scCampaignDue)-anchor.server-(performance.now()-anchor.tick))/1000);
          const countdown=seconds>=3600?Math.floor(seconds/3600)+'h '+Math.floor(seconds%3600/60)+'m':String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');
          n.textContent=seconds>0?'Next send in '+countdown:'Due · awaiting worker status';});};
      update();window.scCampaignCountdown=setInterval(update,1000);
    })();</script>''',unsafe_allow_javascript=True)
