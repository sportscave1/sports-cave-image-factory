"""Optional campaign HTML sections. Legacy documents remain on their original path."""
from html import escape
import re
from crm_campaign_html import import_html
from crm_tracking import asset_url

FOOTER_TOKEN = '{{SYSTEM_FOOTER}}'
DEFAULT_FOOTER = '<!-- Add optional footer content above the protected Sports Cave compliance footer. -->\n' + FOOTER_TOKEN


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


def import_sections(doc, *, images_off=False, campaign_key=''):
    """Sanitize sections independently; user markup cannot wrap the locked footer."""
    sections = doc['html_sections']
    header, header_text, header_checks = import_html(sections['header'], images_off=images_off, campaign_key=campaign_key)
    body, body_text, checks = import_html(doc.get('custom_html', ''), images_off=images_off, campaign_key=campaign_key)
    footer, footer_text, footer_checks = import_html(sections['footer'].replace(FOOTER_TOKEN, ''), images_off=images_off, campaign_key=campaign_key)
    for label in checks:
        if label != 'HTML content present':
            checks[label] = checks[label] and header_checks[label] and footer_checks[label]
    # The mandatory footer is always appended separately by render_campaign, even
    # if its token is removed, duplicated or nested inside hidden/malformed HTML.
    return header + body + footer, '\n\n'.join(t for t in (header_text, body_text, footer_text) if t), checks
