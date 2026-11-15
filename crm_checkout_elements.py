"""Optional visual elements in the existing versioned middle-section document."""
from copy import deepcopy
from html import escape
import re
import uuid

TYPE = 'checkout_element'
KINDS = ('headline', 'text', 'button', 'image', 'product_image', 'lifestyle', 'edition',
         'product_name', 'variant', 'dimensions', 'quantity', 'price', 'details', 'divider', 'spacer')
ACTIONS = ('recovery', 'wall', 'product', 'custom', 'none')
DYNAMIC = {'product_image', 'lifestyle', 'edition', 'product_name', 'variant', 'dimensions', 'quantity', 'price', 'details'}


def element(kind='button', **settings):
    cfg = dict(kind=kind, text='Complete Your Order' if kind == 'button' else '', action='recovery' if kind in ('button', 'image', 'product_image', 'lifestyle') else 'none',
               url='', image_url='', alt='Sports Cave edition', product=0, position=3, align='center', size=16,
               color='#252525', background='#d1a938' if kind=='button' else '#ffffff', border_color='#d8d8d8', border=0, padding=12 if kind=='button' else 8, spacing=8,
               width=600, weight='bold' if kind=='button' else 'normal', edition_style='plain')
    cfg.update(settings)
    return dict(id=uuid.uuid4().hex, type=TYPE, visible=True, settings=cfg)


def validate(cfg):
    from crm_tracking import public_https
    from crm_campaign_html import email_image_url
    if not isinstance(cfg, dict) or set(cfg) != set(element()['settings']): raise ValueError('Invalid visual element settings.')
    if cfg['kind'] not in KINDS or cfg['action'] not in ACTIONS: raise ValueError('Choose a supported element and link action.')
    for k, maximum in (('text', 8000), ('url', 4000), ('image_url', 4000), ('alt', 250)):
        if not isinstance(cfg[k], str) or len(cfg[k]) > maximum: raise ValueError('Invalid visual element ' + k + '.')
    for k, low, high in (('product', 0, 500), ('position', 2, 4), ('size', 8, 64), ('border', 0, 8), ('padding', 0, 80), ('spacing', 0, 100), ('width', 40, 600)):
        if type(cfg[k]) is not int or not low <= cfg[k] <= high: raise ValueError('Invalid visual element ' + k + '.')
    if cfg['align'] not in ('left', 'center', 'right') or cfg['weight'] not in ('normal', 'bold') or cfg['edition_style'] not in ('plain', 'badge', 'collector'): raise ValueError('Invalid element appearance.')
    for k in ('color', 'background', 'border_color'):
        if not isinstance(cfg[k], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', cfg[k]): raise ValueError('Choose a valid colour.')
    if cfg['url'] and not public_https(cfg['url']): raise ValueError('Custom links require a public HTTPS URL.')
    from crm_recovery_links import checkout_url
    if checkout_url(cfg['url']): raise ValueError('Choose Recover Checkout instead of pasting a customer checkout URL.')
    if cfg['image_url'] and not email_image_url(cfg['image_url']): raise ValueError('Images require a durable public JPEG/PNG URL.')


def present(doc):
    return any(s.get('visible') and s.get('type') == TYPE for s in doc.get('middle_sections', []))


def checkout_required(doc):
    return any(s.get('visible') and s.get('type') == TYPE and
               (s['settings']['kind'] in DYNAMIC or s['settings']['action'] in ('recovery','wall','product'))
               for s in doc.get('middle_sections', []))


def recovery_actions(doc):
    return sum(s.get('visible') and s.get('type') == TYPE and s['settings']['action'] == 'recovery' and
               s['settings']['kind'] in ('button', 'image', 'product_image', 'lifestyle') and
               (s['settings']['kind'] != 'button' or bool(s['settings']['text'].strip())) and
               (s['settings']['kind'] != 'image' or bool(s['settings']['image_url']))
               for s in doc.get('middle_sections', []))


def render(cfg, data, *, shop=None, galleries=None):
    from crm_abandoned_checkout import edition_label, variant_details
    from crm_catalogue import price_label
    from crm_recovery_links import TOKEN
    from crm_tracking import public_https
    from crm_campaign_html import email_image_url
    from crm_wall_preview_template import product_link
    validate(cfg)
    kind = cfg['kind']; items = (data or {}).get('items', [])
    bound = kind in DYNAMIC or cfg['action'] in ('wall', 'product')
    chosen = items if cfg['product'] == 0 else items[cfg['product']-1:cfg['product']]
    if not bound: chosen = [{}]
    pieces = []; galleries = galleries if galleries is not None else {}
    style = f"color:{cfg['color']};background-color:{cfg['background']};font-size:{cfg['size']}px;font-weight:{cfg['weight']};text-align:{cfg['align']};padding:{cfg['padding']}px;border:{cfg['border']}px solid {cfg['border_color']};margin:0;line-height:1.5"
    for item in chosen:
        text = cfg['text']; image = ''; variant, dimensions = variant_details(item.get('variant'))
        price = price_label({'currency':item.get('currency'), 'price':item.get('amount')}) if item.get('amount') is not None else ''
        if kind == 'product_image': image = item.get('image', '')
        elif kind == 'image': image = cfg['image_url']
        elif kind == 'lifestyle':
            from crm_lifestyle_images import gallery
            key = item.get('product_id')
            if key not in galleries: galleries[key] = gallery({**(data or {}), 'items':[item]}, shop=shop)
            images = galleries[key]
            image = images[cfg['position']-1].get('url', '') if len(images) >= cfg['position'] else ''
        elif kind == 'edition': text = edition_label(item.get('edition'))
        elif kind == 'product_name': text = item.get('title', '')
        elif kind == 'variant': text = variant
        elif kind == 'dimensions': text = dimensions
        elif kind == 'quantity': text = 'Qty ' + str(item['quantity'])
        elif kind == 'price': text = price
        elif kind == 'details': text = '\n'.join(filter(None, (item.get('title'), variant, dimensions, 'Qty ' + str(item['quantity']), price)))
        if kind in ('image', 'product_image', 'lifestyle'):
            image = email_image_url(image)
            if not image: continue
            body = '<img src="' + escape(image, quote=True) + '" alt="' + escape(item.get('title') or cfg['alt'], quote=True) + f'" width="{cfg["width"]}" style="display:block;width:100%;max-width:{cfg["width"]}px;height:auto;border:0">'
        elif kind == 'divider': body = '<hr style="border:0;border-top:1px solid ' + cfg['border_color'] + '">'
        elif kind == 'spacer': body = '<div style="height:' + str(cfg['spacing']) + 'px">&#160;</div>'
        else:
            if not text.strip(): continue
            # When a field repeats for multiple products, name its source explicitly.
            if kind in DYNAMIC - {'product_name', 'details'} and len(chosen) > 1: text = item.get('title', '') + ' — ' + text
            body = escape(text).replace('\n', '<br>')
            if kind == 'edition' and cfg['edition_style'] != 'plain':
                label_style = 'display:inline-block;padding:4px 8px;border:1px solid ' + cfg['border_color']
                if cfg['edition_style'] == 'collector': label_style += ';letter-spacing:2px;font-weight:bold'
                body = '<span style="' + label_style + '">' + body + '</span>'
            if kind == 'headline': body = '<strong>' + body + '</strong>'
        href = ''
        if cfg['action'] == 'recovery': href = TOKEN
        elif cfg['action'] == 'wall': href = product_link({'items':[item]})
        elif cfg['action'] == 'product':
            # Reuse the existing configured-store validator; remove only its wall flag.
            from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
            wall = product_link({'items':[item]})
            if wall:
                p = urlsplit(wall); href = urlunsplit((p.scheme,p.netloc,p.path,urlencode([(k,v) for k,v in parse_qsl(p.query) if k!='sc_wall_preview']),p.fragment))
        elif cfg['action'] == 'custom': href = cfg['url']
        if cfg['action'] == 'custom' and not public_https(href): raise ValueError('Set a valid custom HTTPS link or choose No Link.')
        if href: body = '<a href="' + escape(href, quote=True) + '" style="text-decoration:none;display:inline-block;' + (style if kind=='button' else 'color:'+cfg['color']) + '">' + body + '</a>'
        elif kind=='button':body='<span style="display:inline-block;'+style+'">'+body+'</span>'
        wrapper=style if kind!='button' else 'text-align:'+cfg['align']
        pieces.append(f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="{cfg["align"]}" style="{wrapper};padding-bottom:{cfg["spacing"]}px">' + body + '</td></tr></table>')
    return ''.join(pieces)


def resolve(doc, data, *, shop=None):
    result = deepcopy(doc); galleries = {}
    for section in result.get('middle_sections', []):
        if section.get('type') == TYPE:
            html = render(section['settings'], data, shop=shop, galleries=galleries) if section['visible'] else ''
            section.pop('settings'); section.update(type='image', html=html)
    return result


def starter():
    return [element('headline', text='Your collection awaits', size=26, weight='bold'),
            element('text', text='Pick up exactly where you left off.'),
            *product_elements(), element('button', text='See It On Your Wall', action='wall')]


def product_elements():
    return [element(k) for k in ('edition', 'product_image', 'product_name', 'variant', 'dimensions', 'quantity', 'price', 'divider', 'button')]


def separate(sections, selected):
    """Explicit author action only. Never transform saved designs on editor open."""
    from crm_checkout_styles import MARKER, compile_document
    from crm_campaign_html import import_html
    index = sections.index(selected); replacements = product_elements()
    if selected['type'] in ('html', 'image'):
        if selected['html'].count(MARKER) != 1: raise ValueError('Separate one native checkout block at a time.')
        # Inline the saved legacy styles before independently balancing its two
        # surrounding fragments. Retain authored copy as ordinary HTML sections.
        before, after = compile_document({'custom_html':selected['html']})['custom_html'].split(MARKER)
        number = max((s.get('html_number', 0) for s in sections), default=0)
        fragments = []
        for fragment in (before, after):
            markup, plain, checks = import_html(fragment)
            if plain.strip() or '<img ' in markup:
                visual = text_elements(markup)
                if visual is None:
                    number += 1
                    visual = [dict(id=uuid.uuid4().hex, type='html', html_number=number, visible=selected['visible'], html=markup)]
                fragments.append(visual)
            else: fragments.append([])
        replacements = fragments[0] + replacements + fragments[1]
    for s in replacements: s['visible'] = selected['visible']
    sections[index:index+1] = replacements


def text_elements(markup):
    """Convert simple template copy on explicit separation; rich HTML stays intact."""
    from html.parser import HTMLParser
    if re.search(r'<(?:a|img|ul|ol|li|hr)\b', markup, re.I): return None
    class Copy(HTMLParser):
        def __init__(self):
            super().__init__(); self.stack=[]; self.text=[]; self.result=[]; self.style={}; self.kind='text'
        def flush(self):
            text=''.join(self.text).strip();self.text=[]
            if not text:return
            settings={}
            for source,target in (('color','color'),('background','background'),('background-color','background')):
                value=self.style.get(source,'')
                if re.fullmatch(r'#[a-fA-F0-9]{6}',value):settings[target]=value
            if self.style.get('text-align') in ('left','center','right'):settings['align']=self.style['text-align']
            size=re.fullmatch(r'(\d+)px',self.style.get('font-size',''))
            if size:settings['size']=max(8,min(64,int(size[1])))
            if self.style.get('font-weight') in ('bold','700','800','900'):settings['weight']='bold'
            self.result.append(element(self.kind,text=text,**settings))
        def handle_starttag(self,tag,attrs):
            if tag in ('p','h1','h2','h3','h4'):self.flush()
            if tag=='br':self.text.append('\n');return
            inherited=dict(self.stack[-1][1]) if self.stack else {}
            inherited.update(dict((k.strip(),v.strip()) for k,sep,v in (d.partition(':') for d in dict(attrs).get('style','').split(';')) if sep))
            self.stack.append((tag,inherited))
            if not ''.join(self.text).strip():self.style=inherited;self.kind='headline' if tag in ('h1','h2','h3','h4') else 'text'
        def handle_data(self,data):
            if not ''.join(self.text).strip() and data.strip():
                self.style=self.stack[-1][1] if self.stack else {}
                self.kind='headline' if any(t in ('h1','h2','h3','h4') for t,_ in self.stack) else 'text'
            self.text.append(data)
        def handle_endtag(self,tag):
            if tag in ('p','h1','h2','h3','h4','td','div'):self.flush()
            for i in range(len(self.stack)-1,-1,-1):
                if self.stack[i][0]==tag:del self.stack[i:];break
    parser=Copy();parser.feed(markup);parser.close();parser.flush();return parser.result
