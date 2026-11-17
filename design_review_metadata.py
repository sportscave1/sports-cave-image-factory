"""Revision-bound metadata supplied by the Home design workflows."""
import json
import re
import uuid
from pathlib import PurePosixPath

from product_upload_dropbox import REVIEW, within
from psd_directory import REVIEW_METADATA_FOLDER
from sports_categories import (
    detect_sport_in_text, infer_sport_category, normalize_sport_category, sport_collection_handles,
)

MAX_HANDOFF_BYTES = 32 * 1024
TITLE_RENAME = '_design_review_rename'


class _StaleRevision(ValueError):
    pass


def handoff_paths(psd_path):
    """Prefer the central folder and accept a sibling sidecar during migration."""
    if not within(psd_path, REVIEW) or not psd_path.lower().endswith('.psd'):
        return ()
    legacy_path = psd_path[:-4] + '.upload.json'
    canonical_path = REVIEW_METADATA_FOLDER + '/' + PurePosixPath(legacy_path).name
    return tuple(dict.fromkeys((canonical_path, legacy_path)))


def _text(value, size=400):
    return value.strip()[:size] if isinstance(value, str) else ''


def _strings(value):
    return [item.strip()[:200] for item in value[:40] if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _json_object(raw):
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
    except (ValueError, UnicodeError) as error:
        raise ValueError('The artwork metadata is not valid JSON.') from error
    return value


def parse_handoff(raw, source):
    return _handoff_details(_json_object(raw), source)


def _handoff_details(value, source):
    mismatch = 'The artwork metadata describes a different Dropbox PSD revision.'
    if any(value.get(field) != source.get(key) for field, key in
           (('dropbox_file_id', 'id'), ('dropbox_path', 'path_display'))):
        raise ValueError(mismatch)
    if value.get('dropbox_revision') != source.get('rev'):
        if all(source.get(key) for key in ('id', 'rev', 'path_display')) and _text(value.get('dropbox_revision')):
            raise _StaleRevision(mismatch)
        raise ValueError(mismatch)
    intent = value.get('upload_intent')
    target = _text(value.get('existing_shopify_product_id'))
    if intent == 'existing_product_refresh':
        if re.fullmatch(r'[1-9][0-9]*', target):
            target = 'gid://shopify/Product/' + target
        if not re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*', target):
            raise ValueError('A refresh needs an exact existing Shopify product ID.')
    elif intent != 'new_product' or target:
        raise ValueError('The artwork metadata must identify a new product or an exact refresh target.')
    title = _text(value.get('design_title'))
    collections = _strings(value.get('intended_collections'))
    sport = _text(value.get('sport'), 100) or infer_sport_category(
        detect_sport_in_text(identifier) for identifier in collections
        if not identifier.startswith('gid://')
    )
    checks_passed = bool(title and collections and value.get('review_status') == 'ready_for_review')
    ready = checks_passed and bool(sport)
    return dict(design_name=title, product_context=_text(value.get('design_story'), 3000),
                sport=sport, athletes=_strings(value.get('athletes')),
                morning_design_job_id=_text(value.get('morning_design_job_id'), 36),
                primary_market=_text(value.get('primary_market'), 30),
                verified_collection_facts=dict(sport=sport, league=_text(value.get('league')),
                                               teams=_strings(value.get('teams'))),
                intended_collections=collections, upload_intent=intent,
                shopify_product_id=target, review_status='ready_for_review' if ready else 'needs_attention',
                review_notes=_text(value.get('review_notes'), 1000) or
                             ' '.join(_strings(value.get('review_notes')))[:1000],
                source_photographs=_strings(value.get('source_photographs')),
                signature_assets=_strings(value.get('signature_assets')),
                **({'sport_selection_pending': True} if checks_passed and not sport else {}))


def _read_sidecar(provider, metadata, *, historical=False):
    if (metadata.get('.tag') != 'file' or not metadata.get('id') or
            type(metadata.get('size')) is not int or not 0 < metadata['size'] <= MAX_HANDOFF_BYTES):
        raise ValueError('The artwork metadata file exceeds the supported size or is unavailable.')
    locator = 'rev:' + metadata['rev'] if historical else metadata['id']
    actual, response = provider.api.get_file_response(provider.token, locator)
    try:
        if any(actual.get(key) != metadata.get(key) for key in ('id', 'rev', 'size')):
            raise ValueError('The artwork metadata changed. Reload the review gallery.')
        raw = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            raw.extend(chunk)
            if len(raw) > MAX_HANDOFF_BYTES:
                raise ValueError('The artwork metadata file exceeds the supported size.')
        if len(raw) != metadata['size']:
            raise ValueError('The artwork metadata download was incomplete.')
        return _json_object(raw), actual
    finally:
        response.close()


def _find_handoff(provider, source, candidates, *, allow_stale_sport=False):
    paths = handoff_paths(source.get('path_display') or '')
    if not paths:
        return None
    if candidates is None:
        candidates = (provider.metadata_if_present(path) for path in paths)
    first_error, stale_sport, pending = None, '', (None, None)
    stale_refresh = False
    for metadata in candidates:
        if metadata:
            value = actual = None
            try:
                value, actual = _read_sidecar(provider, metadata)
                return value, actual, _handoff_details(value, source)
            except ValueError as error:
                if first_error is None:
                    first_error = error
                if allow_stale_sport and isinstance(error, _StaleRevision):
                    stale_refresh |= value.get('upload_intent') == 'existing_product_refresh'
                    if not stale_sport:
                        label = _text(value.get('sport'), 100)
                        # Match Product Uploads' separate Soccer destination.
                        stale_sport = 'Soccer' if label.casefold() == 'soccer' else normalize_sport_category(label)
                if allow_stale_sport and value and isinstance(value.get(TITLE_RENAME), dict):
                    pending = value, actual
    if stale_sport or pending[0] or stale_refresh:
        details = dict(
            design_name=PurePosixPath(source['path_display']).stem,
            sport=stale_sport, verified_collection_facts={'sport': stale_sport},
            intended_collections=list(sport_collection_handles(stale_sport)),
            review_status='needs_attention',
            review_notes='The JSON describes an earlier PSD revision. Verify the current PSD and update '
                         'its review JSON before Shopify handoff.',
        )
        if stale_refresh:
            details['refresh_target_pending'] = True
        return pending[0], pending[1], details
    if first_error is not None:
        raise first_error
    return None


def read_handoff_record(provider, source, *, candidates=None):
    record = _find_handoff(provider, source, candidates)
    return record[:2] if record else None


def read_handoff(provider, source, *, candidates=None, allow_stale_sport=False):
    record = _find_handoff(provider, source, candidates, allow_stale_sport=allow_stale_sport)
    return record[2] if record else None


def read_gallery_handoff(provider, source, candidates):
    record = _find_handoff(provider, source, candidates, allow_stale_sport=True)
    if not record:
        return None
    data, _, details = record
    if data and isinstance(data.get(TITLE_RENAME), dict):
        details['title_sync_pending'] = True
    if data and details.get('upload_intent') == 'existing_product_refresh':
        cleanup = data.get('cleanup_status')
        if cleanup in ('pending', 'complete'):
            details['cleanup_status'] = cleanup
    return details


def review_key(source):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sports-cave-review:{source['id']}:{source['rev']}"))


def is_trial(name):
    return bool(re.search(r'\btrial\b', name.rsplit('.', 1)[0], re.IGNORECASE))


def is_working_file(name):
    return is_trial(name) or bool(re.search(
        r'\b(?:staging|backup)\b|\.sports-cave-replaced-', name.rsplit('.', 1)[0], re.IGNORECASE
    ))


def is_refresh_staging(name):
    return bool(re.search(
        r' - REFRESH(?: - v[0-9]+)?(?: - EDIT-[^ ]+)? - STAGING(?: - .+)?\.psd\Z',
        name, re.IGNORECASE,
    ))


def legacy_metadata(source):
    name = source['name'].rsplit('.', 1)[0]
    from product_sport_tags import ATHLETES, key
    title_words = ' ' + key(name) + ' '
    subjects = [athlete for athlete in ATHLETES if f' {athlete} ' in title_words]
    sport = detect_sport_in_text(source['path_display']) or infer_sport_category(
        ATHLETES[athlete] for athlete in subjects
    )
    return dict(design_name=name, sport=sport, athletes=[name.title() for name in subjects],
                intended_collections=list(sport_collection_handles(sport)), review_status='review')


def resolve_review_sport(details, selected):
    """A manual choice can fill missing sport metadata without clearing unrelated checks."""
    if details.get('sport') or not selected:
        return details
    from sports_categories import CANONICAL_SPORT_CATEGORIES
    if selected not in CANONICAL_SPORT_CATEGORIES:
        raise ValueError('Choose a sport from the list.')
    updated = dict(details, sport=selected,
                   verified_collection_facts=dict(details.get('verified_collection_facts') or {}, sport=selected))
    if updated.pop('sport_selection_pending', False):
        updated['review_status'] = 'ready_for_review'
    if not updated.get('intended_collections'):
        updated['intended_collections'] = list(sport_collection_handles(selected))
    return updated
