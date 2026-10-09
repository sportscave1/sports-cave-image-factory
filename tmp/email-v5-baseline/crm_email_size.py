"""Local production-email sizing. Hosted asset bytes never count as HTML bytes."""
from html import escape
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit
import uuid

SAFE_BYTES=80*1024
LIMIT_BYTES=95*1024
GMAIL_BYTES=102*1024
TRANSPORT_BYTES=40_000_000
LARGE_ASSET_BYTES=1024*1024
SIZE_ERROR='Email is too large for safe delivery. Reduce the email below 95 KB.'
REPRESENTATIVE_ID=str(uuid.UUID(int=1))
# No recipient lookup or generated send. Actual native URLs are rechecked at
# delivery, including URLs longer than this conservative representative value.
_UNSUBSCRIBE_BASE='https://www.sportscaveshop.com/account/unsubscribe?token='
REPRESENTATIVE_UNSUBSCRIBE=_UNSUBSCRIBE_BASE+('x'*(2000-len(_UNSUBSCRIBE_BASE)))


class Assets(HTMLParser):
    def __init__(self):
        super().__init__();self.urls=set()
    def add(self,url):
        try:
            if url and urlsplit(url).scheme=='https':self.urls.add(url)
        except ValueError:pass
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='img':self.add(attrs.get('src'))
        if attrs.get('background'):self.add(attrs['background'])


def remote_assets(html):
    parser=Assets();parser.feed(html)
    for url in re.findall(r'url\(\s*[\'"]?([^\s\)\'"]+)',html,re.I):parser.add(url)
    return sorted(parser.urls)


def analyze_rendered_email(html,text,asset_metadata=None):
    size=len(html.encode('utf-8'));urls=remote_assets(html)
    known=[asset_metadata.get(url) for url in urls] if asset_metadata else [None]*len(urls)
    known=[n for n in known if isinstance(n,int) and n>=0]
    return {'html_bytes':size,'production_html_bytes':size,'html_kb':size/1024,
            'text_bytes':len(text.encode('utf-8')),'safe_limit_bytes':LIMIT_BYTES,
            'gmail_clip_bytes':GMAIL_BYTES,
            'status':'SAFE' if size<=SAFE_BYTES else 'NEAR LIMIT' if size<=LIMIT_BYTES else 'TOO LARGE',
            'percent':min(100,size/LIMIT_BYTES*100),'asset_urls':urls,
            'remote_asset_bytes':sum(known),'largest_asset_bytes':max(known,default=0),
            'large_asset_count':sum(n>LARGE_ASSET_BYTES for n in known),
            'unknown_asset_count':len(urls)-len(known),'checked_asset_count':len(known)}


def render_production(doc,cfg,campaign_id=None,unsubscribe_url=None,send_id=None):
    from crm_campaign_content import render_campaign
    from crm_tracking import send_identity
    identity=str(campaign_id or REPRESENTATIVE_ID)
    return render_campaign(doc,cfg,production=True,
                           unsubscribe_url=unsubscribe_url or REPRESENTATIVE_UNSUBSCRIBE,
                           campaign_id=identity,send_id=send_id or send_identity(identity))


def campaign_size(doc,cfg,campaign_id=None):
    message=render_production(doc,cfg,campaign_id)
    return analyze_rendered_email(message['html'],message['text'])


def validate_rendered_email(message):
    report=analyze_rendered_email(message['html'],message['text'])
    if report['html_bytes']>LIMIT_BYTES:raise ValueError(SIZE_ERROR)
    # Separate MIME transport ceiling; remote images are excluded. Attachments
    # are not currently supported by campaign delivery: fail closed until their
    # encoded MIME/CID sizing is implemented alongside attachment transport.
    if message.get('attachments'):raise ValueError('Campaign attachment transport sizing is not supported.')
    from email.message import EmailMessage
    from email.policy import SMTP
    mime=EmailMessage(policy=SMTP)
    mime['Subject']=message.get('subject','')
    mime.set_content(message['text']);mime.add_alternative(message['html'],subtype='html')
    if len(mime.as_bytes())>TRANSPORT_BYTES:raise ValueError('Email exceeds the 40 MB transport limit.')
    return report


def size_line(report):
    return f"Email size · {report['html_kb']:.1f} KB / 95 KB · {report['status']}"


def meter_html(report):
    colour={'SAFE':'#4b7655','NEAR LIMIT':'#a47b26','TOO LARGE':'#a34b43'}[report['status']]
    assets=('Unknown' if report['unknown_asset_count'] and not report['checked_asset_count']
            else f"{report['remote_asset_bytes']/1024/1024:.1f} MB known")
    tip=(f"HTML: {report['html_kb']:.1f} KB; Plain text: {report['text_bytes']/1024:.1f} KB; "
         f"Remote assets: {assets}; Largest image: {report['largest_asset_bytes']/1024:.0f} KB; "
         f"Images checked: {report['checked_asset_count']}; Unknown: {report['unknown_asset_count']}; "
         f"{report['large_asset_count']} large image(s); Gmail clipping: ~102 KB; "
         'Sports Cave send limit: 95 KB; Resend transport maximum: 40 MB. '
         'Remote assets do not count toward HTML clipping. Recipient URL allowance included.')
    label=f"Email size {report['html_kb']:.1f} KB of 95 KB safe limit"
    return (f'<div class="sc-email-size" title="{escape(tip,quote=True)}" style="width:220px;max-width:100%;height:32px;font-size:11px;line-height:18px">'
            f'<span>Email size {report["html_kb"]:.1f} KB / 95 KB</span> '
            f'<strong style="color:{colour}">{report["status"]}</strong>'
            f'<div role="progressbar" aria-label="{label}" aria-valuemin="0" aria-valuemax="100" '
            f'aria-valuenow="{report["percent"]:.1f}" style="height:6px;background:#e8e4db;border-radius:3px;overflow:hidden">'
            f'<div style="height:6px;width:{report["percent"]:.2f}%;background:{colour}"></div></div></div>')
