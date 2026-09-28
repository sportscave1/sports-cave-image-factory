"""Conservative email HTML import: source is retained; only rebuilt safe markup renders.

Document wrappers and head CSS are ignored. Inline email styles are allowlisted,
and balanced markup prevents pasted HTML from escaping the locked footer wrapper.
"""
from html import escape
from html.parser import HTMLParser
import re
from crm_tracking import public_https, asset_url, campaign_link

TAGS = set('table tbody thead tfoot tr td th div p span h1 h2 h3 h4 strong b em i u s br hr a img ul ol li blockquote center'.split())
VOID = {'br', 'hr', 'img'}
CSS = set('color background-color font-family font-size font-weight font-style line-height text-align text-decoration vertical-align padding padding-top padding-bottom padding-left padding-right border border-top border-bottom border-left border-right border-color border-width border-style border-radius border-collapse border-spacing width max-width height max-height'.split())


class EmailHTML(HTMLParser):
    def __init__(self, images_off=False, campaign_key=""):
        super().__init__(convert_charrefs=True)
        self.parts=[]; self.plain=[]; self.stack=[]; self.skipped=[]
        self.images_off=images_off; self.campaign_key=campaign_key; self.links=0
        self.checks={'HTML content present':False, 'HTML contains only safe email markup':True,
                     'Image alt text complete':True, 'Images use durable public JPEG/PNG URLs':True,
                     'CTA label and HTTPS URL valid':True}

    def handle_starttag(self, tag, attrs):
        if self.skipped:
            if tag not in VOID: self.skipped.append(tag)
            return
        if tag in {'head','script','style','iframe','object','svg','math','form','template'}:
            self.skipped.append(tag)
            if tag not in {'head','style'}: self.checks['HTML contains only safe email markup']=False
            return
        if tag not in TAGS:
            if tag not in {'html','body','meta','link'}: self.checks['HTML contains only safe email markup']=False
            return
        safe=[]; attributes=dict(attrs)
        for name,value in attrs:
            value=value or ''
            if name.startswith('on'):
                self.checks['HTML contains only safe email markup']=False
            elif name=='style':
                styles=[]
                for declaration in value.split(';'):
                    prop,sep,val=declaration.partition(':'); prop=prop.strip().lower(); val=val.strip()
                    if sep and prop in CSS and re.fullmatch(r'[a-zA-Z0-9#.,% ()"\'-]+',val) and not re.search(r'url|expression|var\(|calc\(|-\d',val,re.I):
                        styles.append(prop+':'+val)
                safe.append(('style',';'.join(styles)))
            elif name in {'width','height','cellpadding','cellspacing','colspan','rowspan','border'} and re.fullmatch(r'\d{1,4}%?',value): safe.append((name,value))
            elif name in {'align','valign','alt','title','role'}: safe.append((name,value))
            elif name=='href' and tag=='a':
                self.checks['CTA label and HTTPS URL valid'] &= public_https(value)
                if public_https(value):
                    self.links+=1
                    value=campaign_link(value,self.campaign_key,'html_'+str(self.links),test=True) if self.campaign_key else value
                    safe.append((name,value)); self.plain.append(' '+value+' ')
            elif name=='src' and tag=='img':
                self.checks['Images use durable public JPEG/PNG URLs'] &= asset_url(value)
                if asset_url(value) and not self.images_off: safe.append((name,value))
        if tag=='img':
            self.checks['Image alt text complete'] &= bool((attributes.get('alt') or '').strip())
            self.checks['Images use durable public JPEG/PNG URLs'] &= asset_url(attributes.get('src') or '')
            self.plain.append(attributes.get('alt') or '')
        self.parts.append('<'+tag+''.join(' '+n+'="'+escape(v,quote=True)+'"' for n,v in safe)+'>')
        if tag not in VOID:self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skipped:
            if tag in self.skipped:
                del self.skipped[len(self.skipped)-1-self.skipped[::-1].index(tag):]
            return
        if tag in self.stack:
            while self.stack:
                end=self.stack.pop();self.parts.append('</'+end+'>')
                if end==tag:break
        if tag in {'p','div','tr','h1','h2','li'}:self.plain.append('\n')

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(escape(data));self.plain.append(data)
            self.checks['HTML content present'] |= bool(data.strip())


def import_html(source, *, images_off=False, campaign_key=""):
    parser=EmailHTML(images_off,campaign_key);parser.feed(source);parser.close()
    markup=''.join(parser.parts)+''.join('</'+t+'>' for t in reversed(parser.stack))
    return markup, ''.join(parser.plain).strip(), parser.checks
