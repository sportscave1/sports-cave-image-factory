"""Shared compact presentation only. Flow adapters own all reads and actions."""
from html import escape
import streamlit as st

STYLE='''<style>
[class*="st-key-crm-preview-toolbar-"]{height:40px!important;min-height:40px!important;max-height:42px!important;padding:2px 0;background:#fffdf8;border-bottom:1px solid #e8e4db;box-sizing:border-box;display:flex!important;flex-direction:row!important;flex-wrap:nowrap!important;align-items:center!important;gap:3px!important}
[class*="st-key-crm-preview-toolbar-"]>[data-testid="stLayoutWrapper"]{flex:1 1 0!important;min-width:0!important;width:0!important}
[class*="st-key-crm-preview-toolbar-"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;align-items:center!important;gap:3px!important;height:36px}
[class*="st-key-crm-preview-toolbar-"] [data-testid="stElementContainer"]{width:auto!important;flex:0 0 auto;min-width:0}
[class*="st-key-crm-preview-toolbar-"] [data-testid="stMarkdownContainer"] p{font:600 12px/28px 'Segoe UI',Arial,sans-serif;margin:0;white-space:nowrap}
[class*="st-key-crm-preview-toolbar-"] button{min-height:28px!important;height:28px!important;padding:3px 6px!important;border-radius:3px!important;border:1px solid transparent!important;background:transparent!important;box-shadow:none!important;color:#6b6861!important;font:12px/18px 'Segoe UI',Arial,sans-serif!important}
[class*="st-key-crm-preview-toolbar-"] button:hover{background:#f1eee7!important;border-color:#ded9cf!important}
[class*="st-key-crm-preview-toolbar-"] button[kind="primary"]{background:#f3ecdd!important;border-color:#d7c494!important;color:#775f2b!important}
[class*="st-key-crm-preview-toolbar-"] button:focus-visible{outline:2px solid #b69a62!important;outline-offset:1px}
[class*="st-key-crm-preview-toolbar-"] button [data-testid="stIconMaterial"]{font-size:17px!important;width:18px;height:18px}
[class*="st-key-crm-preview-toolbar-"] [class*="st-key-preview-customer-"]{min-width:0!important;width:100%!important}
[class*="st-key-crm-preview-toolbar-"] [class*="st-key-preview-customer-"] [data-testid="stElementContainer"],
[class*="st-key-crm-preview-toolbar-"] [class*="st-key-preview-customer-"] [data-testid="stPopover"],
[class*="st-key-crm-preview-toolbar-"] [class*="st-key-preview-customer-"] button{width:100%!important;min-width:0}
[class*="st-key-crm-preview-toolbar-"] [class*="st-key-preview-customer-"] button [data-testid="stMarkdownContainer"]{overflow:hidden;min-width:0;flex:1}
[class*="st-key-crm-preview-toolbar-"] [class*="st-key-preview-customer-"] button>div{min-width:0!important;max-width:100%;overflow:hidden}
[class*="st-key-crm-preview-toolbar-"] [class*="st-key-preview-customer-"] [data-testid="stPopover"]>div{min-width:0;max-width:100%}
[class*="st-key-crm-preview-toolbar-"] [class*="st-key-preview-customer-"]{overflow:hidden}
[class*="st-key-crm-preview-toolbar-"] [class*="st-key-preview-customer-"] button p{font-weight:400;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
.st-key-crm-composer-preview{gap:2px!important}
@media(max-width:420px){[class*="st-key-crm-preview-toolbar-"] [data-testid="stMarkdownContainer"] p{font-size:11px}[class*="st-key-crm-preview-toolbar-"] button{padding:3px 4px!important}[class*="st-key-crm-preview-toolbar-"] [data-testid="stHorizontalBlock"]{gap:1px!important}}
</style>'''


def details(cache,doc):
    headers=(cache or {}).get('personalised_headers') or {}
    result=[label+': '+headers[field] for field,label in [('subject','Subject'),('preheader','Preview text')] if headers.get(field)]
    offer=doc.get('recovery_discount')
    if offer:result.append('Offer: '+offer['code']+' · '+offer['value'])
    return result


def toolbar(key,name,*,select=None,refresh=None,refresh_enabled=True,details=(),size=None,busy=False,warning=''):
    from crm_html_workspace import _preview_device
    mode=st.session_state.get(key+'preview_device','Desktop')
    size_text=f"Email size: {size['html_kb']:.1f} KB / 95 KB · {size['status']}" if size else 'Email size is calculated from the personalised production render.'
    tip=' · '.join([name,size_text,'Refreshing in background' if busy else ''])
    st.html(STYLE)
    with st.container(key='crm-preview-toolbar-'+key,horizontal=True,vertical_alignment='center',gap='small'):
        st.markdown('**Email Preview**')
        for label,icon in [('Desktop',':material/desktop_windows:'),('Mobile',':material/smartphone:')]:
            st.button('',icon=icon,help=label,key=key+'device_'+label,type='primary' if mode==label else 'secondary',on_click=_preview_device,args=(key,label))
        with st.container(key='preview-customer-'+key):
            with st.popover('Previewing: '+name,help=tip,key=key+'customer_popover',width='stretch',on_change='rerun') as menu:
                if menu.open:
                    if select:select()
                    st.caption(size_text)
                    for detail in details:
                        if detail:st.caption(detail)
                    if busy:st.caption('Refreshing verified customer data in the background.')
        st.button('',icon=':material/refresh:',help='Refresh preview',key=key+'checkout_refresh',disabled=not refresh_enabled,on_click=refresh)
        if warning or size and size['status']=='TOO LARGE':
            with st.popover('',icon=':material/warning:',help='Preview diagnostics',key=key+'preview_diagnostics'):
                if warning:st.caption(warning)
                if size and size['status']=='TOO LARGE':st.error('Email exceeds the existing 95 KB delivery limit. Reduce the email before sending.')
    return mode


def arm(key,*,seconds=.2):
    """One-shot completion event in this fragment; no idle polling."""
    import json,uuid
    poll=key+'preview-completion'
    st.html('<style>.st-key-'+escape(poll,quote=True)+'{display:none}</style>')
    with st.container(key=poll):st.button('Check preview completion',key=poll+'-tick')
    # The home-page timer intentionally pauses for every open popover. Preview
    # completion is scoped to its own fragment and must also work while the
    # customer picker or Send Test is open; no unrelated form is rerendered.
    st.html('<script>/*'+uuid.uuid4().hex+'*/(()=>{const key='+json.dumps(poll)+';window.scPreviewTimers??={};clearTimeout(window.scPreviewTimers[key]);const tick=()=>{const b=document.querySelector(".st-key-"+key+" button");if(!b?.isConnected)return;if(document.hidden||b.disabled){window.scPreviewTimers[key]=setTimeout(tick,500);return;}b.click();};window.scPreviewTimers[key]=setTimeout(tick,'+str(int(seconds*1000))+');})();</script>',unsafe_allow_javascript=True)
