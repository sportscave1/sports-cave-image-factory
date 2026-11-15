"""Checkout-only CSS contract. Final output still passes the shared HTML sanitizer."""
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
from crm_campaign_html import CSS

CLASSES=frozenset('sc-cart-block sc-cart-label sc-cart-image-wrap sc-cart-image sc-cart-title sc-cart-variant sc-cart-dimensions sc-cart-meta sc-cart-qty sc-cart-divider sc-cart-rule sc-cart-price sc-cart-button-wrap sc-cart-button sc-cart-extra-items'.split())
MARKER='<!--SC_ABANDONED_CHECKOUT-->'
STYLE=re.compile(r'<style\b[^>]*>(.*?)</style\s*>',re.I|re.S)


def default_html():return (Path(__file__).parent/'templates'/'abandoned_checkout_collector_reminder.html').read_text(encoding='utf-8')


def upgrade_html(source):
    """Add missing detail rules to legacy masters/drafts without changing authored rules."""
    # Only the exact previous built-in defaults are upgraded; custom values survive.
    replacements={
      '.sc-cart-variant { color:#ffffff; font-size:13px; line-height:19px; font-weight:500; margin:8px 0; }':'sc-cart-variant',
      '.sc-cart-price { color:#ffffff; font-size:14px; line-height:19px; font-weight:700; margin:8px 0; }':'sc-cart-price',
    }
    defaults=default_html()
    for previous,name in replacements.items():
        current=re.search(r'\.'+name+r'\s*\{[^{}]*\}',defaults)[0]
        source=source.replace(previous,current)
    present=rules(source,strict=False)
    additions=[]
    for selector,body in re.findall(r'(\.sc-cart-[\w-]+)\s*\{([^{}]*)\}',defaults):
        if selector[1:] in {'sc-cart-dimensions','sc-cart-qty','sc-cart-divider','sc-cart-rule'} and selector[1:] not in present:
            additions.append(selector+' {'+body+'}')
    return ('<style>\n'+'\n'.join(additions)+'\n</style>\n'+source) if additions else source


def declarations(source):
    result={}
    for line in source.split(';'):
        prop,sep,value=line.partition(':');prop=prop.strip().lower();value=value.strip()
        if not sep:
            if line.strip():raise ValueError('Invalid checkout CSS declaration.')
            continue
        important=bool(re.search(r'\s*!important\s*$',value,re.I));value=re.sub(r'\s*!important\s*$','',value,flags=re.I).strip()
        if prop not in CSS or not re.fullmatch(r'[a-zA-Z0-9#.,% ()"\'-]+',value) or re.search(r'url|expression|var\(|calc\(|-\d',value,re.I):raise ValueError('Unsupported checkout CSS property or value.')
        if prop=='display' and value not in {'block','inline','inline-block','table','table-row','table-cell','none'}:raise ValueError('Use email-safe checkout layout.')
        if prop not in result or important or not result[prop][1]:result[prop]=(value,important)
    return result


def _css_blocks(css):
    """Read balanced blocks; ordinary email media rules are outside our contract."""
    while css.strip():
        opening=css.find('{')
        if opening<0:
            yield css.strip(), None
            return
        depth=1;end=opening+1;quote=None
        while end<len(css) and depth:
            char=css[end]
            if quote:
                if char==quote and css[end-1]!='\\':quote=None
            elif char in ('"', "'"):quote=char
            elif char=='{':depth+=1
            elif char=='}':depth-=1
            end+=1
        yield css[:opening].strip(), css[opening+1:end-1] if not depth else None
        if depth:return
        css=css[end:]


def rules(source,*,strict=True):
    result={}
    def scan(css,nested=False):
        for selector,body in _css_blocks(css):
            if selector.startswith('@'):
                # Checkout media/nested rules cannot be faithfully inlined.
                if body is not None:scan(body,nested=True)
                elif strict and re.search(r'\.sc-cart-',selector):raise ValueError('Use simple .sc-cart-* checkout CSS rules.')
                continue
            if not re.search(r'\.sc-cart-[\w-]*',selector):continue
            selectors=[item.strip() for item in selector.split(',')]
            if nested or body is None or any(item not in {'.'+name for name in CLASSES} for item in selectors):
                if strict:raise ValueError('Only the checkout class contract can be styled here.')
                continue
            try:values=declarations(body)
            except ValueError:
                if strict:raise
                continue
            for item in selectors:
                existing=result.setdefault(item[1:],{})
                for prop,value in values.items():
                    if prop not in existing or value[1] or not existing[prop][1]:existing[prop]=value
    for css in STYLE.findall(source):scan(re.sub(r'/\*.*?\*/','',css,flags=re.S))
    return result


class Inline(HTMLParser):
    def __init__(self,theme):super().__init__(convert_charrefs=False);self.theme=theme;self.parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);name=attrs.get('class','');styles={}
        for key in name.split():
            for prop,value in self.theme.get(key,{}).items():
                if prop not in styles or value[1]:styles[prop]=value
        if styles:
            for prop,value in declarations(attrs.get('style','')).items():
                if prop not in styles or value[1]:styles[prop]=value
            attrs['style']=';'.join(prop+':'+value[0] for prop,value in styles.items())
        self.parts.append('<'+tag+''.join(' '+k+'="'+escape(v or '',quote=True)+'"' for k,v in attrs.items())+'>')
    def handle_endtag(self,tag):self.parts.append('</'+tag+'>')
    def handle_data(self,data):self.parts.append(data)
    def handle_entityref(self,name):self.parts.append('&'+name+';')
    def handle_charref(self,name):self.parts.append('&#'+name+';')
    def handle_comment(self,data):self.parts.append('<!--'+data+'-->')


def compile_html(source,theme):
    def consumed(match):
        css=re.sub(r'/\*.*?\*/','',match[1],flags=re.S)
        blocks=list(_css_blocks(css))
        # General/mixed styles belong to the shared email sanitizer. Only a
        # checkout-only stylesheet has been fully consumed by this inliner.
        owned={'.'+name for name in CLASSES}
        return '' if blocks and all(body is not None and all(s.strip() in owned for s in selector.split(',')) for selector,body in blocks) else match[0]
    parser=Inline(theme);parser.feed(STYLE.sub(consumed,source));parser.close();return ''.join(parser.parts)


def sources(doc):
    if 'middle_sections' in doc:return [s.get('html','') for s in doc['middle_sections'] if s.get('visible')]
    return [doc.get('custom_html','')]


def count(doc):
    return sum(s.get('type')=='abandoned_checkout_products' and s.get('visible') for s in doc.get('middle_sections',[]))+sum(source.count(MARKER) for source in sources(doc))


def compile_document(doc,*,strict=True):
    from copy import deepcopy
    result=deepcopy(doc);source='\n'.join(sources(doc))
    theme=rules(upgrade_html(source),strict=strict) if rules(source,strict=strict) else rules(default_html())
    for name,values in rules(default_html()).items():
        if name in {'sc-cart-dimensions','sc-cart-qty','sc-cart-divider','sc-cart-rule'}:theme.setdefault(name,values)
    if 'middle_sections' in result:
        for s in result['middle_sections']:
            if s.get('type') in ('html','image'):s['html']=compile_html(s['html'],theme)
        result['custom_html']=next((s['html'] for s in result['middle_sections'] if s.get('html_number')==1),'')
    else:result['custom_html']=compile_html(result.get('custom_html',''),theme)
    return result
