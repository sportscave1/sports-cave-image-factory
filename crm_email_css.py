"""Inline simple email CSS on a render copy; the stored source is untouched.

Supported selectors: tag, .class, #id, tag.class, tag#id and comma lists.
No global stylesheet is installed, so authored rules cannot style the footer.
Media queries, descendants and active/URL CSS remain outside this contract.
"""
from html import escape
from html.parser import HTMLParser
import re

SELECTOR=re.compile(r'^(?:([a-zA-Z][\w-]*))?([.#][a-zA-Z_][\w-]*)?$')

def inline(source):
    if '<style' not in source.lower():return source
    rules=[]
    for sheet in re.findall(r'<style\b[^>]*>(.*?)</style\s*>',source,re.S|re.I):
        sheet=re.sub(r'/\*.*?\*/','',sheet,flags=re.S)
        if '@' in sheet:continue
        for selectors,body in re.findall(r'([^{}]+)\{([^{}]*)\}',sheet):
            for selector in selectors.split(','):
                match=SELECTOR.fullmatch(selector.strip())
                if not match or not any(match.groups()):continue
                tag,qualifier=match.groups();specificity=100 if qualifier and qualifier[0]=='#' else 10 if qualifier else 0
                rules.append((specificity+bool(tag),len(rules),tag.lower() if tag else None,qualifier,body))
    if not rules:return source
    rules.sort(key=lambda r:r[:2])
    class Renderer(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False);self.edits=[];self.lines=[0]+[m.end() for m in re.finditer('\n',source)]
        def handle_starttag(self,tag,attrs):
            values=dict(attrs);styles=[]
            for _,__,target,qualifier,body in rules:
                if target and target!=tag:continue
                if qualifier and (values.get('id')!=qualifier[1:] if qualifier[0]=='#' else qualifier[1:] not in (values.get('class') or '').split()):continue
                styles.append(body)
            if not styles:return
            raw=self.get_starttag_text();raw=re.sub(r'\sstyle\s*=\s*(?:"[^"]*"|\x27[^\x27]*\x27|[^\s>]+)','',raw,flags=re.I)
            suffix='/>' if raw.endswith('/>') else '>'
            rendered=raw[:-len(suffix)]+' style="'+escape(';'.join(styles+[values.get('style') or '']),quote=True)+'"'+suffix
            line,column=self.getpos();start=self.lines[line-1]+column
            self.edits.append((start,start+len(self.get_starttag_text()),rendered))
        handle_startendtag=handle_starttag
    parser=Renderer();parser.feed(source);parser.close()
    for start,end,value in reversed(parser.edits):source=source[:start]+value+source[end:]
    return source
