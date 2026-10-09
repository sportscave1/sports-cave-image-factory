"""Versioned middle sections within the existing campaign JSON document."""
from copy import deepcopy
import re
import uuid

DISPLAY = ('image', 'title', 'price', 'limit', 'next', 'remaining', 'cta')


def middle_sections(doc):
    result=deepcopy(doc.get('middle_sections', [dict(id='html-1', type='html', html_number=1,
                    visible=True, html=doc.get('custom_html', ''))]))
    for s in result:
        if s.get('type')=='catalogue':
            s['settings'].setdefault('headline','');s['settings'].setdefault('subtext','')
    return result


def validate_middle(sections):
    if not isinstance(sections, list):
        raise ValueError('Invalid middle sections.')
    ids, numbers = set(), set()
    for s in sections:
        if not isinstance(s, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', str(s.get('id', ''))) or s['id'] in ids:
            raise ValueError('Invalid section identity.')
        ids.add(s['id'])
        if type(s.get('visible')) is not bool: raise ValueError('Invalid section visibility.')
        common = {'id', 'type', 'visible'}
        if 'name' in s:
            if not isinstance(s['name'],str) or len(s['name'])>80:raise ValueError('Use a section name of up to 80 characters.')
            common.add('name')
        if s.get('type') == 'html':
            if set(s) != common | {'html_number', 'html'} or type(s['html_number']) is not int or not 1 <= s['html_number'] <= 10000 or s['html_number'] in numbers or not isinstance(s['html'], str):
                raise ValueError('Invalid HTML section.')
            numbers.add(s['html_number'])
        elif s.get('type') == 'image':
            if set(s) != common | {'html'} or not isinstance(s['html'], str):
                raise ValueError('Invalid Image section.')
        elif s.get('type') == 'abandoned_checkout_products':
            if set(s)!=common:raise ValueError('Invalid abandoned checkout section.')
        elif s.get('type') == 'checkout_element':
            from crm_checkout_elements import validate
            if set(s) != common | {'settings'}: raise ValueError('Invalid visual element.')
            validate(s['settings'])
        elif s.get('type') == 'catalogue':
            from crm_catalogue import validate_snapshot
            if set(s) != common | {'products', 'settings'}: raise ValueError('Invalid catalogue section.')
            cfg = s['settings']
            if not isinstance(cfg, dict) or not {'columns','display','cta'} <= set(cfg) or set(cfg)-{'columns','display','cta','headline','subtext'} or type(cfg['columns']) is not int or cfg['columns'] not in (1, 2): raise ValueError('Choose one or two columns.')
            if not isinstance(cfg['display'], dict) or set(cfg['display']) != set(DISPLAY) or any(type(v) is not bool for v in cfg['display'].values()): raise ValueError('Invalid catalogue display settings.')
            if not isinstance(cfg['cta'], str) or not 1 <= len(cfg['cta'].strip()) <= 60: raise ValueError('Use a short CTA label.')
            for field,limit in (('headline',80),('subtext',180)):
                if not isinstance(cfg.get(field,''),str) or len(cfg.get(field,''))>limit:raise ValueError('Invalid catalogue '+field+'.')
            products = s['products']
            if not isinstance(products, list) or len(products) > 12 or len({p.get('id') for p in products if isinstance(p, dict)}) != len(products): raise ValueError('Select up to 12 unique products per catalogue.')
            for p in products: validate_snapshot(p)
        else: raise ValueError('Only HTML, Image and Catalogue can appear between Header and Footer.')
    if len({p['id'] for s in sections if s['type']=='catalogue' for p in s['products']}) > 50:
        raise ValueError('Use up to 50 unique products per campaign.')


def commit_middle(doc, sections):
    validate_middle(sections)
    doc['middle_sections'] = deepcopy(sections)
    # Compatibility mirror, never a second rendering source once sections exist.
    doc['custom_html'] = next((s['html'] for s in sections if s.get('html_number') == 1), '')


def apply_event(doc, event):
    sections = middle_sections(doc)
    if not isinstance(event, dict) or event.get('base') != [s['id'] for s in sections]: raise ValueError('Sections changed. Try again.')
    # Structural actions include unsaved textarea edits in the same transaction.
    edits = event.get('edits', {})
    if not isinstance(edits, dict): raise ValueError('Invalid pending edits.')
    for identity, html in edits.items():
        target = next((s for s in sections if s['id'] == identity and s['type'] in ('html','image')), None)
        if target is None or not isinstance(html,str): raise ValueError('Invalid pending edit.')
        target['html'] = html
    kind = event.get('type')
    selected = next((s for s in sections if s['id'] == event.get('id')), None)
    if kind == 'add':
        identity = uuid.uuid4().hex
        if event.get('kind') == 'visual':
            from crm_checkout_elements import element
            sections.append(element())
        elif event.get('kind') == 'flexible_checkout':
            from crm_checkout_elements import starter
            sections.extend(starter())
        elif event.get('kind') == 'html':
            reserved = event.get('reserved_html_number', 0)
            if type(reserved) is not int or not 0 <= reserved <= 10000: raise ValueError('Invalid reserved section number.')
            sections.append(dict(id=identity, type='html', visible=True,
                html_number=max(reserved,max((s.get('html_number', 0) for s in sections), default=0))+1, html=''))
        elif event.get('kind') == 'image':
            sections.append(dict(id=identity, type='image', visible=True, html=''))
        elif event.get('kind') == 'catalogue':
            sections.append(dict(id=identity, type='catalogue', visible=True, products=[],
                settings={'headline':'','subtext':'','columns':2, 'display':{field:field!='price' for field in DISPLAY}, 'cta':'Claim Your Edition'}))
        else: raise ValueError('Unknown section type.')
    elif kind == 'order':
        ids = event.get('ids')
        if not isinstance(ids, list) or len(ids) != len(sections) or set(ids) != {s['id'] for s in sections}: raise ValueError('Invalid section order.')
        by_id = {s['id']:s for s in sections}; sections = [by_id[i] for i in ids]
    elif kind == 'restore_section':
        restored = deepcopy(event.get('section'))
        position = event.get('position')
        if not isinstance(restored,dict) or any(s['id']==restored.get('id') for s in sections) or type(position) is not int or position<0:
            raise ValueError('Section cannot be restored here.')
        sections.insert(min(position,len(sections)),restored)
    elif selected is None: raise ValueError('Section not found.')
    elif kind == 'rename':
        name=event.get('name')
        if not isinstance(name,str):raise ValueError('Invalid section name.')
        if not name.strip() and not event.get('reset'):raise ValueError('Enter a section name or reset to default.')
        selected['name']='' if event.get('reset') else name.strip()
    elif kind == 'duplicate':
        copied=deepcopy(selected);copied['id']=uuid.uuid4().hex
        if copied['type']=='html':copied['html_number']=max(s.get('html_number',0) for s in sections)+1
        sections.insert(sections.index(selected)+1,copied)
    elif kind == 'visible': selected['visible'] = event.get('visible')
    elif kind == 'html' and selected['type'] in ('html', 'image'): selected['html'] = event.get('html')
    elif kind == 'settings' and selected['type'] in ('catalogue','checkout_element'): selected['settings'] = deepcopy(event.get('settings'))
    elif kind == 'separate_checkout':
        from crm_checkout_elements import separate
        if selected['type'] not in ('html','image','abandoned_checkout_products'): raise ValueError('Select a native checkout block.')
        separate(sections, selected)
    elif kind == 'remove':
        if event.get('confirmed') is not True: raise ValueError('Confirm section removal.')
        sections.remove(selected)
    elif kind in ('product_order', 'product_remove') and selected['type'] == 'catalogue':
        products = selected['products']; ids = event.get('ids')
        if kind == 'product_remove': selected['products'] = [p for p in products if p['id'] != event.get('product_id')]
        elif isinstance(ids, list) and len(ids) == len(products) and set(ids) == {p['id'] for p in products}:
            by_id = {p['id']:p for p in products}; selected['products'] = [by_id[i] for i in ids]
        else: raise ValueError('Invalid product order.')
    else: raise ValueError('Unknown section action.')
    commit_middle(doc, sections)


def render_middle(doc, *, images_off=False, campaign_key=''):
    from crm_checkout_elements import checkout_required, resolve as resolve_elements
    if checkout_required(doc):raise ValueError('Resolve checkout data before rendering this automation.')
    doc=resolve_elements(doc,None)
    from crm_lifestyle_images import resolve as resolve_lifestyle
    doc=resolve_lifestyle(doc)
    from crm_frame_banner_template import resolve as resolve_banner
    doc=resolve_banner(doc)
    from crm_campaign_html import import_html
    from crm_catalogue import catalogue_html, product_issues
    html, text, checks = [], [], None
    present = False
    for s in middle_sections(doc):
        if not s['visible']: continue
        if s['type'] in ('abandoned_checkout_products','checkout_element'):raise ValueError('Resolve checkout data before rendering this automation.')
        if 'SC_CHECKOUT_RECOVERY_URL' in s.get('html',''):raise ValueError('Resolve the original checkout recovery link before rendering this email.')
        if 'SC_ABANDONED_CHECKOUT' in s.get('html',''):raise ValueError('Abandoned Checkout requires a checkout recovery automation. Campaign recipients have no checkout context.')
        if 'SC_WALL_PREVIEW_URL' in s.get('html',''):raise ValueError('Resolve the wall preview product link before rendering this email.')
        source = s['html'] if s['type'] in ('html', 'image') else catalogue_html(s, campaign_key=campaign_key)
        # Generated catalogue links already share one tracked product destination.
        markup, plain, result = import_html(source, images_off=images_off,
            campaign_key=campaign_key if s['type'] in ('html', 'image') else '',trusted_catalogue=s['type']=='catalogue')
        if s['type'] == 'image':
            from crm_image_prompt import has_image
            result['HTML content present'] |= has_image(markup)
        if s['type'] == 'catalogue':
            # sc-stack is the renderer's own allowlisted responsive class.
            result['Catalogue product facts valid'] = bool(s['products']) and not any(product_issues(p, s['settings']) for p in s['products'])
        present |= result.pop('HTML content present')
        checks = result if checks is None else {k:checks.get(k, True) and result.get(k, True) for k in checks.keys() | result.keys()}
        html.append(markup); text.append(plain)
    if checks is None: checks = import_html('')[2]
    checks['HTML content present'] = present
    return ''.join(html), '\n\n'.join(t for t in text if t), checks
