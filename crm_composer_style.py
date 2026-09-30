"""Presentation-only overrides scoped to the Campaign composer."""
import streamlit as st
from html import escape


def history_cell(value,sub='',*,pill=False,label=None):
    """Escaped, two-level cells shared by the existing history rows."""
    value=str(value);sub=str(sub)
    return ('<div class="sc-history-cell" title="'+escape(label or value,quote=True)+'">'
            '<strong'+(' class="sc-history-status"' if pill else '')+'>'+escape(value)+'</strong>'
            +('<small>'+escape(sub)+'</small>' if sub else '')+'</div>')


def history_date(value):
    from crm_logic import date
    parsed=date(value)
    return parsed.strftime('%d %b %H:%M')+' UTC' if parsed else '—'


def history_header(labels,widths):
    with st.container(key='crm-history-table-heading'):
        columns=st.columns(widths,gap='small')
        for column,label in zip(columns,labels):
            column.html('<div class="sc-history-label" title="'+escape(label,quote=True)+'">'+escape(label)+'</div>')


def polished_styles():
    st.html('''<style>
    /* Scope every rule: Inbox, dialogs and other CRM pages retain their styling. */
    html body .st-key-crm-workspace:has(.st-key-crm-composer-layout){gap:10px}
    html body .st-key-crm-campaign-actions{align-items:center;flex-wrap:nowrap;gap:8px}
    html body .st-key-crm-campaign-actions > div{flex:0 0 auto !important;width:auto !important}
    html body .st-key-crm-campaign-actions button{white-space:nowrap;min-height:38px !important;padding:8px 16px !important;border-radius:7px !important;font-weight:500}
    html body .st-key-crm-campaign-actions button[kind="primary"]{background:var(--sc-gold,#c9a33f) !important;color:#171813 !important;border-color:var(--sc-gold,#c9a33f) !important;font-weight:650;box-shadow:0 1px 2px #00000012 !important}
    html body .st-key-crm-campaign-actions button[kind="secondary"]{background:#faf9f6 !important;color:#343630 !important}
    html body .st-key-crm-campaign-actions button:hover{filter:brightness(.97)}
    html body .st-key-crm-campaign-actions button:focus-visible{outline:2px solid var(--sc-gold,#c9a33f);outline-offset:3px}
    html body .st-key-crm-composer-layout{--crm-panel-height:clamp(440px,calc(100dvh - var(--sc-topbar-height,64px) - 165px),740px);gap:14px}
    html body .st-key-crm-composer-controls{padding:14px !important;background:#faf9f6;border-radius:10px;border-color:#e3dfd5}
    html body .st-key-crm-composer-controls [data-testid="stWidgetLabel"]{margin-bottom:3px}
    html body .st-key-crm-composer-controls [data-testid="stWidgetLabel"] p{font-size:12px;font-weight:500;color:#55584f}
    html body .st-key-crm-composer-controls [role="tablist"]{gap:20px;margin-bottom:10px}
    html body .st-key-crm-composer-preview{background:#f5f4ef;border-radius:10px;padding:12px 14px;border-color:#e3dfd5}
    html body .st-key-crm-composer-preview > div{gap:8px}
    html body .st-key-crm-preview-devices{gap:4px}
    html body .st-key-crm-send-timing [role="radiogroup"]{display:flex;gap:4px;background:#efeee8;padding:4px;border:1px solid #e3dfd5;border-radius:8px}
    html body .st-key-crm-send-timing [role="radiogroup"] label{flex:1;margin:0 !important;padding:7px 12px;border-radius:5px;justify-content:center;cursor:pointer;min-width:0}
    html body .st-key-crm-send-timing [role="radiogroup"] label > div:first-child{position:absolute;opacity:0;width:1px;height:1px;overflow:hidden}
    html body .st-key-crm-send-timing [role="radiogroup"] > div{flex:1}
    html body .st-key-crm-send-timing [data-testid="stElementContainer"],html body .st-key-crm-send-timing .stRadio{width:100% !important}
    html body .st-key-crm-send-timing [role="radiogroup"] label p{white-space:nowrap}
    html body .st-key-crm-send-timing [data-testid="stRadioOption"] > div > div:first-child{display:none}
    html body .st-key-crm-send-timing [data-testid="stRadioOption"] > div{justify-content:center}
    html body .st-key-crm-send-timing [role="radiogroup"] label:has(input:checked){background:#252721;box-shadow:inset 0 -2px var(--sc-gold,#c9a33f)}
    html body .st-key-crm-send-timing [role="radiogroup"] label:has(input:checked) p{color:#fff !important}
    html body .st-key-crm-send-timing [role="radiogroup"] label:has(input:focus-visible){outline:2px solid var(--sc-gold,#c9a33f);outline-offset:2px}
    html body .st-key-crm-send-timing [role="radiogroup"] label:hover{box-shadow:inset 0 0 0 1px #b9b7aa}
    html body .st-key-crm-recent-campaigns{border-top:1px solid #e3dfd5;padding-top:14px;gap:6px}
    html body .st-key-crm-recent-campaigns h4{font-size:15px;letter-spacing:.01em;padding:0;margin:0}
    html body .st-key-crm-recent-campaigns [data-testid="stHorizontalBlock"]{gap:10px;align-items:center}
    html body .st-key-crm-history-heading{justify-content:space-between;margin-bottom:2px}
    html body .st-key-crm-history-heading > div:last-child{flex:0 0 auto;margin-left:auto}
    html body .st-key-crm-history-heading button{min-height:34px;font-size:12px;border:1px solid #dcd8ce;background:#fcfbf8;border-radius:8px}
    html body .st-key-crm-history-selector [role="radiogroup"]{display:flex;flex-wrap:nowrap;gap:2px;width:max-content;background:#f5f3ee;border:1px solid #e0dcd2;border-radius:9px;padding:3px;margin:0 0 4px}
    html body .st-key-crm-history-selector [role="radiogroup"] label{margin:0 !important;min-height:34px;padding:7px 17px;border-radius:6px;cursor:pointer}
    html body .st-key-crm-history-selector [role="radiogroup"] label > div:first-child{position:absolute;opacity:0;width:1px;height:1px;overflow:hidden}
    html body .st-key-crm-history-selector [data-testid="stRadioOption"] > div > div:first-child{display:none}
    html body .st-key-crm-history-selector [role="radiogroup"] label p{font-size:12px;color:#66645e;white-space:pre;font-weight:500}
    html body .st-key-crm-history-selector [role="radiogroup"] label:has(input:checked){background:#fffdfa;box-shadow:inset 0 -2px var(--sc-gold,#c9a33f)}
    html body .st-key-crm-history-selector [role="radiogroup"] label:has(input:checked) p{color:#22231f;font-weight:650}
    html body .st-key-crm-history-selector [role="radiogroup"] label:has(input:focus-visible){outline:2px solid var(--sc-gold,#c9a33f);outline-offset:1px}
    html body .st-key-crm-history-selector [role="radiogroup"] label:hover{background:#ebe8e0}
    html body .st-key-crm-recent-campaigns [class*="st-key-crm-history-row-"]{border-top:1px solid #e9e6de;padding:6px 0;gap:0}
    html body .st-key-crm-recent-campaigns [class*="st-key-crm-history-row-"]:hover{background:#faf8f2}
    html body .st-key-crm-recent-campaigns [data-testid="stColumn"]{min-width:0}
    html body .st-key-crm-recent-campaigns [data-testid="stPopover"] button{min-height:32px;padding:4px 9px;border:1px solid #e2ded4;border-radius:7px;background:#fcfbf8;color:#44453f;font-size:12px;white-space:nowrap}
    html body .st-key-crm-recent-campaigns button:focus-visible{outline:2px solid var(--sc-gold,#c9a33f);outline-offset:2px}
    html body .st-key-crm-recent-campaigns button[kind="tertiary"] p{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;font-weight:550}
    html body .st-key-crm-recent-campaigns .sc-history-cell{min-width:0;line-height:1.3;font-size:12px;font-variant-numeric:tabular-nums;color:#30312c;padding:2px 0}
    html body .st-key-crm-recent-campaigns .sc-history-cell strong{display:block;font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    html body .st-key-crm-recent-campaigns .sc-history-cell small{display:block;font-size:11px;color:#74746b;margin-top:3px;white-space:nowrap}
    html body .st-key-crm-recent-campaigns .sc-history-cell .sc-history-status{display:inline-block;border:1px solid #e0ddd2;border-radius:5px;background:#f3f1ea;padding:3px 6px;font-size:10px;white-space:normal}
    html body .st-key-crm-recent-campaigns .sc-history-label{color:#76766b;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.025em;white-space:nowrap;padding:7px 0}
    html body .st-key-crm-sent-rows{overflow-x:auto;padding-bottom:3px;gap:0}
    html body .st-key-crm-sent-rows [data-testid="stHorizontalBlock"]{min-width:1030px;flex-wrap:nowrap}
    html body .st-key-crm-history-empty{background:#faf9f5;border:1px solid #e7e3d9;border-radius:8px;padding:12px 14px}
    html body .st-key-crm-recent-campaigns [data-testid="stCaptionContainer"] p{font-size:12px;margin:0}
    html body .st-key-crm-recent-campaigns button[kind="tertiary"]{border:0 !important;background:transparent !important;text-align:left}
    html body .st-key-crm-recent-campaigns [data-testid="stExpander"] summary{min-height:34px;padding:5px 10px}
    html body #sc-campaign-save-status{margin:2px 0 6px;font-size:11px !important}
    /* Recovery bridge occupies no visible space; retain its iframe and events. */
    html body [data-testid="stElementContainer"]:has(iframe[title="crm_recovery_ui.campaign_recovery"]){min-height:0;height:0;overflow:hidden;margin:0}
    html body [data-testid="stVerticalBlock"]:has(>.st-key-crm-composer-layout){gap:8px}
    @media(max-width:1100px){html body .st-key-crm-campaign-actions button{padding:7px 10px !important}html body .st-key-crm-composer-layout{gap:10px}}
    @media(max-width:760px){html body .st-key-crm-composer-layout{flex-direction:column}html body .st-key-crm-composer-layout > div:has(>.st-key-crm-composer-controls){width:100% !important;flex-basis:auto !important}html body .st-key-crm-composer-preview{min-width:0}}
    </style>''')
