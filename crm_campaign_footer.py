"""Editable campaign footer HTML with inline, validated compliance placeholders."""
from html import escape
from html.parser import HTMLParser
import re

from crm_campaign_html import import_html, TEMPLATE_LINK_TOKENS
from crm_tracking import public_https
from crm_resend_marketing import single_email

LEGACY_TOKEN = '{{SYSTEM_FOOTER}}'
DISCLOSURE = 'You’re receiving this marketing email because you subscribed to Sports Cave updates.'
LINK_TOKENS = TEMPLATE_LINK_TOKENS
REQUIRED = {
    '{{BUSINESS_NAME}}': '<strong>{{BUSINESS_NAME}}</strong>',
    '{{BUSINESS_ADDRESS}}': '<span>{{BUSINESS_ADDRESS}}</span>',
    '{{CONTACT_EMAIL}}': '<span>{{CONTACT_EMAIL}}</span>',
    '{{WEBSITE_URL}}': '<a href="{{WEBSITE_URL}}" style="color:#dfc986">Website</a>',
    '{{MARKETING_DISCLOSURE}}': '<span>{{MARKETING_DISCLOSURE}}</span>',
    '{{UNSUBSCRIBE_URL}}': '<a href="{{UNSUBSCRIBE_URL}}" style="color:#dfc986">Unsubscribe</a>',
}
DEFAULT_FOOTER = '''<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#171717">
<tr><td align="center" style="padding:24px;color:#eeeeeb;background-color:#171717;border-top:3px solid #c9a33f;font-family:Arial;font-size:13px;line-height:1.6">
<p><strong>{{BUSINESS_NAME}}</strong></p>
<p><a href="https://www.instagram.com/sportscaveshop/" style="color:#dfc986">Instagram</a> · <a href="https://www.facebook.com/profile.php?id=100090408036260" style="color:#dfc986">Facebook</a> · <a href="https://au.pinterest.com/SportsCaveShop/" style="color:#dfc986">Pinterest</a></p>
<p><a href="{{WEBSITE_URL}}" style="color:#eeeeeb">Website</a> · <a href="{{CONTACT_URL}}" style="color:#eeeeeb">{{CONTACT_EMAIL}}</a></p>
<p>{{BUSINESS_ADDRESS}}</p>
<p>{{MARKETING_DISCLOSURE}}</p>
<p><a href="{{UNSUBSCRIBE_URL}}" style="color:#dfc986">Unsubscribe</a>{{PRIVACY_LINK}}</p>
</td></tr></table>'''


def prepare_footer(source):
    """Return one source, migrating legacy tokens and restoring missing fields.

    Insert small inline elements into the existing final cell/container, never a
    second styled footer. Draft snapshots change only on the existing save path.
    """
    if LEGACY_TOKEN in source:
        if not re.sub(r'<!--.*?-->|\{\{SYSTEM_FOOTER\}\}', '', source, flags=re.S).strip():
            return DEFAULT_FOOTER
        source = source.replace(LEGACY_TOKEN, '')
    missing = [value for token, value in REQUIRED.items() if token not in source]
    if missing:
        region = '\n'.join('<p>'+value+'</p>' for value in missing)
        # Prefer an existing table cell, then a div; malformed markup is balanced
        # by the same sanitizer before rendering and cannot escape the footer.
        closings = list(re.finditer(r'</td\s*>|</th\s*>', source, re.I))
        if not closings: closings = list(re.finditer(r'</div\s*>', source, re.I))
        at = closings[-1].start() if closings else len(source)
        source = source[:at] + '\n' + region + '\n' + source[at:]
    return source


class ComplianceMarkup(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack=[]; self.visible=set(); self.unsubscribe=False

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs); style=attrs.get('style','').lower().replace(' ','')
        hidden=bool(self.stack and self.stack[-1][1]) or bool(re.search(
            r'(?:display:none|color:transparent|(?:font-size|line-height|max-height|height|max-width|width):0(?:\.0+)?(?:px|pt|em|%|;|$))',style))
        tiny=re.search(r'(?:^|;)font-size:(\d+(?:\.\d+)?|\.\d+)(px|pt)(?:;|$)',style)
        if tiny and float(tiny.group(1))<8:hidden=True
        if tag not in {'br','hr','img'}:self.stack.append((tag,hidden,attrs))
        if not hidden and attrs.get('href')=='{{WEBSITE_URL}}':self.visible.add('{{WEBSITE_URL}}')

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:];break

    def handle_data(self, data):
        if self.stack and self.stack[-1][1]:return
        for token in REQUIRED:
            if token in data:self.visible.add(token)
        if data.strip() and any(a.get('href')=='{{UNSUBSCRIBE_URL}}' for _,_,a in self.stack):
            self.unsubscribe=True


def render_footer(source, cfg, *, images_off=False, unsubscribe_url=None):
    source=prepare_footer(source)
    markup,_,checks=import_html(source, images_off=images_off, template_links=LINK_TOKENS)
    inspector=ComplianceMarkup();inspector.feed(markup)
    checks['Footer compliance placeholders visible']=all(t in inspector.visible for t in REQUIRED if t!='{{UNSUBSCRIBE_URL}}') and inspector.unsubscribe
    if unsubscribe_url is not None and not public_https(unsubscribe_url):
        raise ValueError('Verified HTTPS unsubscribe URL required.')
    values={
        '{{BUSINESS_NAME}}':cfg.get('business',''), '{{BUSINESS_ADDRESS}}':cfg.get('postal',''),
        '{{CONTACT_EMAIL}}':cfg.get('contact',''), '{{WEBSITE_URL}}':cfg.get('website','') if public_https(cfg.get('website','')) else '',
        '{{CONTACT_URL}}':'mailto:'+cfg['contact'] if single_email(cfg.get('contact','')) else '',
        '{{UNSUBSCRIBE_URL}}':unsubscribe_url or '', '{{MARKETING_DISCLOSURE}}':DISCLOSURE,
        '{{PRIVACY_URL}}':cfg.get('privacy','') if public_https(cfg.get('privacy','')) else '',
    }
    # Inactive test unsubscribe and missing optional links become text in place,
    # not fake URLs or extra diagnostic blocks in the email design.
    for token in LINK_TOKENS:
        if not values[token]:
            markup=re.sub(r'<a\b[^>]*href="'+re.escape(token)+r'"[^>]*>(.*?)</a>',r'<span>\1</span>',markup,flags=re.S)
    if not values['{{BUSINESS_ADDRESS}}']:
        markup=re.sub(r'<p\b[^>]*>\s*\{\{BUSINESS_ADDRESS\}\}\s*</p>','',markup)
    privacy=(' · <a href="'+escape(values['{{PRIVACY_URL}}'],quote=True)+'" style="color:#dfc986">Privacy</a>') if values['{{PRIVACY_URL}}'] else ''
    markup=markup.replace('{{PRIVACY_LINK}}',privacy)
    for token,value in values.items():markup=markup.replace(token,escape(value,quote=True))
    plain=import_html(markup)[1]
    return markup,plain,checks
