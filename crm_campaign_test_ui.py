"""Compact, section-oriented test readiness; no persistence or delivery actions."""
from html import escape
import json
import streamlit as st
from crm_campaign_issues import issue_groups


def test_styles():
    st.html('''<style>
    [data-testid="stPopoverBody"]:has(.sc-test-readiness){width:min(520px,calc(100vw - 24px))!important;max-width:calc(100vw - 24px);padding:14px!important;max-height:85vh;overflow:auto}
    [data-testid="stPopoverBody"]:has(.sc-test-readiness) [data-testid="stVerticalBlock"]{gap:10px}
    .sc-test-readiness{font-size:13px;line-height:1.4;color:#242320}
    .sc-test-readiness h4{font-size:14px;margin:0 0 8px;font-weight:600}
    .sc-test-issue{padding:9px 0;border-top:1px solid #e6e1d7}
    .sc-test-issue p{margin:3px 0;color:#68645d;font-size:12px}
    .sc-test-issue button{background:none;border:0;padding:5px 0;color:#765b24;font-size:12px;cursor:pointer;min-height:28px}
    .sc-test-issue button:focus-visible{outline:2px solid #b49450;outline-offset:2px}
    </style>''')


def readiness(checks):
    groups=issue_groups(checks)
    failed=[label for label,valid in checks['test'].items() if not valid]
    if not failed:
        st.html('<div class="sc-test-readiness">✓ Ready to send test</div>')
        return
    heading=f'Test not ready · {len(groups)} section'+('s' if len(groups)!=1 else '')+' need attention' if groups else 'Test not ready'
    parts=['<div class="sc-test-readiness"><h4>'+escape(heading)+'</h4>']
    for group in groups:
        parts.append('<div class="sc-test-issue"><strong>'+escape(group['display_label'])+'</strong>')
        if group['image_count']:parts.append('<p>'+str(group['image_count'])+' images need attention</p>')
        parts.extend('<p>'+escape(message)+'</p>' for message in group['messages'])
        if group['editable']:
            parts.append('<button type="button" data-crm-section="'+escape(group['section_id'],quote=True)+'">Go to section</button>')
        parts.append('</div>')
    section_checks={'Images use durable public JPEG/PNG URLs','Image alt text complete','Catalogue product facts valid',
        'HTML contains only safe email markup','CTA label and HTTPS URL valid'}
    for label in failed:
        if groups and label in section_checks:continue
        friendly={'Images use durable public JPEG/PNG URLs':'Image source needs attention',
            'Image alt text complete':'Image description missing','Catalogue product facts valid':'Catalogue needs attention',
            'Subject present and truthful-copy review complete':'Add a truthful subject',
            'HTML content present':'Add email content','Plain-text alternative generated':'Add readable email text',
            'HTML size reviewed / below 95 KB':'Email content is too large',
            'HTML contains only safe email markup':'Review unsafe or malformed HTML',
            'CTA label and HTTPS URL valid':'Check link destinations'}.get(label,label)
        parts.append('<p>'+escape(friendly)+'</p>')
    st.html(''.join(parts)+'</div>')
    with st.expander('View technical details',expanded=False):
        st.code(json.dumps({'failed_checks':failed,'sections':checks.get('section_issues',[])},indent=2),language='json',height=220)
