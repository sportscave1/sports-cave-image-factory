"""Conservative product-level preparation decisions; no artwork or allocation writes.

Layer names are hints, never placement instructions. All coordinates come from
the inspected source; ambiguous or nested roles remain disabled.
"""
import re
import auto_editions as ae

NUMBER = re.compile(r'^(\s*(?:(?:LIMITED\s+)?EDITION\s+)?#?\s*)(\d{1,6})(\s*/\s*|\s+of\s+)(\d{1,6})(\s*)$', re.I)
PLAQUES = {'SC_EDITION_PLAQUE', 'limited-edition-plaque'}
MATTING = {'SC_EDITION_MATTING', 'Matting', 'matting'}


class NeedsRepair(ValueError):
    pass


def detect(inspection, total):
    """Accept a single complete top-level editable edition, with its own plaque."""
    doc = inspection.get('document', {})
    canvas = ae.dimensions([doc.get('width_px'), doc.get('height_px')])
    rows = inspection.get('layers', [])
    candidates = []
    for row in rows:
        match = NUMBER.fullmatch(row.get('text') or '') if row.get('kind') == 'text' else None
        if match and row.get('visible'):
            candidates.append((row, match))
    if len(candidates) != 1:
        raise NeedsRepair('Exactly one visible, editable edition-number layer is required.')
    number, match = candidates[0]
    if (len(number.get('path', [])) != 1 or number.get('smart_object_chain')
            or number.get('editable') is not True or number.get('locked')):
        raise NeedsRepair('The edition number is nested, locked or not independently editable.')
    if type(total) is not int or not 1 <= total <= 1000 or int(match[4]) != total:
        raise NeedsRepair('PSD edition total differs from the authoritative product edition limit.')
    if len(str(total)) > len(match[2]):
        raise NeedsRepair('Existing number formatting cannot hold the full edition range unchanged.')
    fonts = number.get('fonts', [])
    if not fonts or any(f.get('installed') is not True for f in fonts):
        raise NeedsRepair('The exact edition-number font is unavailable.')
    plaques = [r for r in rows if len(r.get('path', [])) == 1
               and r['path'][0]['name'] in PLAQUES and r.get('visible')]
    if len(plaques) != 1:
        raise NeedsRepair('A unique recognised collector plaque is required; manual role review needed.')
    plaque = plaques[0]
    nb = ae.bounds(number.get('bounds_px'), canvas)
    pb = ae.bounds(plaque.get('bounds_px'), canvas)
    if not (pb[0] <= nb[0] < nb[2] <= pb[2] and pb[1] <= nb[1] < nb[3] <= pb[3]):
        raise NeedsRepair('The edition-number layer is not contained in its plaque.')
    return dict(number_layer=number['path'][0]['name'], plaque_layer=plaque['path'][0]['name'],
                reference_number=int(match[2]), total=total, source_dimensions=canvas,
                number_bounds=nb, plaque_bounds=pb, font=number.get('layout', {}).get('font'))


def preparation_scale(canvas):
    """Bounded proportional TEST enlargement; never supplier certification."""
    ae.dimensions(canvas)
    choices = [s for s in (1, 2, 3, 4) if canvas[0]*canvas[1]*s*s <= ae.WORKER_MAX_PIXELS]
    if not choices:
        raise NeedsRepair('Source canvas exceeds the verified worker pixel budget.')
    # Retain already-high-resolution artwork, otherwise use the largest supported
    # integer enlargement. A separate visual quality review remains mandatory.
    return 1 if min(canvas) >= 7016 else max(choices)
