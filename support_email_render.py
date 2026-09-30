"""Read-only received-mail HTML sanitizer. Never used by compose/send/drafts."""
from html import escape, unescape
from html.parser import HTMLParser
import re
from urllib.parse import unquote
from support_email_compose import _SafeHTML, safe_url

IMAGE_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}

class ImageReferences(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cids = set()
    def handle_starttag(self, tag, attrs):
        src = dict(attrs).get('src', '') or ''
        if tag == 'img' and src.lower().startswith('cid:'):
            self.cids.add(unquote(src[4:]).strip('<>'))

def referenced_cids(markup):
    parser = ImageReferences()
    parser.feed(markup or '')
    return parser.cids

class ReaderHTML(_SafeHTML):
    tags = _SafeHTML.tags | {'h1','h2','h3','h4','h5','h6','hr','pre','code','s','strike','center','font',
                            'table','thead','tbody','tfoot','tr','td','th','caption','colgroup','col','img'}
    blocked = _SafeHTML.blocked | {'form','input','button','textarea','select','applet','audio','video','noscript'}
    styles = {'color','background-color','font-family','font-size','font-weight','font-style','line-height',
              'text-align','text-decoration','letter-spacing','vertical-align','border','border-top','border-bottom',
              'border-left','border-right','border-color','border-style','border-width','border-collapse','border-spacing',
              'padding','padding-top','padding-bottom','padding-left','padding-right','margin','margin-top','margin-bottom',
              'margin-left','margin-right','width','height','max-width','list-style-type'}
    void = {'br','hr','img','col'}
    def __init__(self, inline):
        super().__init__()
        self.inline = inline or {}
    def handle_starttag(self, tag, attrs):
        if tag in self.blocked or self.hidden or tag not in self.tags:
            return super().handle_starttag(tag, attrs)
        values, clean = dict(attrs), {}
        if tag == 'a':
            url = safe_url(values.get('href'))
            if url: clean.update(href=url, target='_blank', rel='noopener noreferrer')
        if tag == 'img':
            src = values.get('src') or ''
            if src.lower().startswith('cid:'):
                src = self.inline.get(unquote(src[4:]).strip('<>'), '')
                if not re.fullmatch(r'data:image/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+', src): src = ''
            elif not (src.lower().startswith('https://') and safe_url(src)):
                src = ''
            if src:
                clean.update(src=src, loading='lazy', referrerpolicy='no-referrer')
            clean['alt'] = values.get('alt') or ('Image unavailable' if not src else '')
            if not src:
                self.out.append('<span role="img" aria-label="Image unavailable">'+escape(clean['alt'])+'</span>')
                return
        for name in ('width','height','cellpadding','cellspacing','border','colspan','rowspan'):
            value = values.get(name) or ''
            if re.fullmatch(r'\d{1,4}%?',value): clean[name]=value
        for name, allowed in [('align',{'left','right','center','justify'}),('valign',{'top','middle','bottom'}),('dir',{'ltr','rtl'})]:
            if values.get(name) in allowed: clean[name]=values[name]
        if values.get('title'): clean['title']=values['title']
        styles=[]
        for declaration in (values.get('style') or '').split(';'):
            name, _, value=declaration.partition(':')
            name,value=name.strip().lower(),value.strip()
            # No URLs, escapes, functions, comments, positioning or executable CSS.
            if name in self.styles and re.fullmatch(r"[#A-Za-z0-9 .,%'\-]+",value):
                styles.append(f'{name}:{value}')
        if tag=='font':
            for attr,css in [('color','color'),('face','font-family')]:
                if re.fullmatch(r"[#A-Za-z0-9 .,'\-]+",values.get(attr) or ''): styles.append(f'{css}:{values[attr]}')
        if styles: clean['style']=';'.join(styles)
        self.out.append('<'+tag+''.join(f' {k}="{escape(str(v),quote=True)}"' for k,v in clean.items())+'>')
        if tag not in self.void: self.stack.append(tag)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self.void: self.handle_endtag(tag)

def sanitize_received_html(markup, inline=None):
    markup=str(markup or '')
    # Decode a wholly entity-encoded HTML MIME body once, never guess HTML for text/plain.
    if '<' not in markup and re.search(r'&lt;/?(?:html|body|p|div|b|i|table)\b',markup,re.I):
        markup=unescape(markup)
    parser=ReaderHTML(inline)
    parser.feed(markup)
    return parser.finish()

def reader_document(markup):
    return '''<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-src 'none'">
<style>html,body{margin:0;padding:0;max-width:100%;overflow-wrap:anywhere}body{font:14px/1.6 Arial,sans-serif;color:#222}img{max-width:100%!important;height:auto!important}table{max-width:100%!important}pre{white-space:pre-wrap}*{box-sizing:border-box}a{overflow-wrap:anywhere}</style></head><body>'''+markup+'</body></html>'
