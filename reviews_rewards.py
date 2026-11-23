"""Rating-neutral reward eligibility. Issuance and delivery require release wiring."""
DEFAULT={'rewards_enabled':False,'image_percent':10,'video_percent':15}

def policy(value):
    result={**DEFAULT,**{k:v for k,v in value.items() if k in DEFAULT}}
    if type(result['rewards_enabled']) is not bool:raise ValueError('Invalid rewards setting.')
    for field in ('image_percent','video_percent'):
        if type(result[field]) is not int or not 1<=result[field]<=50:raise ValueError('Choose a reward from 1% to 50%.')
    return result

def eligibility(review,media,settings):
    settings=policy(settings)
    if not settings['rewards_enabled'] or review.get('source')!='sports_cave' or not review.get('verified_purchase') or not review.get('customer_id') or not review.get('order_id'):return None
    kinds={m['kind'] for m in media if m['status']=='COPIED' and m.get('consent') and m.get('approved')}
    kind='video' if 'video' in kinds else 'image' if 'image' in kinds else None
    return {'media_kind':kind,'percent':settings[kind+'_percent']} if kind else None

def register(store,identity):
    """Unique review key prevents duplicate rewards; imported history is never rewarded."""
    review=store.get_review(identity)
    candidate=eligibility(review,store.media(identity),store.collection_settings()) if review else None
    if candidate:
        store.q("""INSERT INTO sc_review_rewards(review_id,customer_id,order_id,media_kind,percent)
          VALUES(%s,%s,%s,%s,%s) ON CONFLICT(review_id) DO UPDATE SET media_kind=excluded.media_kind,
          percent=excluded.percent,status='ELIGIBLE',updated_at=now() WHERE sc_review_rewards.status IN ('ELIGIBLE','CANCELLED')""",
          (identity,review['customer_id'],review['order_id'],candidate['media_kind'],candidate['percent']))
    else:
        store.q("UPDATE sc_review_rewards SET status='CANCELLED',updated_at=now() WHERE review_id=%s AND status='ELIGIBLE'",(identity,))
    return candidate
