"""Revision-bound metadata supplied by the Home design workflows."""
import json
import re
import uuid

from product_upload_dropbox import REVIEW, within
from sports_categories import detect_sport_in_text, infer_sport_category, sport_collection_handles

MAX_HANDOFF_BYTES = 32 * 1024


def _text(value, size=400):
    return value.strip()[:size] if isinstance(value, str) else ''


def _strings(value):
    return [item.strip()[:200] for item in value[:40] if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def parse_handoff(raw, source):
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
    except (ValueError, UnicodeError) as error:
        raise ValueError('The artwork metadata is not valid JSON.') from error
    if any(value.get(field) != source.get(key) for field, key in
           (('dropbox_file_id', 'id'), ('dropbox_revision', 'rev'), ('dropbox_path', 'path_display'))):
        raise ValueError('The artwork metadata describes a different Dropbox PSD revision.')
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
                verified_collection_facts=dict(sport=sport, league=_text(value.get('league')),
                                               teams=_strings(value.get('teams'))),
                intended_collections=collections, upload_intent=intent,
                shopify_product_id=target, review_status='ready_for_review' if ready else 'needs_attention',
                review_notes=_text(value.get('review_notes'), 1000),
                source_photographs=_strings(value.get('source_photographs')),
                signature_assets=_strings(value.get('signature_assets')),
                **({'sport_selection_pending': True} if checks_passed and not sport else {}))


def read_handoff_record(provider, source, *, metadata=None):
    path = source.get('path_display') or ''
    if not within(path, REVIEW):
        return None
    sidecar = path[:-4] + '.upload.json'
    if metadata is None:
        metadata = provider.metadata_if_present(sidecar)
    if not metadata:
        return None
    if (metadata.get('.tag') != 'file' or not metadata.get('id') or
            type(metadata.get('size')) is not int or not 0 < metadata['size'] <= MAX_HANDOFF_BYTES):
        raise ValueError('The artwork metadata file exceeds the supported size or is unavailable.')
    actual, response = provider.api.get_file_response(provider.token, metadata['id'])
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
        parse_handoff(raw, source)
        return json.loads(raw), actual
    finally:
        response.close()


def read_handoff(provider, source, *, metadata=None):
    record = read_handoff_record(provider, source, metadata=metadata)
    return parse_handoff(json.dumps(record[0]), source) if record else None


def review_key(source):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sports-cave-review:{source['id']}:{source['rev']}"))


def is_trial(name):
    return bool(re.search(r'\btrial\b', name.rsplit('.', 1)[0], re.IGNORECASE))


def is_working_file(name):
    return is_trial(name) or bool(re.search(
        r'\b(?:staging|backup)\b|\.sports-cave-replaced-', name.rsplit('.', 1)[0], re.IGNORECASE
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
