"""Keyboard fallback for the native Campaigns action popover, without a rerun."""
import streamlit as st


def install():
    st.html('''<script>(()=>{
      if(window.scCampaignEscapeInstalled)return;
      window.scCampaignEscapeInstalled=true;
      const opened=()=>{
        // Streamlit also gives the popover role=dialog. Only a real modal
        // should take precedence over the action-menu Escape fallback.
        if(document.querySelector('[data-testid="stDialog"] [role="dialog"]'))return;
        const menu=[...document.querySelectorAll('[data-testid="stPopoverBody"]')]
          .find(el=>el.querySelector('[class*="st-key-home-actions-"]')&&el.getClientRects().length);
        if(!menu)return;
        const trigger=document.querySelector('.st-key-crm-home-table [data-testid="stPopover"] button[aria-expanded="true"]');
        if(!trigger)return;
        return {menu,trigger};
      };
      document.addEventListener('keydown',event=>{
        if(event.key!=='Escape'||event.isComposing)return;
        const current=opened();if(!current)return;
        const {trigger}=current;
        event.preventDefault();event.stopImmediatePropagation();
        trigger.click();
        requestAnimationFrame(()=>{if(trigger.isConnected)trigger.focus({preventScroll:true});});
      },true);
      document.addEventListener('pointerdown',event=>{
        const current=opened();if(!current)return;
        if(current.menu.contains(event.target)||current.trigger.contains(event.target))return;
        // Keep the original outside action and its focus behaviour intact.
        current.trigger.click();
      },true);
    })();</script>''',unsafe_allow_javascript=True)
