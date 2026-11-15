"""Pure per-unit eligibility and local artifact guards. No remote/local command endpoints."""
import hashlib
import json
from pathlib import Path
import print_specifications


def unit_identity(row, mapping, spec):
    required = {'order': row.get('shopify_order_id'), 'line': row.get('shopify_line_item_id'),
                'unit': row.get('allocation_index') or row.get('unit_ordinal'),
                'product': row.get('shopify_product_gid') or row.get('shopify_product_id'),
                'variant': row.get('shopify_variant_id') or row.get('variant_id'),
                'number': row.get('edition_number'), 'total': row.get('edition_total'),
                'file': mapping.get('dropbox_file_id'), 'revision': mapping.get('revision') or mapping.get('dropbox_revision'),
                'hash': mapping.get('content_hash'), 'spec': spec}
    if any(v in (None, '') for v in required.values()):
        raise ValueError('Exact order-line unit, variant and revision evidence is required')
    if any(type(required[k]) is not int or required[k] <= 0 for k in ('unit','number','total')) or required['number'] > required['total']:
        raise ValueError('Positive integer unit and assigned edition within its total are required')
    return hashlib.sha256(json.dumps(required, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def state(row, mapping=None, *, inspection=None, processor=None, artifact=None):
    if not mapping or mapping.get('verified') is not True or mapping.get('state') != 'Linked':
        return {'label': 'Needs Setup', 'reason': 'Needs PSD: no approved verified mapping. Open PSD/manual handling remains available.'}
    if row.get('duplicate_allocation_warning') or row.get('invalidated_at') or row.get('allocation_valid') is False:
        return {'label': 'Blocked', 'reason': 'Edition allocation is invalid or ambiguous.'}
    if not row.get('edition_number') or not row.get('edition_total') or not row.get('shopify_line_item_id'):
        return {'label': 'Needs Setup', 'reason': 'An exact confirmed order-line unit allocation is required.'}
    if any(type(row.get(k)) is not int or row[k] <= 0 for k in ('edition_number','edition_total')):
        return {'label': 'Blocked', 'reason': 'Assigned edition and total must be positive integers.'}
    if row.get('edition_number') > row.get('edition_total'):
        return {'label': 'Blocked', 'reason': 'Assigned edition exceeds the confirmed edition total.'}
    if inspection and inspection.get('status') not in ('Ready', 'Can Standardise'):
        return {'label': 'Needs Setup', 'reason': 'The number layer needs verified template preparation. Use Open PSD.'}
    spec = print_specifications.for_variant(row.get('variant_full') or row.get('variant_title') or row.get('variant'))
    if not print_specifications.verified(spec):
        return {'label': 'Needs Setup', 'reason': 'Supplier SKU print area, pixels, bleed and colour requirements are unverified.'}
    if row.get('allocation_valid') is not True or row.get('identity_enforced') is not True:
        return {'label': 'Needs Setup', 'reason': 'Fresh authoritative allocation-validity evidence is required.'}
    if not inspection or not inspection.get('verified_source'):
        return {'label': 'Needs Setup', 'reason': 'Verified editable number-layer evidence is missing.'}
    # Existing helper open-file capability and Studio pairing are NOT print processor authentication.
    if not processor or processor.get('authenticated') is not True or 'verifiedPrintJpgV1' not in processor.get('capabilities', []):
        return {'label': 'Needs Setup', 'reason': 'The desktop companion does not support authenticated print jobs. Use Open PSD/local owner workflow.'}
    try:
        plan = print_specifications.master_plan(row.get('variant_full') or row.get('variant_title') or row.get('variant'), inspection.get('layout'))
        if plan['status'] != 'Shared master':
            return {'label': 'Needs Setup', 'reason': plan['reason']}
        source = inspection.get('source_identity') or {}
        expected = {'product': row.get('shopify_product_gid') or row.get('shopify_product_id'),
                    'file': mapping['dropbox_file_id'], 'revision': mapping.get('revision') or mapping.get('dropbox_revision'),
                    'hash': mapping.get('content_hash')}
        if source != expected:
            return {'label': 'Blocked', 'reason': 'Editable-layer evidence does not match the exact product/file revision/hash.'}
        key = unit_identity(row, mapping, plan['master'])
    except ValueError as error:
        return {'label': 'Blocked', 'reason': str(error)}
    if artifact:
        if artifact.get('identity') != key:
            return {'label': 'Blocked', 'reason': 'JPG belongs to a different unit, edition, revision or specification.'}
        if artifact.get('status') == 'Generating':
            return {'label': 'Generating', 'reason': 'A bounded job already owns this unit. Duplicate generation is disabled.'}
        if artifact.get('status') == 'Blocked':
            return {'label': 'Blocked', 'reason': artifact.get('reason') or 'Artwork validation failed.'}
        if artifact.get('validated') is not True or artifact.get('quality_approved') is not True or artifact.get('print_ready') is not True:
            return {'label': 'Review', 'reason': 'Dimensions and identity checks are not print-quality approval.'}
        if artifact.get('strategy') != 'largest_approved_size_first' or artifact.get('dimensions') != plan['master']['pixel_dimensions']:
            return {'label': 'Blocked', 'reason': 'Artifact is not the approved XL master for this unit.'}
        return {'label': 'Download JPG', 'reason': 'Requires local authorised artifact verification before every download.'}
    return {'label': 'Generate JPG', 'reason': 'Generate one approved XL master for this unit; reuse for compatible smaller sizes.'}


def verified_download(record, expected_identity, actor, root, *, plan=None):
    """Local owner workflow only; never exposed as an HTTP download route."""
    from PIL import Image
    if record.get('owner') != actor or record.get('identity') != expected_identity or record.get('validated') is not True or record.get('quality_approved') is not True or record.get('print_ready') is not True:
        raise ValueError('Output identity, owner, validation and print approval are required')
    if record.get('strategy') == 'largest_approved_size_first' and (not plan or plan.get('status') != 'Shared master' or record.get('dimensions') != plan['master']['pixel_dimensions']):
        raise ValueError('Current supplier and layout compatibility must approve this XL master download')
    path = Path(record['jpg']).resolve()
    if not path.is_relative_to(Path(root).resolve()) or path.suffix.lower() != '.jpg':
        raise ValueError('Output path outside managed local cache')
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != record.get('jpg_sha256'):
        raise ValueError('Generated JPG changed')
    with Image.open(path) as image:
        if list(image.size) != record.get('dimensions'):
            raise ValueError('Generated JPG size changed')
    return path
