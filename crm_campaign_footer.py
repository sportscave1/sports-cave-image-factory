"""Author-owned footer HTML; unsubscribe validation never changes the design."""
from html import escape
from html.parser import HTMLParser
import re

from crm_campaign_html import import_html, TEMPLATE_LINK_TOKENS
from crm_tracking import public_https
from crm_resend_marketing import single_email

LEGACY_TOKEN = '{{SYSTEM_FOOTER}}'
DISCLOSURE = 'You’re receiving this marketing email because you subscribed to Sports Cave updates.'
LINK_TOKENS = TEMPLATE_LINK_TOKENS
UNSUBSCRIBE_REQUIRED = 'Footer must contain {{UNSUBSCRIBE_URL}} before live marketing can be sent.'
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
    """Ignore the obsolete visual block at render time; never rewrite storage."""
    return source.replace(LEGACY_TOKEN, '')


class UnsubscribeMarkup(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack=[]; self.unsubscribe=False

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs); style=attrs.get('style','').lower().replace(' ','')
        hidden=bool(self.stack and self.stack[-1][1]) or bool(re.search(
            r'(?:display:none|color:transparent|(?:font-size|line-height|max-height|height|max-width|width):0(?:\.0+)?(?:px|pt|em|%|;|$))',style))
        tiny=re.search(r'(?:^|;)font-size:(\d+(?:\.\d+)?|\.\d+)(px|pt)(?:;|$)',style)
        if tiny and float(tiny.group(1))<8:hidden=True
        if tag not in {'br','hr','img'}:self.stack.append((tag,hidden,attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:];break

    def handle_data(self, data):
        if self.stack and self.stack[-1][1]:return
        if data.strip() and any(a.get('href')=='{{UNSUBSCRIBE_URL}}' for _,_,a in self.stack):
            self.unsubscribe=True


def has_unsubscribe_link(source):
    """Check sanitized footer markup, not comments, scripts or unlinked tokens."""
    markup=import_html(prepare_footer(source),template_links=LINK_TOKENS)[0]
    inspector=UnsubscribeMarkup();inspector.feed(markup);inspector.close()
    return inspector.unsubscribe


def render_footer(source, cfg, *, images_off=False, unsubscribe_url=None):
    source=prepare_footer(source)
    markup,_,checks=import_html(source, images_off=images_off, template_links=LINK_TOKENS)
    if unsubscribe_url is not None:
        if not has_unsubscribe_link(source):raise ValueError(UNSUBSCRIBE_REQUIRED)
        if not public_https(unsubscribe_url):raise ValueError('Verified HTTPS unsubscribe URL required.')
    # Resolve only placeholders explicitly present in the author's template.
    # No identity, address, disclosure, link or paragraph is ever added for them.
    values={
        '{{BUSINESS_NAME}}':cfg.get('business',''), '{{BUSINESS_ADDRESS}}':cfg.get('postal',''),
        '{{CONTACT_EMAIL}}':cfg.get('contact',''), '{{WEBSITE_URL}}':cfg.get('website','') if public_https(cfg.get('website','')) else '',
        '{{CONTACT_URL}}':'mailto:'+cfg['contact'] if single_email(cfg.get('contact','')) else '',
        '{{UNSUBSCRIBE_URL}}':unsubscribe_url or '', '{{MARKETING_DISCLOSURE}}':DISCLOSURE,
        '{{PRIVACY_URL}}':cfg.get('privacy','') if public_https(cfg.get('privacy','')) else '',
    }
    # Inactive test unsubscribe and missing optional links become text in place,
    # not fake URLs or extra diagnostic blocks in the email design.
    def inactive_link(match):
        attrs=re.sub(r'\s(?:href|target|rel)="[^"]*"','',match.group(1))
        return '<span'+attrs+'>'+match.group(2)+'</span>'
    for token in LINK_TOKENS:
        if not values[token]:
            markup=re.sub(r'<a(\s[^>]*href="'+re.escape(token)+r'"[^>]*)>(.*?)</a>',inactive_link,markup,flags=re.S)
    privacy=(' · <a href="'+escape(values['{{PRIVACY_URL}}'],quote=True)+'" style="color:#dfc986">Privacy</a>') if values['{{PRIVACY_URL}}'] else ''
    markup=markup.replace('{{PRIVACY_LINK}}',privacy)
    for token,value in values.items():markup=markup.replace(token,escape(value,quote=True))
    plain=import_html(markup)[1]
    return markup,plain,checks
