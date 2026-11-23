"""Authenticated release helper: import an archived CSV with existing Dropbox media.

No CLI/automatic production connection. The release operator supplies an
authenticated OS user, ReviewsStore and verified manifest. The manifest contains
no customer email; originals and WebP variants are already in Dropbox.
"""
import hashlib
import json
import re

from reviews_import import read_csv
from reviews_model import normalize,auto_mapping
from reviews_store import require,actor
from reviews_dropbox import ReviewDropboxStorage

def import_archive(store,user,csv_data,manifest,source_store,storage=None):
    require(user)
    if manifest.get('version')!=1 or manifest.get('csv_sha256')!=hashlib.sha256(csv_data).hexdigest():raise ValueError('The review CSV does not match the Dropbox archive manifest.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*\.myshopify\.com',source_store):raise ValueError('Provide the verified source store domain.')
    headers,rows=read_csv(csv_data);mapping=auto_mapping(headers);items=[]
    archive={}
    for entry in manifest.get('media',[]):
        key=(entry['row'],entry['source_url'])
        if key in archive:raise ValueError('Duplicate archived media association.')
        archive[key]=entry
    used=set();backend=storage or ReviewDropboxStorage()
    for number,raw in enumerate(rows,2):
        item=normalize(raw,'judgeme',mapping,source_store)
        if item['status']!='PUBLISHED':continue
        for media in item['media']:
            key=(number,media['source_url']);entry=archive.get(key)
            if not entry or entry['kind']!=media['kind']:raise ValueError('A review attachment has no matching Dropbox source.')
            source=entry['storage']
            if source.get('provider')!='dropbox':raise ValueError('Review media must be in Dropbox.')
            variants=source.get('posters' if media['kind']=='video' else 'variants') or {}
            if set(variants)!={'320','1280'}:raise ValueError('Both WebP display sizes are required.')
            for ref in [source['original'],*variants.values()]:backend.verify(ref)
            used.add(key)
        items.append((number,item))
    if len(used)!=len(archive):raise ValueError('The archive contains attachments not present in this published CSV.')
    products=[]
    for start in range(0,len(items),200):products.extend(store.match_products([i['product_hints'] for _,i in items[start:start+200]]))
    inserted=0;media_count=0;video_reviews=[]
    # Review identities and all media associations commit together. No external
    # downloads, discount writes or customer messages occur in this transaction.
    with store.db() as conn:
        for (number,item),product in zip(items,products):
            inserted+=int(store.import_one(conn,item,product))
            matches=conn.execute("""SELECT id FROM sc_reviews WHERE dedupe_key=%s OR source_fingerprint=%s OR id IN
              (SELECT review_id FROM sc_review_identities WHERE source=%s AND source_store_id=%s AND external_id=%s) LIMIT 2""",
              (item['dedupe_key'],item.get('source_fingerprint'),item['source'],item['source_store_id'],item.get('source_review_id'))).fetchall()
            if len(matches)!=1:raise ValueError('Review identity is ambiguous; reconcile it before linking media.')
            identity=matches[0]['id']
            for media in item['media']:
                entry=archive[(number,media['source_url'])];source=entry['storage'];original=source['original']
                conn.execute("""UPDATE sc_review_media SET object_key=%s,sha256=%s,size_bytes=%s,mime_type=%s,
                  storage=%s::jsonb,status='COPIED',approved=%s,lease_until=NULL,error_code=NULL
                  WHERE review_id=%s AND source_url=%s""",
                  (original['id'],original['sha256'],original['size'],entry['original_mime'],json.dumps(source),bool(entry.get('approved')),identity,media['source_url']))
                conn.execute('INSERT INTO sc_review_audit(review_id,actor,action) VALUES(%s,%s,%s)',(identity,actor(user),'dropbox_media_import'))
                media_count+=1
                if media['kind']=='video' and entry.get('approved'):video_reviews.append(str(identity))
        conn.execute("""INSERT INTO sc_review_imports(source,label,status,total,cursor,imported,duplicates,payload,actor)
          VALUES('judgeme','Judge.me Dropbox archive','COMPLETED',%s,%s,%s,%s,'[]'::jsonb,%s)""",
          (len(items),len(items),inserted,len(items)-inserted,actor(user)))
    from reviews_public_cache import CACHE
    CACHE.invalidate()
    return {'reviews':len(items),'inserted':inserted,'duplicates':len(items)-inserted,'media':media_count,'published_video_review_ids':video_reviews}
