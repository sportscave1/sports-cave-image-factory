"""GET-only, lazy creative resolution. Fixed cards are never asset-feed alternatives."""
import hashlib
import json
import logging
from urllib.parse import urlparse

CREATIVE_FIELDS = ('id,name,object_story_id,effective_object_story_id,object_story_spec,'
                   'asset_feed_spec,object_type,image_hash,image_url,thumbnail_url,video_id,'
                   'body,title,link_url,template_url,template_url_spec,destination_spec,call_to_action_type')


def obj(value):
    return value if isinstance(value, dict) else {}


def rows(value):
    return value if isinstance(value, list) else obj(value).get('data', []) if isinstance(obj(value).get('data'), list) else []


CAROUSEL_FORMATS = ('CAROUSEL', 'DYNAMIC_CAROUSEL')


def authored_card(item):
    return any(obj(item).get(key) for key in ('id', 'image_hash', 'image_url', 'picture',
               'name', 'title', 'link', 'url', 'media', 'target', 'video_id', 'image_label', 'video_label'))


def inline_cards(raw):
    children = rows(obj(obj(raw.get('object_story_spec')).get('link_data')).get('child_attachments'))
    return children if sum(bool(authored_card(c)) for c in children) > 1 else []


def story_complete(story):
    """Never certify a partial nested edge, including a truncated subattachment."""
    edge = obj(obj(story).get('attachments'))
    edges = [edge] + [obj(obj(a).get('subattachments')) for a in rows(edge)]
    return not any(obj(e.get('paging')).get('next') for e in edges)


def source_cards(raw, story=None):
    """Inline authoring > complete story > uniquely labelled feed; no pool pairing."""
    link = obj(obj(raw.get('object_story_spec')).get('link_data'))
    children = inline_cards(raw)
    if children:
        return children, 'object_story_spec.link_data.child_attachments'
    if obj(story).get('_incomplete') or not story_complete(story):
        return [], 'story_pagination_incomplete'
    attachments = rows(obj(story).get('attachments'))
    groups = [a for a in attachments if rows(obj(a).get('subattachments'))]
    if len(groups) == 1 and len(rows(obj(groups[0]).get('subattachments'))) > 1:
        return rows(obj(groups[0]).get('subattachments')), 'effective_object_story_id.attachments.subattachments'
    if len(groups) > 1:
        return [], 'ambiguous_story_sequences'
    if len(attachments) > 1 and all(obj(a).get('type') in ('photo', 'image') for a in attachments):
        return attachments, 'effective_object_story_id.attachments'
    feed = obj(raw.get('asset_feed_spec'))
    groups = rows(feed.get('carousels'))
    if len(groups) != 1:
        return [], 'ambiguous_asset_feed_sequences' if groups else 'unconfirmed_ordered_structure'
    cards = []
    bindings = (('image_label', 'images', 'hash', 'image_hash'),
                ('title_label', 'titles', 'text', 'name'),
                ('description_label', 'descriptions', 'text', 'description'),
                ('link_url_label', 'link_urls', 'website_url', 'link'),
                ('video_label', 'videos', 'video_id', 'video_id'))
    for child in rows(obj(groups[0]).get('child_attachments')):
        card = dict(obj(child))
        for label, collection, field, target in bindings:
            if label not in card:
                continue
            name = obj(card[label]).get('name')
            matches = [obj(a) for a in rows(feed.get(collection)) if name and
                       any(obj(l).get('name') == name for l in rows(obj(a).get('adlabels')))]
            if len(matches) != 1:
                return [], 'ambiguous_asset_feed_labels'
            asset = matches[0]
            if label == 'image_label':
                if not (asset.get('hash') or public_image(asset.get('url'))):
                    return [], 'unresolved_asset_feed_labels'
                card['image_url'] = asset.get('url')
            elif not asset.get(field):
                return [], 'unresolved_asset_feed_labels'
            if label == 'video_label':
                card['thumbnail_url'] = public_image(asset.get('thumbnail_url'))
            card[target] = asset.get(field)
        if card.get('video_id') and (card.get('image_hash') or card.get('image_url')):
            return [], 'ambiguous_asset_feed_media'
        cards.append(card)
    return cards, 'asset_feed_spec.carousels.child_attachments'


def public_image(value):
    try:
        url = urlparse(value) if isinstance(value, str) else None
        return value if url and url.scheme == 'https' and url.hostname else ''
    except ValueError:
        return ''


def canvas_evidence(value, path='creative'):
    """Only concrete Canvas destinations, not names or guessed cover formats."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('link', 'url', 'link_url', 'template_url', 'website_url') and isinstance(item, str):
                try:
                    parsed = urlparse(item)
                    host = (parsed.hostname or '').lower()
                    if (host == 'facebook.com' or host.endswith('.facebook.com')) and parsed.path.startswith('/canvas/'):
                        return path + '.' + key
                except ValueError:
                    pass
            result = canvas_evidence(item, path + '.' + key)
            if result:
                return result
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result = canvas_evidence(item, f'{path}[{index}]')
            if result:
                return result
    return ''


def normalize(raw, story=None, images=None):
    raw, story, images = obj(raw), obj(story), images or {}
    spec = obj(raw.get('object_story_spec'))
    feed = obj(raw.get('asset_feed_spec'))
    link = obj(spec.get('link_data'))
    children, source = source_cards(raw, story)
    attachments = rows(obj(story.get('attachments')).get('data'))
    cards = []
    genuine = 0
    excluded_end_cards = 0
    for original_position, item in enumerate(children, 1):
        item = obj(item)
        # The flag alone never strips the last authored product. For returned
        # story attachments require an explicit terminal Page/profile attachment
        # plus Meta's end-card setting; ambiguous attachments are retained.
        if (source.startswith('effective') and link.get('multi_share_end_card') is True
                and original_position == len(children) and item.get('type') in ('profile', 'page')):
            excluded_end_cards += 1
            continue
        genuine += bool(authored_card(item))
        media, target = obj(item.get('media')), obj(item.get('target'))
        cta = obj(item.get('call_to_action'))
        destination = item.get('link') or item.get('url') or target.get('url') or obj(cta.get('value')).get('link') or ''
        image_hash = str(item.get('image_hash') or '')
        best = (public_image(item.get('image_url')) or public_image(images.get(image_hash))
                or public_image(item.get('picture')) or public_image(obj(media.get('image')).get('src'))
                or public_image(item.get('thumbnail_url')))
        position = len(cards) + 1
        source_id = str(item.get('id') or target.get('id') or image_hash or item.get('video_id') or '')
        cards.append({'position': position, 'source_position': original_position,
                      'source_id': source_id, 'identity': f"{raw.get('id', '')}:{original_position}:{source_id}",
                      'image_hash': image_hash, 'image_url': best,
                      'high_resolution_image_url': best, 'source_creative_id': str(raw.get('id') or ''),
                      'source_attachment_id': str(item.get('id') or target.get('id') or ''),
                      'role': item.get('role') or '',
                      'video_id': str(item.get('video_id') or ''),
                      'thumbnail_url': public_image(item.get('thumbnail_url')) or public_image(item.get('picture')) or best,
                      'headline': item.get('name') or item.get('title') or '',
                      'description': item.get('description') or '',
                      'link': destination,
                      'destination_url': destination,
                      'link_caption': item.get('caption') or '',
                      'cta': cta.get('type') or '', 'call_to_action': cta,
                      'image_unavailable': not bool(best)})
    ie = canvas_evidence(raw) or canvas_evidence(story, 'story')
    fmt, reason = 'UNKNOWN', 'insufficient_creative_evidence'
    if genuine > 1:
        fmt, reason = ('DYNAMIC_CAROUSEL' if obj(raw.get('asset_feed_spec')) else 'CAROUSEL'), source
    elif obj(raw.get('asset_feed_spec')):
        fmt, reason = 'DYNAMIC', 'asset_feed_spec'
    elif ie:
        fmt, reason = 'INSTANT_EXPERIENCE', ie
    elif raw.get('video_id') or obj(spec.get('video_data')).get('video_id'):
        fmt, reason = 'VIDEO', 'video_id'
    elif ((not children and (link.get('image_hash') or public_image(link.get('picture'))
                            or obj(spec.get('photo_data')).get('image_hash')))
          or not (raw.get('effective_object_story_id') or raw.get('object_story_id'))
          or (len(attachments) == 1 and obj(attachments[0]).get('type') in ('photo', 'image')
              and not obj(attachments[0]).get('subattachments'))):
        if public_image(raw.get('image_url')) or public_image(link.get('picture')) or link.get('image_hash') or raw.get('image_hash') or obj(spec.get('photo_data')).get('image_hash'):
            fmt, reason = 'SINGLE_IMAGE', 'creative.single_image_asset'
    primary_texts = [obj(b).get('text') for b in rows(feed.get('bodies'))
                     if isinstance(obj(b).get('text'), str) and obj(b)['text'].strip()]
    message = link.get('message') or raw.get('body') or story.get('message') or ''
    if message and message not in primary_texts:
        primary_texts.insert(0, message)
    incomplete = (source.startswith(('ambiguous_', 'unresolved_', 'story_pagination_'))
                  or (fmt not in CAROUSEL_FORMATS and bool(children or rows(feed.get('carousels'))
                      or 'CAROUSEL' in rows(feed.get('ad_formats')))))
    return {'creative_id': str(raw.get('id') or ''),
            'object_story_id': str(raw.get('object_story_id') or ''),
            'effective_object_story_id': str(raw.get('effective_object_story_id') or ''),
            'creative_format': fmt,
            'creative_format_source': reason,
            'creative_format_confidence': 'deterministic' if fmt != 'UNKNOWN' else 'unconfirmed',
            'cards': cards if fmt in CAROUSEL_FORMATS else [],
            'carousel_structure_source': source, 'source_card_count': len(children),
            'excluded_end_card_count': excluded_end_cards,
            'carousel_resolution_incomplete': incomplete,
            'shared_primary_texts': primary_texts,
            'shared_primary_text': link.get('message') or raw.get('body') or story.get('message') or (primary_texts[0] if primary_texts else '') or '',
            'shared_message': link.get('message') or story.get('message') or '',
            'shared_headline': link.get('name') or raw.get('title') or '',
            'shared_cta': obj(link.get('call_to_action')).get('type') or raw.get('call_to_action_type') or '',
            'multi_share_optimized': link.get('multi_share_optimized') is True,
            'multi_share_end_card': link.get('multi_share_end_card') is True,
            'image_url': public_image(raw.get('image_url')) or public_image(link.get('picture')) or public_image(images.get(str(raw.get('image_hash') or link.get('image_hash') or ''))) or public_image(raw.get('thumbnail_url'))}


def resolve(config, creative_id):
    from meta_review_live import Reader
    if not str(creative_id).isdigit():
        raise ValueError('Select a valid Meta creative identity.')
    reader = Reader(config, max_pages=10, seconds=60)
    raw = reader.get(str(creative_id), {'fields': CREATIVE_FIELDS})
    if not isinstance(raw, dict) or str(raw.get('id')) != str(creative_id):
        raise ValueError('Meta creative identity could not be verified.')
    story, warnings = {}, []
    link = obj(obj(raw.get('object_story_spec')).get('link_data'))
    story_id = raw.get('effective_object_story_id') or raw.get('object_story_id')
    story_pagination_complete = None
    if story_id and not inline_cards(raw):
        try:
            story = reader.get(str(story_id), {'fields': 'id,message,attachments{type,title,description,url,target,media,subattachments.limit(100){type,title,description,url,target,media}}'})
            if not isinstance(story, dict) or not isinstance(obj(story.get('attachments')).get('data'), list):
                raise ValueError('Story attachments were not returned.')
            # An incomplete edge cannot certify an authored card sequence.
            for edge in [obj(story.get('attachments')), *[obj(obj(a).get('subattachments')) for a in rows(obj(story.get('attachments')).get('data'))]]:
                if obj(edge.get('paging')).get('next'):
                    story_pagination_complete = False
                    raise ValueError('Story attachments are incomplete.')
            story_pagination_complete = True
        except Exception:
            story = {**story, '_incomplete': True} if story_pagination_complete is False else {}
            warnings.append('Story attachments unavailable; format/card completeness could not be confirmed.')
    hashes = {str(obj(c).get('image_hash')) for c in source_cards(raw,story)[0] if obj(c).get('image_hash') and not public_image(obj(c).get('image_url'))}
    if raw.get('image_hash') and not raw.get('image_url'):
        hashes.add(str(raw['image_hash']))
    images = {}
    if hashes:
        try:
            for row in reader.pages(config['ad_account_id'] + '/adimages', {'fields': 'hash,url,url_128', 'hashes': json.dumps(sorted(hashes))}):
                if str(row.get('hash')) in hashes:
                    images[str(row['hash'])] = public_image(row.get('url')) or public_image(row.get('url_128'))
        except Exception:
            warnings.append('Some source image hashes could not be resolved.')
    result = normalize(raw, story, images)
    if result['creative_format']=='DYNAMIC' and (rows(obj(raw.get('asset_feed_spec')).get('carousels')) or
            'CAROUSEL' in rows(obj(raw.get('asset_feed_spec')).get('ad_formats'))):
        warnings.append('Ordered carousel source is unavailable or ambiguous. The representative thumbnail is not the complete carousel.')
    result['diagnostic'] = {
        'object_story_spec_present': bool(obj(raw.get('object_story_spec'))),
        'inline_child_attachment_count': len(rows(link.get('child_attachments'))),
        'effective_object_story_id_present': bool(raw.get('effective_object_story_id')),
        'story_attachment_count': len(rows(story.get('attachments'))),
        'story_subattachment_count': sum(len(rows(obj(a).get('subattachments'))) for a in rows(story.get('attachments'))),
        'story_pagination_complete': story_pagination_complete,
        'asset_feed_spec_present': bool(obj(raw.get('asset_feed_spec'))),
        'asset_feed_carousel_group_count': len(rows(obj(raw.get('asset_feed_spec')).get('carousels'))),
        'asset_feed_carousel_child_count': sum(len(rows(obj(g).get('child_attachments'))) for g in rows(obj(raw.get('asset_feed_spec')).get('carousels'))),
        'image_hash_count': len({c['image_hash'] for c in result['cards'] if c.get('image_hash')}),
        'resolved_image_count': sum(bool(c.get('image_url')) for c in result['cards']),
    }
    result['warnings'] = warnings
    result['raw'] = raw
    log_resolution(result)
    return result


def diagnostic(value, *, campaign_id='', ad_id='', displayed_count=None, handoff_count=None):
    """Allowlisted structural evidence only: no raw Graph data or credentials."""
    keys = ('object_story_spec_present', 'inline_child_attachment_count',
            'effective_object_story_id_present', 'story_attachment_count',
            'story_subattachment_count', 'story_pagination_complete',
            'asset_feed_spec_present', 'asset_feed_carousel_group_count',
            'asset_feed_carousel_child_count', 'image_hash_count', 'resolved_image_count')
    prior = obj(value.get('diagnostic'))
    cards = value.get('cards') or value.get('carousel_cards') or []
    return {**{k: prior.get(k) for k in keys},
            'campaign_id': str(campaign_id or value.get('campaign_id') or prior.get('campaign_id') or ''),
            'ad_id': str(ad_id or value.get('ad_id') or prior.get('ad_id') or ''),
            'creative_id': str(value.get('creative_id') or ''),
            'detected_format': value.get('creative_format', 'UNKNOWN'),
            'format_source': value.get('creative_format_source', ''),
            'source_card_count': value.get('source_card_count', 0),
            'normalized_card_count': len(cards),
            'resolved_card_count': sum(bool(c.get('image_url') or c.get('image_sha256')) and not c.get('image_unavailable', False) for c in cards),
            'displayed_card_count': prior.get('displayed_card_count', 0) if displayed_count is None else displayed_count,
            'handoff_card_count': prior.get('handoff_card_count', 0) if handoff_count is None else handoff_count}


def log_resolution(value, ad_id='', handoff_count=0):
    logging.getLogger(__name__).info('meta_creative %s', json.dumps(
        diagnostic(value, ad_id=ad_id, handoff_count=handoff_count), sort_keys=True))


def render_shared_primary_text(st, value):
    from meta_carousel_view import render_primary
    render_primary(st, value)


def label(value):
    fmt = value.get('creative_format', 'UNKNOWN')
    if fmt=='DYNAMIC': return 'Dynamic / Unknown'
    return (('Dynamic Carousel' if fmt=='DYNAMIC_CAROUSEL' else 'Carousel') + ' · ' + str(len(value.get('cards') or [])) + ' cards' if fmt in CAROUSEL_FORMATS
            else fmt.replace('_', ' ').title())


def campaign_format(values):
    formats = {v.get('creative_format', 'UNKNOWN') for v in values}
    return next(iter(formats)) if len(formats) == 1 else 'MIXED' if formats else 'UNKNOWN'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def render_image_actions(st, url, identity, key_prefix='source'):
    """Meta Review links only. Copy/download remains in Creative Refresh."""
    st.link_button('Open full-resolution image', url)


import streamlit as _streamlit


@_streamlit.fragment
def render_cards(st, value, *, archived=False, key_prefix="source"):
    """Shared client-side strip; consumes resolved cards without another read."""
    from meta_carousel_view import render
    render(st, value, archived=archived, key_prefix=key_prefix)
