"""Optional campaign HTML sections. Legacy documents remain on their original path."""
from html import escape
from crm_campaign_html import import_html

from crm_campaign_footer import LEGACY_TOKEN as FOOTER_TOKEN, DEFAULT_FOOTER, render_footer


def with_email_defaults(doc,cfg):
    """Resolve a render copy only. Queue snapshots carry their resolved settings."""
    if 'email_defaults' not in cfg:return doc
    from copy import deepcopy
    result=deepcopy(doc)
    if result.get('content_mode')!='HTML':
        from crm_email_blocks import render_blocks,legacy_blocks
        body=render_blocks(result.get('blocks') or legacy_blocks(result['content']),market=result['market'])[0]
        result.update(content_mode='HTML',custom_html='<table role="presentation" width="100%">'+body+'</table>')
    # Stored sections are historical copies, not overrides of shared branding.
    # Resolve only the render copy so authored bodies and history stay intact.
    result['html_sections']=deepcopy(cfg['email_defaults'])
    return result


def section_defaults(cfg):
    from pathlib import Path
    return {'header':Path(__file__).with_name('templates').joinpath('email_shared_header.html').read_text(encoding='utf-8'), 'footer':DEFAULT_FOOTER}


def import_sections(doc, *, images_off=False, campaign_key='', cfg=None, unsubscribe_url=None):
    """Balance and sanitize each authored section without adding footer content."""
    sections = doc['html_sections']
    header, header_text, header_checks = import_html(sections['header'], images_off=images_off, campaign_key=campaign_key)
    # This exact repository-owned asset is trusted. Preserve its Outlook fallback
    # without permitting arbitrary conditional-comment HTML from the editor.
    approved=section_defaults({})['header']
    if sections['header'].strip()==approved.strip() and not images_off:
        header=sections['header']
        if campaign_key:
            from crm_tracking import campaign_link
            url=campaign_link('https://www.sportscaveshop.com',campaign_key,'html_1')
            header=header.replace('href="https://www.sportscaveshop.com"','href="'+escape(url,quote=True)+'"')
    from crm_middle_sections import render_middle
    body, body_text, checks = render_middle(doc, images_off=images_off, campaign_key=campaign_key)
    if cfg is None:
        from crm_campaign_content import settings
        cfg=settings()
    footer, footer_text, footer_checks = render_footer(sections['footer'],cfg,images_off=images_off,unsubscribe_url=unsubscribe_url)
    for label in checks:
        if label != 'HTML content present':
            checks[label] = checks[label] and header_checks.get(label,True) and footer_checks.get(label,True)
    return header + body + footer, '\n\n'.join(t for t in (header_text, body_text, footer_text) if t), checks
