"""Small, cached storefront projection; archive pages are loaded on demand."""
import re

# Public provider identities preserve the existing storefront's editorial order.
FEATURED = ['f0a533af-ce9f-4114-845d-dc003032c337', 'd69b0463-04bc-412c-948a-1636353b3528', '813945ea-267e-4f52-ab71-3a2c528ce98f', '013c8326-eeb9-41c0-8a3a-07ee648bcf2a', 'feaf0032-af79-4e0f-ac04-1b6c7667f1e3', '82212abb-7957-46ff-a819-fea0c3ab6e5e', '3cea26d2-792c-42c7-a283-48e1d8cf5c54', '89dc61f0-b911-4f63-b9cc-611b81d7ba38', 'b5a0d0bd-b2ef-4b09-8932-c5412f4c57b2', '13ba01ac-03d1-40e9-97ef-b2febe31c0dc', '45104666-957d-4e50-b8ee-b313b4a0c991', '4c91276a-636b-4eae-944a-d9912d65900e', 'd2c2044f-a1f3-40e1-9930-a7e4eb16411a', 'a1d66815-137b-410b-b3b3-83caa2ac7a83', 'dd0c3c88-1708-4019-b7a8-3a36aa5bc649', 'ab612dbd-b1f1-4892-aec2-ef554c893955', 'c1fc64d3-bd69-4401-b510-24e30112cc97']
EXCLUDED = '0af86c4c-bda9-5e9a-9070-0414339b5cd8'
US_IDS = ['d69b0463-04bc-412c-948a-1636353b3528', '013c8326-eeb9-41c0-8a3a-07ee648bcf2a',
          '3cea26d2-792c-42c7-a283-48e1d8cf5c54', 'c1fc64d3-bd69-4401-b510-24e30112cc97']
US_TERMS = r'\m(nba|wnba|nfl|mlb|nhl|nascar|basketball|baseball|super bowl|kyle larson|don mattingly|babe ruth|shohei ohtani|aaron judge|ohtani|kobe|jordan|stephen curry|steph curry|lebron|wilt chamberlain|muhammad ali|mike tyson|tiger woods|tom brady|patrick mahomes|inter miami)\M'
FIELDS = 'r.id,r.source,r.source_review_id,r.review_type,r.product_title,r.reviewer_name,r.rating,r.title,r.body,r.created_at,r.verified_purchase'
VISIBLE = "r.status='PUBLISHED' AND (r.product_id IS NOT NULL OR r.review_type='STORE') AND right(COALESCE(r.source_review_id,''),36)<>%s"


def projection(store, origin, country='AU', offset=0):
    if country not in ('AU', 'US'):country='AU'
    if not isinstance(offset,int) or not 0<=offset<=50000:raise ValueError('Invalid page.')
    order="CASE WHEN r.review_type='PRODUCT' THEN 0 ELSE 1 END,r.created_at DESC,r.id DESC"
    args=[EXCLUDED]
    if country=='US':
        order="CASE WHEN right(COALESCE(r.source_review_id,''),36)<>%s AND (right(COALESCE(r.source_review_id,''),36)=ANY(%s) OR COALESCE(NULLIF(r.product_title,''),r.title||' '||r.body) ~* %s) THEN 0 ELSE 1 END,"+order
        args.extend(['f0a533af-ce9f-4114-845d-dc003032c337',US_IDS,US_TERMS])
    archive=store.q('SELECT '+FIELDS+' FROM sc_reviews r WHERE '+VISIBLE+' ORDER BY '+order+' LIMIT 6 OFFSET %s',(*args,offset))
    more=len(archive)>5;archive=archive[:5]
    featured=[]
    if offset==0:
        featured=store.q('SELECT '+FIELDS+' FROM sc_reviews r WHERE '+VISIBLE+" AND ((r.source='judgeme' AND right(r.source_review_id,36)=ANY(%s)) OR r.source='sports_cave') AND EXISTS (SELECT 1 FROM sc_review_media m WHERE m.review_id=r.id AND m.kind='image' AND m.status='COPIED' AND m.approved=true AND m.storage->>'provider'='dropbox') ORDER BY array_position(%s::text[],right(r.source_review_id,36)) NULLS LAST,r.created_at DESC,r.id DESC LIMIT 30",(EXCLUDED,FEATURED,FEATURED))
    combined={str(r['id']):r for r in archive+featured}
    media=[] if not combined else store.q("SELECT id,review_id,storage FROM sc_review_media WHERE review_id=ANY(%s::uuid[]) AND kind='image' AND status='COPIED' AND approved=true AND storage->>'provider'='dropbox' ORDER BY created_at,id",(list(combined),))
    by_review={}
    for item in media:
        variants=item['storage'].get('variants') or {}
        if not variants.get('320') or not variants.get('1280'):continue
        base=origin+'/reviews/media/'+str(item['id'])
        by_review.setdefault(str(item['review_id']),[]).append({'kind':'image','url':base+'?size=1280','thumbnail_url':base+'?size=320','poster_url':base+'?size=1280','width':variants['1280'].get('width',1280),'height':variants['1280'].get('height',1280)})
    settings=store.settings()
    def public(row):
        legacy=str(row.get('source_review_id') or '')[-36:]
        return {'id':str(row['id']),'legacy_id':legacy if row['source']=='judgeme' and re.fullmatch('[a-f0-9-]{36}',legacy) else str(row['id']),
                'reviewer_name':row['reviewer_name'],'rating':row['rating'],'title':row['title'],'body':row['body'],
                'product_title':row['product_title'],'created_at':None,'verified_purchase':bool(settings['verified'] and row['verified_purchase']),
                'media':by_review.get(str(row['id']),[])}
    histogram=store.q("SELECT rating,count(*) AS count FROM sc_reviews WHERE status='PUBLISHED' AND (product_id IS NOT NULL OR review_type='STORE') GROUP BY rating") if offset==0 else []
    return {'reviews':[public(row) for row in archive],'featured':[public(row) for row in featured],
            'summary':store.aggregate(),'histogram':[[n,next((int(r['count']) for r in histogram if r['rating']==n),0)] for n in (5,4,3,2,1)] if offset==0 else [],
            'next_offset':offset+5 if more else None}
