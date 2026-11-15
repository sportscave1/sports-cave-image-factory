"""Independent insertable section; recipient data exists only in rendered copies."""
from copy import deepcopy
from html import escape
from pathlib import Path
import re
from crm_wall_preview_template import product_link

IDENTITY='builtin-frame-synced-banner'
NAME='See It In Your Cave — Frame-Synced Banner'
PREFIX='SC_FRAME_BANNER_'


def library_row():return {'id':IDENTITY,'name':NAME,'version':1,'builtin':True}


def source():return (Path(__file__).parent/'templates'/'frame_synced_banner.html').read_text(encoding='utf-8')


def present(doc):
    return any(PREFIX in s.get('html','') for s in doc.get('middle_sections',[]) if s.get('visible')) if 'middle_sections' in doc else PREFIX in doc.get('custom_html','')


def resolve(doc,data=None):
    if not any(PREFIX in s.get('html','') for s in doc.get('middle_sections',[])) and PREFIX not in doc.get('custom_html',''):return doc
    result=deepcopy(doc)
    from crm_frame_banner_assets import prepare,frame_name
    # A public active product destination defines eligibility, not its position
    # in the original basket. Original checkout rows are never removed/changed.
    item=next((i for i in ((data or {}).get('items',[]) if present(doc) else []) if product_link({'items':[i]}) and
               (frame_name(i.get('variant','')) or re.search(r'\b(?:art|artwork|print|edition)\b',str(i.get('title','')),re.I))),None)
    link=product_link({'items':[item]}) if item else ''
    image=prepare(item) if item else ''
    title=str((item or {}).get('title') or '')
    variant=str((item or {}).get('variant') or '')
    visual=('<img src="'+escape(image,quote=True)+'" alt="'+escape(' — '.join(filter(None,(title,variant))),quote=True)+'" width="556" style="display:block;width:100%;max-width:556px;height:auto;margin:0 auto 14px">') if image else ''
    info=('<p style="margin:0 0 6px;color:#ffffff;font: bold 14px Arial">'+escape(title)+'</p><p style="margin:0 0 18px;color:#cccccc;font:12px Arial">'+escape(variant)+'</p>') if item else ''
    def render(value):
        if PREFIX not in value:return value
        value=value.replace('<!--SC_FRAME_BANNER_IMAGE-->',visual).replace('<!--SC_FRAME_BANNER_PRODUCT-->',info)
        if link:value=value.replace(PREFIX+'URL',escape(link,quote=True))
        else:value=re.sub(r'<a\b[^>]*\bhref\s*=\s*([\"\'])SC_FRAME_BANNER_URL\1[^>]*>.*?</a\s*>','',value,flags=re.I|re.S)
        if PREFIX in value:raise ValueError('Keep the frame banner image/product markers and complete CTA destination intact.')
        return value
    for section in result.get('middle_sections',[]):
        if section.get('type') in ('html','image'):section['html']=render(section.get('html',''))
    result['custom_html']=render(result.get('custom_html',''))
    return result
