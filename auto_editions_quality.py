"""Fail-closed V16 production evidence. No mapping, allocation or approval writes.

Standards are owner-reviewed server configuration, never client/manifest claims.
An exact approved preparation anchors aesthetics, fonts, plaque and every number;
another artwork/revision cannot inherit its approval merely by matching geometry.
"""
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
from functools import lru_cache
from PIL import ImageCms

import auto_editions as ae

POLICY = 'auto-editions-production-v16-1'
STANDARDS = Path(__file__).parent / 'data/auto_editions_production_standards.json'

class VisualEvidenceReview(ValueError):
    """Only fixed safe comparison messages may cross the operator boundary."""


def enabled():
    return os.getenv('AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED', '').lower() == 'true'


def standards():
    stat=STANDARDS.stat()
    return _standards(str(STANDARDS),stat.st_mtime_ns,stat.st_size)


@lru_cache(maxsize=1)
def _standards(path, mtime, size):
    records = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(records, list):
        raise ValueError('Production standards configuration is invalid.')
    return records


def standard_for(manifest, records):
    matches = [s for s in records if s.get('preparation_hash') == ae.fingerprint(manifest)
               and s.get('source') == manifest.get('source') and not s.get('revoked')]
    if len(matches) != 1:
        return None
    s = matches[0]
    required = ('id', 'actor_id', 'approved_at', 'supplier_evidence', 'supplier_sku')
    if (any(not isinstance(s.get(k), str) or not s[k].strip() for k in required)
            or s.get('human_visual_approved') is not True
            or s.get('supplier_requirements_verified') is not True
            or not isinstance(s.get('variant_ids'), list) or not s['variant_ids']
            or any(not re.fullmatch(r'(?:gid://shopify/ProductVariant/)?[1-9][0-9]*', str(v)) for v in s['variant_ids'])):
        return None
    try:
        stamp = datetime.fromisoformat(s['approved_at'].replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
            return None
        spec = s['output']
        ae.dimensions(spec['dimensions'])
        for key in ('printable_mm', 'bleed_mm', 'safe_margins_mm'):
            values = spec[key]
            if (not isinstance(values, list) or len(values) != (2 if key == 'printable_mm' else 4)
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           or v < (0.001 if key == 'printable_mm' else 0) for v in values)):
                return None
        if (spec['format'] != 'JPEG' or spec['mode'] != 'RGB' or spec['dpi'] != [300, 300]
                or spec['quality'] != 100 or spec['subsampling'] != 0
                or not re.fullmatch('[a-f0-9]{64}', spec['icc_sha256'])
                or type(spec['minimum_source_ppi']) not in (int, float)
                or not math.isfinite(spec['minimum_source_ppi']) or spec['minimum_source_ppi'] < 300
                or spec.get('geometry_includes_bleed') is not True
                or spec.get('safe_area_visually_approved') is not True):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return s


def result(state, reason, manifest, standard=None, **evidence):
    return dict(status=state, reason=reason, preparation_hash=ae.fingerprint(manifest),
                source=manifest.get('source'), policy=POLICY,
                standard_id=standard.get('id') if standard else None,
                standard_hash=ae.fingerprint(standard) if standard else None,
                evidence=evidence)


@ae.serial_render
def assess(record, mapping, checkpoint, metadata, read_metadata, fetch, records, *, visual=None, compare=None):
    """Background only. Every receipt and asset is revalidated; no I/O in tables.

    read_metadata/file fetch are injected existing Dropbox services. No upload,
    source edit, supplier action or allocation is possible through this interface.
    """
    m = record['manifest']
    evidence_stage='preparation and source identity validation'
    try:
        ae.validate_manifest(m)
        digest = ae.fingerprint(m)
        if record.get('hash') != digest:
            return result('Failed', 'Immutable preparation identity differs.', m)
        source = m['source']
        import psd_directory
        original_path=str(metadata.get('path_display') or metadata.get('path_lower') or '').lower()
        if (not original_path.startswith(psd_directory.ROOT.lower()+'/')
                or not original_path.endswith('.psd')):
            return result('Needs Review', 'Original PSD is outside the approved source directory.', m)
        if (mapping.get('shopify_product_gid') != source['product_gid']
                or mapping.get('dropbox_file_id') != source['file_id']
                or checkpoint.get('product_gid') != source['product_gid']
                or checkpoint.get('file_id') != source['file_id']
                or checkpoint.get('preparation_hash') != digest
                or checkpoint.get('source') != source
                or checkpoint.get('edition_total') != m['edition_total']
                or checkpoint.get('current_total',m['edition_total']) != m['edition_total']
                or ae.source_identity(source['product_gid'], metadata) != source):
            return result('Needs Review', 'Source, mapping or preparation checkpoint changed.', m)
        if checkpoint.get('status') not in ('Blocked', 'Cloud Ready'):
            return result('Needs Review', 'Preparation has an unresolved processing state.', m)
        if checkpoint.get('conflicting_approval'):
            return result('Needs Review', 'A conflicting layout approval requires review.', m)
        # Visual-only callers supply a validated, exact owner policy. They can
        # never obtain Production Ready or a supplier certificate through it.
        standard = visual if visual is not None else standard_for(m, records)
        if not standard:
            return result('Needs Review', 'No exact owner-approved artwork and supplier standard.', m)
        spec = standard['output']
        plaque = ae.bounds(m.get('plaque_bounds'), m['dimensions'])
        region = m['number_region']
        if (not (plaque[0] <= region[0] < region[2] <= plaque[2]
                 and plaque[1] <= region[1] < region[3] <= plaque[3])
                or m.get('source_modified') is not False):
            return result('Needs Repair', 'Number placement or source preservation is invalid.', m, standard)
        if m['dimensions'] != spec['dimensions']:
            return result('Needs Repair', 'Output dimensions differ from the approved supplier geometry.', m, standard)
        if visual is None:
            ppi = [px * 25.4 / mm for px, mm in zip(m['source_dimensions'], spec['printable_mm'])]
            if min(ppi) < spec['minimum_source_ppi']:
                return result('Needs Repair', 'Native artwork resolution is below the supplier requirement.', m, standard)
        layers=m.get('source_inspection', {}).get('layers', [])
        number=[l for l in layers if (l.get('path') or [{}])[-1].get('name')==m.get('number_layer_name')]
        plaques=[l for l in layers if (l.get('path') or [{}])[-1].get('name')==m.get('plaque_layer_name')]
        if (len(number)!=1 or len(plaques)!=1 or not number[0].get('editable')
                or number[0].get('visible') is not True or plaques[0].get('visible') is not True
                or number[0].get('smart_object_chain') or plaques[0].get('smart_object_chain')):
            return result('Needs Repair', 'Original numbering and plaque roles are ambiguous.', m, standard)
        text=re.fullmatch(r'\s*(?:(?:LIMITED\s+)?EDITION\s+)?#?\s*(\d{1,6})(?:\s*/\s*|\s+of\s+)(\d{1,6})\s*',
                          str(m.get('original_text','')),re.I)
        if not text or not 1<=int(text[1])<=int(text[2])==m['edition_total']:
            return result('Needs Repair', 'Original edition text differs from the approved limit.', m, standard)
        fonts = [f for layer in layers for f in layer.get('fonts', [])]
        if not number[0].get('fonts') or not fonts or any(f.get('installed') is not True for f in fonts):
            return result('Needs Repair', 'Required original fonts are not verified.', m, standard)
        proofs = record.get('proofs') or []
        if (any(p.get('preparation_hash') != digest for p in proofs)
                or not any(p.get('outside_number_exact') is True for p in proofs)
                or not {1, m['edition_total']} <= {p.get('number') for p in proofs if p.get('pixel_exact') is True}):
            return result('Failed', 'Current placement and pixel preservation proofs are incomplete.', m, standard)
        assets = [m['master']] + [m['patches'][str(n)] for n in range(1, m['edition_total'] + 1)]
        if [a['name'] for a in assets] != ['master.png'] + [f'number-{n}.png' for n in range(1, m['edition_total'] + 1)]:
            return result('Failed', 'Prepared filenames do not identify the complete numbered range.', m, standard)
        receipts = record.get('receipts') or {}
        rows = receipts.get('assets') or []
        if (receipts.get('preparation_hash') != digest or len(rows) != len(assets)
                or len({r.get('name') for r in rows}) != len(rows)
                or len({r.get('file_id') for r in rows}) != len(rows)):
            return result('Failed', 'Prepared file receipts are missing, duplicated or unbound.', m, standard)
        by_name = {r['name']: r for r in rows}
        from auto_editions_cloud import DropboxAssets
        from PIL import Image
        with tempfile.TemporaryDirectory(prefix='sc-production-quality-') as folder:
            root = Path(folder)
            for asset in assets:
                evidence_stage='Dropbox receipt and asset checksum validation'
                receipt = by_name.get(asset['name'], {})
                fresh = read_metadata(receipt.get('file_id'))
                if (not fresh or fresh.get('id') != receipt.get('file_id')
                        or fresh.get('rev') != receipt.get('revision')
                        or type(receipt.get('bytes')) is not int or receipt['bytes'] <= 0
                        or fresh.get('size') != receipt['bytes']
                        or str(fresh.get('path_display', '')).lower() != DropboxAssets.path(digest, asset['name']).lower()):
                    return result('Failed', 'A Dropbox receipt, revision or approved location differs.', m, standard)
                path = root / asset['name']
                fetch(digest, asset, path)
                ae.asset_path(root, asset)
                if path.stat().st_size != receipt['bytes'] or ae.file_hash(path, dropbox=True) != fresh.get('content_hash'):
                    return result('Failed', 'Prepared bytes differ from the current Dropbox receipt.', m, standard)
                with Image.open(path) as image:
                    evidence_stage='ICC profile and geometry validation'
                    image.load()
                    profile = image.info.get('icc_profile', b'')
                    try:
                        if not profile:raise ValueError('Missing profile')
                        ImageCms.ImageCmsProfile(io.BytesIO(profile))
                    except (ValueError,OSError,ImageCms.PyCMSError):
                        return result('Needs Repair', 'A valid embedded supplier colour profile is required.', m, standard)
                    region = m['number_region']
                    expected = m['dimensions'] if asset is m['master'] else [region[2]-region[0], region[3]-region[1]]
                    if (image.format != 'PNG' or image.mode != 'RGB' or list(image.size) != expected
                            or ae.hashlib.sha256(profile).hexdigest() != spec['icc_sha256']):
                        return result('Needs Repair', 'Prepared colour profile, mode or dimensions are invalid.', m, standard)
            if visual is not None:
                evidence_stage='trusted original, numbered reference and Shopify comparison'
                if compare is None:raise ValueError('Independent approved references are required.')
                evidence=compare(root)
                return result('Auto Approved','Automatic visual policy verified; supplier certification remains separate.',m,standard,
                              receipts_verified=len(assets),print_ready=False,fulfilment_authorized=False,**evidence)
            # The reviewed standard pins EVERY number patch hash, not only samples.
            for number in sorted({1, m['edition_total']}):
                path = root / 'output.jpg'
                ae.render_jpg(m, root, number, path)
                verify_output(path, spec)
        return result('Production Ready', '', m, standard, receipts_verified=len(assets),
                      scope=standard['variant_ids'], supplier_sku=standard['supplier_sku'], output=spec,
                      approval_basis='exact previously human-approved artwork and supplier standard',
                      print_ready=True, fulfilment_authorized=False)
    except (ValueError, TypeError, KeyError, OSError, ImageCms.PyCMSError) as error:
        if visual is not None and isinstance(error,VisualEvidenceReview):
            return result('Needs Review',str(error),m,visual)
        if visual is not None:
            return result('Failed','Automatic visual verification failed during '+evidence_stage+'.',m,visual)
        return result('Failed', 'Production evidence could not be conclusively validated.', m)


def verify_output(path, spec):
    """Inspect encoded production output, never trust a print_ready manifest flag."""
    from PIL import Image, ImageCms, JpegImagePlugin
    import hashlib
    with Image.open(path) as image:
        image.load()
        profile = image.info.get('icc_profile', b'')
        ImageCms.ImageCmsProfile(io.BytesIO(profile))
        if (image.format != spec['format'] or image.mode != spec['mode']
                or list(image.size) != spec['dimensions']
                or list(image.info.get('dpi', ())) != spec['dpi']
                or hashlib.sha256(profile).hexdigest() != spec['icc_sha256']
                or JpegImagePlugin.get_sampling(image) != spec['subsampling']
                or any(v != 1 for table in image.quantization.values() for v in table)):
            raise ValueError('Encoded output does not meet the approved supplier requirements.')


def current_certificate(check, manifest, records):
    """Cheap local policy fence shared by listing and numbered generation."""
    if not enabled() or not check or check.get('status') != 'Production Ready':
        return False
    standard = standard_for(manifest, records)
    return bool(standard and check.get('preparation_hash') == ae.fingerprint(manifest)
                and check.get('source') == manifest['source'] and check.get('policy') == POLICY
                and check.get('standard_hash') == ae.fingerprint(standard)
                and check.get('evidence', {}).get('print_ready') is True
                and check['evidence'].get('output') == standard['output']
                and check['evidence'].get('scope') == standard['variant_ids']
                and check['evidence'].get('supplier_sku') == standard['supplier_sku']
                and check['evidence'].get('receipts_verified') == manifest['edition_total']+1)
