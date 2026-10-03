"""Checkout-only CSS contract. Final output still passes the shared HTML sanitizer."""
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
from crm_campaign_html import CSS

CLASSES=frozenset('sc-cart-block sc-cart-label sc-cart-image-wrap sc-cart-image sc-cart-title sc-cart-variant sc-cart-meta sc-cart-price sc-cart-button-wrap sc-cart-button sc-cart-extra-items'.split())
MARKER='<!--SC_ABANDONED_CHECKOUT-->'
STYLE=re.compile(r'<style\b[^>]*>(.*?)</style\s*>',re.I|re.S)


def default_html():return (Path(__file__).parent/'templates'/'abandoned_checkout_collector_reminder.html').read_text(encoding='utf-8')


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


def rules(source):
    result={}
    for css in STYLE.findall(source):
        css=re.sub(r'/\*.*?\*/','',css,flags=re.S)
        while css.strip():
            match=re.match(r'\s*([^{}]+)\{([^{}]*)\}',css)
            if not match:raise ValueError('Use simple .sc-cart-* checkout CSS rules.')
            values=declarations(match[2])
            for selector in match[1].split(','):
                name=selector.strip().removeprefix('.')
                if selector.strip()!='.'+name or name not in CLASSES:raise ValueError('Only the checkout class contract can be styled here.')
                existing=result.setdefault(name,{})
                for prop,value in values.items():
                    if prop not in existing or value[1] or not existing[prop][1]:existing[prop]=value
            css=css[match.end():]
    return result


class Inline(HTMLParser):
    def __init__(self,theme):super().__init__(convert_charrefs=False);self.theme=theme;self.parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);name=attrs.get('class','');styles={}
        for key in name.split():
            for prop,value in self.theme.get(key,{}).items():
                if prop not in styles or value[1] or not styles[prop][1]:styles[prop]=value
        if styles:
            for prop,value in declarations(attrs.get('style','')).items():
                if prop not in styles or value[1] or not styles[prop][1]:styles[prop]=value
            attrs['style']=';'.join(prop+':'+value[0] for prop,value in styles.items())
        self.parts.append('<'+tag+''.join(' '+k+'="'+escape(v or '',quote=True)+'"' for k,v in attrs.items())+'>')
    def handle_endtag(self,tag):self.parts.append('</'+tag+'>')
    def handle_data(self,data):self.parts.append(data)
    def handle_entityref(self,name):self.parts.append('&'+name+';')
    def handle_charref(self,name):self.parts.append('&#'+name+';')
    def handle_comment(self,data):self.parts.append('<!--'+data+'-->')


def compile_html(source,theme):
    parser=Inline(theme);parser.feed(STYLE.sub('',source));parser.close();return ''.join(parser.parts)


def sources(doc):
    if 'middle_sections' in doc:return [s.get('html','') for s in doc['middle_sections'] if s.get('visible')]
    return [doc.get('custom_html','')]


def count(doc):
    return sum(s.get('type')=='abandoned_checkout_products' and s.get('visible') for s in doc.get('middle_sections',[]))+sum(source.count(MARKER) for source in sources(doc))


def compile_document(doc):
    from copy import deepcopy
    result=deepcopy(doc);source='\n'.join(sources(doc));theme=rules(source) or rules(default_html())
    if 'middle_sections' in result:
        for s in result['middle_sections']:
            if s.get('type') in ('html','image'):s['html']=compile_html(s['html'],theme)
        result['custom_html']=next((s['html'] for s in result['middle_sections'] if s.get('html_number')==1),'')
    else:result['custom_html']=compile_html(result.get('custom_html',''),theme)
    return result
