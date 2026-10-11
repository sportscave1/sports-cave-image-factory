"""Dense automation editor panels; no OS shell or campaign overrides."""
import streamlit as st


def styles():
    st.html('''<style>
    html body [data-testid="stMain"]:has(.st-key-automation-toolbar) .st-key-crm-composer-controls{padding:8px!important}
    [data-testid="stMain"]:has(.st-key-automation-toolbar) .st-key-crm-composer-controls div:has(>[role="tablist"]){position:sticky;top:0;z-index:5;background:#faf9f6!important}
    [data-testid="stMain"]:has(.st-key-automation-toolbar) .st-key-crm-composer-controls [role="tablist"]{background:#faf9f6!important;padding-top:4px;margin-bottom:4px!important}
    .st-key-crm-compact-library [data-testid="stVerticalBlock"]{gap:4px!important}
    .st-key-crm-compact-library [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:4px!important;min-width:0}
    .st-key-crm-compact-library [class*="st-key-compact-row-"]>div:first-child,.st-key-compact-library-heading>div:first-child{flex:1 1 0!important;min-width:0!important}
    .st-key-crm-compact-library [class*="st-key-compact-row-"]>div:last-child,.st-key-compact-library-heading>div:last-child{flex:0 0 30px!important;width:30px!important}
    .st-key-crm-compact-library button{min-height:28px!important;padding:2px 6px!important;white-space:nowrap;border-radius:4px!important}
    .st-key-crm-compact-library button p{font-size:12px!important;text-align:left}
    html body .st-key-crm-compact-library [class*="st-key-compact-group-"] button{justify-content:flex-start!important;background:#f0efeb!important}
    .st-key-crm-compact-library [class*="st-key-compact-group-"] button>div{width:100%;justify-content:flex-start!important}
    .st-key-crm-compact-library [class*="st-key-compact-edit-"] button p,.st-key-compact-template-add button p{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
    .compact-template-name{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;padding-left:12px;line-height:28px}
    html body .st-key-crm-personalise-image [data-testid="stExpander"] summary{min-height:30px!important;padding:4px 6px!important}
    .st-key-crm-personalise-image [data-testid="stVerticalBlock"]{gap:5px!important}
    .st-key-crm-personalise-image label p,.st-key-crm-personalise-image button p{font-size:12px!important}
    .st-key-crm-compact-library textarea{line-height:1.35!important}
    @media(max-width:760px){
      .st-key-crm-composer-layout:has(.st-key-crm-automation-live-preview){flex-wrap:wrap!important}
      .st-key-crm-composer-layout:has(.st-key-crm-automation-live-preview)>div{width:100%!important;flex-basis:100%!important;min-width:0!important}
      .st-key-crm-composer-layout:has(.st-key-crm-automation-live-preview) .st-key-crm-composer-controls{height:60dvh!important;min-height:320px!important}
    }
    </style>''')
