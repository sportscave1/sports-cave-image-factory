"""Optional campaign HTML sections. Legacy documents remain on their original path."""
from html import escape
import re
from crm_campaign_html import import_html
from crm_tracking import asset_url

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
    result.setdefault('html_sections',deepcopy(cfg['email_defaults']))
    return result


def section_defaults(cfg):
    accent = cfg.get('accent', '#b49450')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', accent):
        accent = '#b49450'
    logo = cfg.get('logo', '')
    brand = ('<img src="' + escape(logo, quote=True) + '" alt="Sports Cave" width="180" style="max-width:180px;height:auto">'
             if asset_url(logo) else 'SPORTS CAVE')
    header = ('<table role="presentation" width="100%" cellspacing="0" cellpadding="0">\n'
              '<tr><td style="padding:22px 24px;background-color:#171717;color:#ffffff;border-bottom:3px solid ' + accent + ';font-family:Arial;font-size:20px;font-weight:700">\n'
              + brand + '\n<p style="font-family:Arial;font-size:11px;color:#dfc986">CAMPAIGN TEST / PREVIEW · LIVE MARKETING DISABLED</p>\n'
              '</td></tr>\n</table>')
    return {'header': header, 'footer': DEFAULT_FOOTER}


def import_sections(doc, *, images_off=False, campaign_key='', cfg=None, unsubscribe_url=None):
    """Balance and sanitize each authored section without adding footer content."""
    sections = doc['html_sections']
    header, header_text, header_checks = import_html(sections['header'], images_off=images_off, campaign_key=campaign_key)
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
