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


def source_cards(raw, story=None):
    """Ordered authored structures only; never infer cards from an image pool."""
    link=obj(obj(raw.get('object_story_spec')).get('link_data'))
    children=rows(link.get('child_attachments'))
    if children: return children,'object_story_spec.link_data.child_attachments'
    attachments=rows(obj(story).get('attachments'))
    groups=[a for a in attachments if rows(obj(a).get('subattachments'))]
    if len(groups)==1: return rows(obj(groups[0]).get('subattachments')),'effective_object_story_id.attachments.subattachments'
    if len(attachments)>1 and all(obj(a).get('type') in ('photo','image') for a in attachments):
        return attachments,'effective_object_story_id.attachments'
    feed=obj(raw.get('asset_feed_spec'))
    groups=rows(feed.get('carousels'))
    if len(groups)!=1: return [],'unconfirmed_ordered_structure'
    def asset(label, collection):
        name=obj(label).get('name')
        matches=[a for a in rows(feed.get(collection)) if name and any(obj(l).get('name')==name for l in rows(obj(a).get('adlabels')))]
        return obj(matches[0]) if len(matches)==1 else {}
    cards=[]
    for child in rows(obj(groups[0]).get('child_attachments')):
        child=obj(child);image=asset(child.get('image_label'),'images')
        cards.append({**child,'image_hash':image.get('hash'),'image_url':image.get('url'),
            'name':asset(child.get('title_label'),'titles').get('text'),
            'description':asset(child.get('description_label'),'descriptions').get('text'),
            'link':asset(child.get('link_url_label'),'link_urls').get('website_url'),
            'video_id':asset(child.get('video_label'),'videos').get('video_id')})
    return cards,'asset_feed_spec.carousels.child_attachments'


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
    for original_position, item in enumerate(children, 1):
        item = obj(item)
        # The flag alone never strips the last authored product. For returned
        # story attachments require an explicit terminal Page/profile attachment
        # plus Meta's end-card setting; ambiguous attachments are retained.
        if (source.startswith('effective') and link.get('multi_share_end_card') is True
                and original_position == len(children) and item.get('type') in ('profile', 'page')):
            continue
        genuine += bool(any(item.get(key) for key in ('id', 'image_hash', 'image_url', 'picture',
                                                      'name', 'title', 'link', 'url', 'media', 'target','image_label','video_label')))
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
                      'cta': cta.get('type') or '',
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
    return {'creative_id': str(raw.get('id') or ''),
            'object_story_id': str(raw.get('object_story_id') or ''),
            'effective_object_story_id': str(raw.get('effective_object_story_id') or ''),
            'creative_format': fmt,
            'creative_format_source': reason,
            'creative_format_confidence': 'deterministic' if fmt != 'UNKNOWN' else 'unconfirmed',
            'cards': cards if fmt in CAROUSEL_FORMATS else [],
            'carousel_structure_source': source, 'source_card_count': len(children),
            'shared_primary_text': link.get('message') or raw.get('body') or story.get('message') or (obj(rows(feed.get('bodies'))[0]).get('text') if len(rows(feed.get('bodies')))==1 else '') or '',
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
    if story_id and not source_cards(raw)[0]:
        try:
            story = reader.get(str(story_id), {'fields': 'id,message,attachments{type,title,description,url,target,media,subattachments.limit(100){type,title,description,url,target,media}}'})
            if not isinstance(story, dict) or not isinstance(obj(story.get('attachments')).get('data'), list):
                raise ValueError('Story attachments were not returned.')
            # An incomplete edge cannot certify an authored card sequence.
            for edge in [obj(story.get('attachments')), *[obj(obj(a).get('subattachments')) for a in rows(obj(story.get('attachments')).get('data'))]]:
                if obj(edge.get('paging')).get('next'):
                    raise ValueError('Story attachments are incomplete.')
        except Exception:
            story = {}
            warnings.append('Story attachments unavailable; format/card completeness could not be confirmed.')
    hashes = {str(obj(c).get('image_hash')) for c in source_cards(raw,story)[0] if obj(c).get('image_hash') and not obj(c).get('image_url')}
    if raw.get('image_hash') and not raw.get('image_url'):
        hashes.add(str(raw['image_hash']))
    images = {}
    if hashes:
        try:
            for row in reader.pages(config['ad_account_id'] + '/adimages', {'fields': 'hash,url,url_128', 'hashes': json.dumps(sorted(hashes))}):
                images[str(row.get('hash'))] = row.get('url') or row.get('url_128')
        except Exception:
            warnings.append('Some source image hashes could not be resolved.')
    result = normalize(raw, story, images)
    if result['creative_format']=='DYNAMIC' and (rows(obj(raw.get('asset_feed_spec')).get('carousels')) or
            'CAROUSEL' in rows(obj(raw.get('asset_feed_spec')).get('ad_formats'))):
        warnings.append('Ordered carousel source is unavailable or ambiguous. The representative thumbnail is not the complete carousel.')
    result['warnings'] = warnings
    result['raw'] = raw
    log_resolution(result)
    return result


def log_resolution(value, ad_id='', handoff_count=0):
    logging.getLogger(__name__).info('meta_creative creative_id=%s ad_id=%s detected_format=%s carousel_structure_source=%s source_card_count=%d normalized_card_count=%d resolved_card_count=%d fallback_card_count=0 handoff_card_count=%d',
        value.get('creative_id',''),ad_id,value.get('creative_format','UNKNOWN'),value.get('carousel_structure_source',''),value.get('source_card_count',0),
        len(value.get('cards') or value.get('carousel_cards') or []),sum(bool(c.get('image_url')) and not c.get('image_unavailable',False) for c in value.get('cards') or value.get('carousel_cards') or []),handoff_count)


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
    """Fragment-owned viewer: arrow navigation never re-reads Meta or the parent."""
    cards = value.get('cards') or value.get('carousel_cards') or []
    st.caption(label({**value, 'cards': cards}))
    if not cards:
        st.warning('Source cards were not retained in this legacy handoff. Reload the winner from Meta Review.')
        return
    missing=sum(c.get('image_unavailable',False) or not (c.get('image_url') or c.get('image_sha256')) for c in cards)
    if missing: st.warning(f'{missing} of {len(cards)} source cards could not be retrieved.')
    if value.get('multi_share_optimized'): st.caption('Meta may reorder delivery; source creative order is retained.')
    identity=key_prefix+'-'+fingerprint([value.get('creative_id'),[(c.get('identity'),c.get('position')) for c in cards]])[:12]
    key='meta-card-index-'+identity
    index=min(max(int(st.session_state.get(key,0)),0),len(cards)-1)
    with st.container(key='meta-source-cards-'+identity):
        st.html('<style>[class*="st-key-meta-source-cards-"]{max-width:560px;margin-left:auto;margin-right:auto} [class*="st-key-meta-source-cards-"] [data-testid="stImage"] img{max-height:320px;max-width:100%;width:auto!important;object-fit:contain} [class*="st-key-meta-source-cards-"] [data-testid="stImage"]{margin:auto;max-width:100%} [class*="st-key-meta-source-cards-"] button{min-height:40px;min-width:40px;color:#9b7727} [class*="st-key-meta-source-cards-"] button p{font-size:0} [class*="st-key-meta-source-cards-"] [data-testid="stColumn"]:nth-child(2){text-align:center}</style>')
        left,counter,right=st.columns([1,3,1],vertical_alignment='center')
        if left.button('Previous card',icon=':material/chevron_left:',disabled=index==0,key=key+'-previous'): index-=1
        if right.button('Next card',icon=':material/chevron_right:',disabled=index==len(cards)-1,key=key+'-next'): index+=1
        st.session_state[key]=index
        counter.caption(f'{index+1} / {len(cards)}')
        card=cards[index]
        st.caption(f"CARD {index+1} OF {len(cards)}")
        data,mime=None,None
        if archived and card.get('image_sha256'):
            try:
                import meta_review_store
                data,mime=meta_review_store.load_media(card['image_sha256'])
            except Exception: pass
        if data:
            st.image(data,width=320)
            from ads_refresh_reference import render_winning_image_copy
            render_winning_image_copy(data,mime)
        elif card.get('image_url'):
            st.image(card.get('thumbnail_url') or card['image_url'],width=320)
        else: st.caption(f"Card {card['position']} — image unavailable from Meta")
        if card.get('image_url'):
            st.link_button('Open full-resolution image',card.get('high_resolution_image_url') or card['image_url'])
        for field,title in (('headline','Headline'),('description','Description'),('cta','CTA'),('destination_url','Destination')):
            if card.get(field): st.text(title+': '+card[field])
