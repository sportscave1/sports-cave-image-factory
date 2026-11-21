"""Do not promote obsolete saved exports into newly submitted campaigns."""
import json
import time
from uuid import NAMESPACE_URL, uuid5

from ads_ie_two_line import VERSION, active


def obsolete(result):
    # Only the automated New Ads IE format is covered by this creative release.
    return (isinstance(result, dict) and result.get('campaign_type') == 'Instant Experience'
            and result.get('platform', 'meta').lower() == 'meta'
            and result.get('workflow_mode') != 'creative_refresh'
            and bool(result.get('master_prompt')) and not active(result['master_prompt']))


def replace_unposted(value):
    """Retain old evidence and continue a distinct, deduplicated creative revision.

    Called under the existing ad worker lease, before accepting desktop events.
    A Posting receipt (including a lost submit acknowledgement) takes precedence.
    Transient recovery of a current brief never enters this path.
    """
    import ads_page
    import design_publish_ad as ads
    from meta_posting_jobs import JOBS

    if value.get('posting_id') or value.get('blocked_collection') or not obsolete(value.get('result')):
        return False
    if value['stage'] in ('complete', 'cancelled', 'failed'):
        return False
    posting_id = ads._posting_id(value['upload'])
    if JOBS.snapshot(posting_id).get('status'):
        value.update(posting_id=posting_id, stage='posting')
        ads.write(ads.PREFIX + value['upload'], value)
        return True
    old = value['result']
    # Use the unchanged production builder, never relabel an old prompt or file.
    result = ads_page.build_ads_result_record(
        old['product_name'], old['category'], old['country'], 'Instant Experience',
        product_id=old['product_id'], product_url=old['product_url'],
        variation_token=old.get('variation_token'), campaign_moment=old.get('campaign_moment'),
        product_metadata=old.get('product_metadata'),
        instant_experience_settings=old.get('instant_experience_settings'),
        recent_instant_experience_fingerprints=old.get('recent_instant_experience_fingerprints', []))
    if old.get('posting_settings'):
        result['posting_settings'] = old['posting_settings']
    identity = str(uuid5(NAMESPACE_URL, 'sports-cave-creative-revision:' + value['upload'] + ':' + VERSION))
    replacement = dict(source='new_ads', upload=identity, requester=value['requester'],
        sport=value['sport'], country=value['country'], stage='waiting', result=result,
        product_gid='gid://shopify/Product/' + str(old['product_id']).rsplit('/', 1)[-1],
        handle=value['handle'], creative_revision_of=value['upload'])
    if value.get('targeting'):
        replacement['targeting'] = value['targeting']
    with ads.connect() as conn, conn.cursor() as cur:
        # Product/market deduplication also covers a newer successful manual run.
        cur.execute("""SELECT value->>'upload' AS id FROM app_settings a
            WHERE a.key LIKE %s AND a.key<>%s
              AND a.value->'result'->>'product_url'=%s
              AND a.value->>'country'=%s AND a.value->>'sport'=%s
              AND a.value->>'stage' NOT IN ('cancelled','failed')
              AND position(%s in a.value->'result'->>'master_prompt')>0
              AND NOT EXISTS (SELECT 1 FROM app_settings c
                  WHERE c.key='ads_job_control:' || (a.value->>'upload')
                  AND c.value->>'action' IN ('cancel','delete'))
            ORDER BY a.updated_at DESC LIMIT 1""",
            (ads.PREFIX+'%', ads.PREFIX+value['upload'], old['product_url'],
             value['country'], value['sport'], VERSION))
        existing = cur.fetchone()
        if existing:
            identity = existing['id']
        else:
            cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
                ON CONFLICT DO NOTHING''', (ads.PREFIX+identity, json.dumps(replacement)))
        value.update(stage='cancelled', superseded_by=identity, creative_superseded_at=time.time(),
            detail='Older creative release retained for history. Continuing the current two-line, no-badge ad workflow: '+identity)
        cur.execute('UPDATE app_settings SET value=%s::jsonb, updated_at=now() WHERE key=%s',
                    (json.dumps(value), ads.PREFIX+value['upload']))
    return True
