"""Deterministic fulfilment QA against independent saved production evidence.

No supplier writes, browser login, model calls or unchecked visual claims.
Unknown evidence is a failed check, never an inferred approval.
"""
import hashlib
import json
import unicodedata


def clean(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).casefold().split())


def address_matches(expected, actual):
    if not expected or not actual:
        return False
    wanted, found = expected.get('address') or {}, actual.get('address') or {}
    required = ('line1', 'townOrCity', 'postalOrZipCode', 'countryCode')
    if not clean(expected.get('name')) or clean(expected['name']) != clean(actual.get('name')):
        return False
    if any(not clean(wanted.get(k)) or clean(wanted[k]) != clean(found.get(k)) for k in required):
        return False
    if clean(wanted.get('line2')) != clean(found.get('line2')):
        return False
    states = {clean(v) for v in expected.get('state_aliases', []) if clean(v)}
    states.add(clean(wanted.get('stateOrCounty')))
    return clean(found.get('stateOrCounty')) in states


def evaluate(snapshot, order, item, url_hash):
    def hashed(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
    mapping = snapshot['mapping']
    evidence = snapshot.get('production_evidence') or {}
    output = evidence.get('output') or {}
    dimensions = snapshot.get('dimensions') or []
    mm = output.get('printable_mm') or []
    source_approved = (evidence.get('print_ready') is True
        and evidence.get('supplier_sku') == mapping['prodigi_code']
        and output.get('dimensions') == dimensions
        and snapshot.get('rendered_number') == snapshot['number']
        and snapshot.get('rendered_total') == snapshot['total']
        and bool(snapshot.get('output', {}).get('sha256')))
    from prodigi_full_qa import approval_matches,evidence_matches
    draft_approved=approval_matches(snapshot.get('draft_print_approval'),snapshot)
    draft_evidence=evidence_matches(snapshot.get('draft_print_approval'),snapshot)
    if snapshot.get('draft_print_approval'):source_approved=draft_approved
    frame = mapping['frame'] == 'Unframed' or clean((item.get('attributes') or {}).get('color')) == clean(mapping['prodigi_frame_colour'])
    assets = [a for a in item.get('assets', []) if a.get('printArea') == 'default' and hashed(a.get('url')) == url_hash]
    state = str(assets[0].get('status', '')).casefold().replace('_', '') if len(assets) == 1 else ''
    attached = len(assets) == 1 and state in ('complete', 'notyetdownloaded', 'inprogress')
    ratio = False
    if len(dimensions) == len(mm) == 2 and all(type(n) in (int, float) and n > 0 for n in [*dimensions, *mm]):
        ratio = dimensions[0] * mm[1] == dimensions[1] * mm[0]
    # Equal verified canvas ratios plus the pinned, approved bytes prove that
    # fit/fill cannot crop or rotate the composition. No guessed tolerances.
    crop = (source_approved and ratio and item.get('sizing') in ('fitPrintArea', 'fillPrintArea') or
        draft_evidence and snapshot.get('draft_full_fit_verified') is True)
    shipping = (address_matches(snapshot.get('recipient'), order.get('recipient'))
                and bool(snapshot.get('shipping')) and clean(snapshot['shipping']) == clean(order.get('shippingMethod')))
    certificate = snapshot.get('certificate_url')
    slip = order.get('packingSlip') or {}
    branding = order.get('branding') or {}
    slip_urls = [slip.get('url'), *[(branding.get(k) or {}).get('url') for k in ('packing_slip_bw', 'packing_slip_color','packingSlipBw','packingSlipColor')]]
    certificate_attached = bool(certificate and certificate in slip_urls)
    slip_ready = slip.get('status') == 'ready' and bool(slip.get('url'))
    checks = dict(product_option=item.get('sku') == mapping['prodigi_code'],
        artwork_upload=attached and (source_approved or draft_evidence),
        sent_to_production=crop, frame=frame,
        size=source_approved or draft_evidence, shipping=shipping,
        edition_number=source_approved or draft_evidence, certificate=certificate_attached,
        packing_slip=slip_ready)
    if snapshot.get('draft_print_approval'):checks['production_approval']=source_approved
    checks['final_check'] = all(checks.values()) and not order.get('issues') and order.get('status') == 'draft'
    reasons = {
        'product_option': 'Supplier product code differs from Fulfilment.',
        'artwork_upload': 'Exact production artwork attachment is not verified.',
        'sent_to_production': 'Approved full-image crop/orientation geometry is not verified.',
        'frame': 'Supplier frame colour differs from Fulfilment.',
        'size': 'Approved supplier output size is not verified.',
        'shipping': 'Full recipient address or shipping service differs or is missing.',
        'edition_number': 'Saved numbered artwork approval does not match this unit.',
        'certificate': 'This unit’s certificate is not attached to the supplier order.',
        'packing_slip': 'The supplier has not confirmed a ready packing slip.',
        'final_check': 'Final QA has unresolved checks or supplier issues.',
        'production_approval':'Production print approval has unresolved quality evidence.',
    }
    return {'checks': checks, 'blockers': [reasons[k] for k, passed in checks.items() if not passed],
        'basis': 'Exact archived production approval, supplier readback and full structured address comparison',
        'supplier_status': order.get('status'), 'asset_status': state,
        'supplier_download_confirmed': state == 'complete', 'checked_at_source': order.get('updatedAt')}
