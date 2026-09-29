"""Versioned middle sections within the existing campaign JSON document."""
from copy import deepcopy
import re
import uuid

DISPLAY = ('image', 'title', 'price', 'limit', 'next', 'remaining', 'cta')


def middle_sections(doc):
    return deepcopy(doc.get('middle_sections', [dict(id='html-1', type='html', html_number=1,
                    visible=True, html=doc.get('custom_html', ''))]))


def validate_middle(sections):
    if not isinstance(sections, list) or not 1 <= len(sections) <= 20:
        raise ValueError('Use 1–20 middle sections.')
    ids, numbers = set(), set()
    for s in sections:
        if not isinstance(s, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', str(s.get('id', ''))) or s['id'] in ids:
            raise ValueError('Invalid section identity.')
        ids.add(s['id'])
        if type(s.get('visible')) is not bool: raise ValueError('Invalid section visibility.')
        common = {'id', 'type', 'visible'}
        if s.get('type') == 'html':
            if set(s) != common | {'html_number', 'html'} or type(s['html_number']) is not int or not 1 <= s['html_number'] <= 10000 or s['html_number'] in numbers or not isinstance(s['html'], str):
                raise ValueError('Invalid HTML section.')
            numbers.add(s['html_number'])
        elif s.get('type') == 'catalogue':
            from crm_catalogue import validate_snapshot
            if set(s) != common | {'products', 'settings'}: raise ValueError('Invalid catalogue section.')
            cfg = s['settings']
            if not isinstance(cfg, dict) or set(cfg) != {'columns', 'display', 'cta'} or type(cfg['columns']) is not int or cfg['columns'] not in (1, 2): raise ValueError('Choose one or two columns.')
            if not isinstance(cfg['display'], dict) or set(cfg['display']) != set(DISPLAY) or any(type(v) is not bool for v in cfg['display'].values()): raise ValueError('Invalid catalogue display settings.')
            if not isinstance(cfg['cta'], str) or not 1 <= len(cfg['cta'].strip()) <= 60: raise ValueError('Use a short CTA label.')
            products = s['products']
            if not isinstance(products, list) or len(products) > 12 or len({p.get('id') for p in products if isinstance(p, dict)}) != len(products): raise ValueError('Select up to 12 unique products per catalogue.')
            for p in products: validate_snapshot(p)
        else: raise ValueError('Only HTML and Catalogue can appear between Header and Footer.')
    if 1 not in numbers: raise ValueError('HTML Section 1 must remain; hide it instead.')
    if len({p['id'] for s in sections if s['type']=='catalogue' for p in s['products']}) > 50:
        raise ValueError('Use up to 50 unique products per campaign.')


def commit_middle(doc, sections):
    validate_middle(sections)
    doc['middle_sections'] = deepcopy(sections)
    # Compatibility mirror, never a second rendering source once sections exist.
    doc['custom_html'] = next(s['html'] for s in sections if s.get('html_number') == 1)


def apply_event(doc, event):
    sections = middle_sections(doc)
    if not isinstance(event, dict) or event.get('base') != [s['id'] for s in sections]: raise ValueError('Sections changed. Try again.')
    kind = event.get('type')
    selected = next((s for s in sections if s['id'] == event.get('id')), None)
    if kind == 'add':
        identity = uuid.uuid4().hex
        if event.get('kind') == 'html':
            sections.append(dict(id=identity, type='html', visible=True,
                html_number=max((s.get('html_number', 0) for s in sections), default=0)+1, html=''))
        elif event.get('kind') == 'catalogue':
            sections.append(dict(id=identity, type='catalogue', visible=True, products=[],
                settings={'columns':2, 'display':dict.fromkeys(DISPLAY, True), 'cta':'View the Edition'}))
        else: raise ValueError('Unknown section type.')
    elif kind == 'order':
        ids = event.get('ids')
        if not isinstance(ids, list) or len(ids) != len(sections) or set(ids) != {s['id'] for s in sections}: raise ValueError('Invalid section order.')
        by_id = {s['id']:s for s in sections}; sections = [by_id[i] for i in ids]
    elif selected is None: raise ValueError('Section not found.')
    elif kind == 'visible': selected['visible'] = event.get('visible')
    elif kind == 'html' and selected['type'] == 'html': selected['html'] = event.get('html')
    elif kind == 'settings' and selected['type'] == 'catalogue': selected['settings'] = deepcopy(event.get('settings'))
    elif kind == 'remove':
        if selected.get('html_number') == 1 or event.get('confirmed') is not True: raise ValueError('Confirm section removal. HTML Section 1 can only be hidden.')
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
    from crm_campaign_html import import_html
    from crm_catalogue import catalogue_html, product_issues
    html, text, checks = [], [], None
    present = False
    for s in middle_sections(doc):
        if not s['visible']: continue
        source = s['html'] if s['type'] == 'html' else catalogue_html(s)
        markup, plain, result = import_html(source, images_off=images_off, campaign_key=campaign_key)
        if s['type'] == 'catalogue':
            # sc-stack is the renderer's own allowlisted responsive class.
            result['Catalogue product facts valid'] = bool(s['products']) and not any(product_issues(p, s['settings']) for p in s['products'])
        present |= result.pop('HTML content present')
        checks = result if checks is None else {k:checks.get(k, True) and result.get(k, True) for k in checks.keys() | result.keys()}
        html.append(markup); text.append(plain)
    if checks is None: checks = import_html('')[2]
    checks['HTML content present'] = present
    return ''.join(html), '\n\n'.join(t for t in text if t), checks
