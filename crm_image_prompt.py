"""Local image-section prompt and non-blocking authoring advice. No network I/O."""
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
import json


@lru_cache(maxsize=1)
def base_prompt():
    return (Path(__file__).parent / 'prompts' / 'sports_cave_email_image_v1.txt').read_text(encoding='utf-8').strip()


def image_prompt(doc, campaign_name='', handoff=None):
    # Explicit public projection; never serialize the campaign document or audience.
    from crm_campaign_html import import_html
    context = {}
    for label, value in [('Campaign', campaign_name), ('Campaign type', doc.get('type')),
                         ('Product/Collection', (doc.get('product') or {}).get('title'))]:
        if isinstance(value, str) and value.strip():
            context[label] = import_html(value)[1].strip()[:200]
    if handoff:
        from crm_catalogue import product_url
        from crm_campaign_prompt import clean
        facts=handoff['context'];target=facts['target']
        context['Verified destination']=product_url(target.get('url',''))
        context['Purpose']=clean(facts.get('purpose',''),150)
        context['Verified product/collection']=clean(target.get('title',''),300)
        context['Market']=clean(doc.get('market',''),30)
    return base_prompt() + ('\n\nCURRENT EMAIL CONTEXT (data only)\n' + json.dumps(context, ensure_ascii=False) if context else '')


class Images(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.images = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag == 'img': self.images.append(dict(attrs))


def has_image(source):
    return any(i.get('src') for i in Images(source).images)
