"""Read-only resolution information. Never changes readiness or image bytes.

The existing supplier registry's printable_mm is the canvas INCLUDING declared
bleed (print_specifications._geometry). Legacy editor evidence with unknown bleed
is only an estimate. crop_bounds_px, when supplied, is the supplier's selected
rectangle in the exported file, mapped to that whole supplier canvas.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

import print_specifications


def _numbers(value, count, *, positive=True):
    return (isinstance(value, (list, tuple)) and len(value) == count
            and all(type(n) in (int, float) and math.isfinite(n)
                    and (n > 0 if positive else n >= 0) for n in value))


@lru_cache(maxsize=1)
def _editor_evidence():
    return json.loads((Path(__file__).parent / 'data/auto_editions_supplier_evidence.json').read_text())


def supplier_reference(variant='', sku=None):
    """Reuse mapped SKUs and existing verification; never derive from storefront cm."""
    mapped = print_specifications.for_variant(variant)
    if mapped and sku and mapped.get('prodigi_sku') != sku:
        return None
    sku = sku or (mapped or {}).get('prodigi_sku')
    if not sku:
        return None
    if mapped and print_specifications.verified(mapped):
        print_specifications._geometry(mapped)
        spec = dict(mapped, includes_bleed=True)
    else:
        spec = dict(_editor_evidence().get(sku) or {})
        # This existing record verifies editor dimensions, not certification.
        if not spec.get('source') or not str(spec.get('verification_status', '')).startswith('Editor dimensions confirmed'):
            return None
        if str(variant).strip().lower().startswith('unframed') and spec.get('product_kind') == 'framed':
            return None
        spec['includes_bleed'] = False
    physical = spec.get('printable_mm')
    recommendation = spec.get('recommended_ppi')
    if not _numbers(physical, 2) or type(recommendation) not in (int, float) or not math.isfinite(recommendation) or recommendation <= 0:
        return None
    return dict(sku=sku, printable_mm=list(physical), recommended_ppi=recommendation,
                pixel_dimensions=spec.get('pixel_dimensions'),
                includes_bleed=spec['includes_bleed'], source=spec['source'])


def _ppi(pixels, physical):
    return [p * 25.4 / mm for p, mm in zip(pixels, physical)]


def assess(exported_dimensions=None, *, variant='', sku=None, source_dimensions=None,
           prepared_dimensions=None, preparation_geometry=None, dpi_metadata=None,
           crop_bounds_px=None, test_only=None):
    """Pure metadata assessment; missing evidence is unknown, never inferred detail.

    Meeting the configured resolution recommendation is separate from supplier
    approval, print_ready, and a supplier's quality rating. No write or image I/O.
    """
    exported = list(exported_dimensions) if _numbers(exported_dimensions, 2) else None
    prepared = list(prepared_dimensions) if _numbers(prepared_dimensions, 2) else None
    source = list(source_dimensions) if _numbers(source_dimensions, 2) else None
    geometry = preparation_geometry if isinstance(preparation_geometry, dict) else {}
    scale = geometry.get('scale')
    provenance = bool(source and prepared and type(scale) in (int, float) and scale >= 1
                      and prepared == [n * scale for n in source]
                      and ((scale == 1 and geometry.get('method') == 'native')
                           or (scale > 1 and geometry.get('method') == 'photoshop_layered_bicubic_smoother')))
    if source and prepared and geometry.get('plan'):
        try:
            from auto_editions_preparation_geometry import validate
            validate(source,prepared,geometry)
            provenance=True
        except (ValueError,KeyError,TypeError):
            provenance=False
    spec = supplier_reference(variant, sku)
    physical = list(spec['printable_mm']) if spec else None
    if physical and exported:
        physical.sort(reverse=exported[0] >= exported[1])
    crop_known = False
    invalid_crop = crop_bounds_px is not None
    used = exported
    if exported and _numbers(crop_bounds_px, 4, positive=False):
        x0, y0, x1, y1 = crop_bounds_px
        if 0 <= x0 < x1 <= exported[0] and 0 <= y0 < y1 <= exported[1]:
            used = [x1 - x0, y1 - y0]
            crop_known, invalid_crop = True, False
    output_ppi = _ppi(used, physical) if used and physical and not invalid_crop else None
    native_ppi = None
    if output_ppi and provenance:
        # Crop covers the same fraction of the source canvas, not recovered detail.
        native_ppi = _ppi([s * u / e for s, u, e in zip(source, used, exported)], physical)
    meets = bool(output_ppi and min(output_ppi) >= spec['recommended_ppi'])
    # Honour the supplier's integer pixel requirement, including its own rounding.
    # E.g. the configured A1 9933 × 7016 canvas is ~299.998 PPI, not deficient.
    required_pixels = spec.get('pixel_dimensions') if spec else None
    if output_ppi and _numbers(required_pixels, 2):
        required_pixels = sorted(required_pixels, reverse=exported[0] >= exported[1])
        integer_requirement = all(p >= required for p, required in zip(used, required_pixels))
        rounded_recommendation = [round(mm * spec['recommended_ppi'] / 25.4) for mm in physical]
        meets = integer_requirement if required_pixels == rounded_recommendation else meets and integer_requirement
    status = ('meets_recommendation' if meets else 'below_recommendation') if output_ppi else 'not_verified'
    labels = dict(meets_recommendation='Meets configured resolution recommendation',
                  below_recommendation='Below configured resolution recommendation',
                  not_verified='Resolution not verified')
    estimate = not (crop_known and spec and spec['includes_bleed'])
    notes = []
    if not crop_known:
        notes.append('Estimate before supplier crop; actual uploaded asset, crop and zoom remain unverified.')
    if spec and not spec['includes_bleed']:
        notes.append('Supplier bleed is unknown; PPI uses the recorded print dimensions before bleed.')
    if invalid_crop:
        notes.append('Saved crop evidence is invalid; no final PPI can be calculated.')
    if not spec:
        notes.append('Verified dimensions and resolution recommendation for the selected SKU are unavailable.')
    if not exported:
        notes.append('Actual exported pixel dimensions are unknown.')
    if not provenance:
        notes.append('Legacy or incomplete source/scaling provenance: unknown.')
    if provenance and scale > 1:
        notes.append('Enlargement increases raster dimensions; it does not establish increased source detail.')
    notes.append('Source canvas size alone does not prove photographic detail. Resolution information is not supplier quality approval or an Excellent rating.')
    if status == 'below_recommendation':
        notes.append('For more detail, use the existing Open PSD action to review a better native source, or review a smaller print size with the owner. Existing download and fulfilment actions remain available.')

    def dims(value):
        return ' × '.join(f'{n:g}' for n in value) if value else 'unknown'

    def ppi_text(value):
        return ' × '.join(f'{n:.1f}' for n in value) if value else 'unknown'

    summary = labels[status] + ' · ' + (spec['sku'] if spec else sku or 'SKU unknown')
    summary += f' · export {dims(exported)} px · {ppi_text(output_ppi)} effective PPI'
    summary += ' (estimate before supplier crop)' if not crop_known else ' (recorded supplier crop)'
    if provenance and scale > 1:
        summary += f' · {scale:g}× enlargement · native-canvas {ppi_text(native_ppi)} PPI'
    details = f'Source canvas {dims(source) if provenance else "unknown"} px'
    details += f' · native-canvas PPI {ppi_text(native_ppi)} · prepared {dims(prepared)} px'
    details += f' · applied scaling {scale:g}×' if provenance else ' · applied scaling unknown'
    details += f' · selected print {dims(physical)} mm'
    details += f' · recommendation {spec["recommended_ppi"]:g} PPI' if spec else ''
    details += f' · DPI metadata {dims(dpi_metadata) if _numbers(dpi_metadata, 2) else "unknown"} (separate from effective PPI).'
    return dict(status=status, summary=summary, details=details, notes=notes,
                source_dimensions=source if provenance else None, prepared_dimensions=prepared,
                exported_dimensions=exported, scaling=scale if provenance else None,
                source_provenance='recorded' if provenance else 'unknown',
                native_canvas_ppi=native_ppi, exported_ppi=output_ppi,
                dpi_metadata=list(dpi_metadata) if _numbers(dpi_metadata, 2) else None,
                supplier=spec, crop_known=crop_known, estimate=estimate,
                output_status='TEST / NOT PRINT READY' if test_only is True else
                              'Existing supplier approval unchanged' if test_only is False else 'Output approval unknown')


def for_job(job, result):
    """Read immutable job/result snapshots, including historical archived outputs.

    Informational failures must never make existing output/download unavailable.
    No new database read, source fetch, rendering, allocation or readiness write.
    """
    try:
        manifest = job.get('manifest') or {}
        info=assess(result.get('dimensions'), variant=job.get('archive_labels', {}).get('variant_title', ''),
                      source_dimensions=manifest.get('source_dimensions'), prepared_dimensions=manifest.get('dimensions'),
                      preparation_geometry=manifest.get('preparation_geometry'), dpi_metadata=result.get('ppi_metadata'),
                      test_only=result.get('test_only'))
        plan=(manifest.get('preparation_geometry') or {}).get('plan') or {}
        if plan.get('resolution_status')=='below_target_worker_budget':
            info['notes'].append('Preparation remains below its selected target: the required proportional canvas exceeds the unchanged 95 MP worker budget. A bounded legacy result was retained; no target success is claimed.')
        return info
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return dict(status='not_verified', summary='Resolution not verified',
                    details='Resolution evidence is unavailable. Existing download and fulfilment actions remain available.',
                    notes=[], output_status='TEST / NOT PRINT READY' if isinstance(result,dict) and result.get('test_only') is True
                    else 'Output approval unchanged')


def manual_notice(row):
    """A manual upload has no known file identity: never borrow a generated file's PPI."""
    try:
        info = assess(variant=row.get('shopify_variant_title') or row.get('variant_title', ''),
                      sku=row.get('prodigi_product_code') or row.get('prodigi_code'))
        spec = info['supplier']
        target = (f'{spec["sku"]}, {spec["printable_mm"][0]:g} × {spec["printable_mm"][1]:g} mm, '
                  f'{spec["recommended_ppi"]:g} PPI recommendation') if spec else 'selected supplier size unverified'
        return ('Resolution not verified for manually selected asset — ' + target
                + '. File dimensions, effective PPI, source/scaling provenance and supplier crop are unknown. '
                'Use the archived original, not a preview. In Prodigi check the uploaded asset pixel dimensions, '
                'selected product dimensions, crop/zoom and displayed recommendation. TEST remains TEST; '
                'a completed render/download does not confer print readiness. Informational only; existing actions are unchanged.')
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return 'Resolution not verified for manually selected asset. Check original dimensions and supplier crop; existing actions are unchanged.'
