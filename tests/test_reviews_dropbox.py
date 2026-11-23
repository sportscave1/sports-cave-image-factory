"""Offline contracts: Dropbox owns all media; public images are bounded WebP."""
import hashlib
import io
import json
import os
import unittest
from unittest.mock import Mock,patch
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reviews_media import save_owned,webp_variants
from reviews_dropbox import ReviewDropboxStorage,content_hash,asset
import tests.test_reviews_migration as migration
from tests.test_reviews_migration import photo,OWNED,REF
from tests.test_crm import ADMIN

class DropboxMediaTests(unittest.TestCase):
    def test_paid_os_routes_keep_other_pages_and_secure_collection_base(self):
        from reviews_routing import PublicReviews,public_base,PUBLIC_ORIGIN
        fallback=FastAPI()
        @fallback.get('/fixture-health')
        def health():return {'ok':True}
        with patch('reviews_http.ReviewsStore') as store,TestClient(PublicReviews(fallback)) as client:
            store.return_value.settings.return_value={'enabled':False}
            self.assertEqual(client.get('/fixture-health').json(),{'ok':True})
            self.assertEqual(client.get('/reviews/public').status_code,404)
        self.assertEqual(public_base({'RENDER':'true','CRM_PUBLIC_BASE_URL':'https://fixture.example'}),PUBLIC_ORIGIN)
        self.assertEqual(public_base({'CRM_PUBLIC_BASE_URL':'https://fixture.example'}),'https://fixture.example')
    def test_original_is_saved_before_display_copies_and_webp_is_small(self):
        data=photo();calls=[];storage=Mock()
        storage.put.side_effect=lambda name,body:(calls.append((name,body)) or {**REF,'size':len(body),'sha256':hashlib.sha256(body).hexdigest()})
        value=save_owned(data,'image',storage)
        self.assertEqual(calls[0][1],data);self.assertTrue(calls[0][0].endswith('-original.png'))
        self.assertEqual(len(calls),3);self.assertEqual(value['storage']['provider'],'dropbox')
        for name,body in calls[1:]:
            self.assertTrue(name.endswith('.webp'))
            with Image.open(io.BytesIO(body)) as im:self.assertEqual(im.format,'WEBP');self.assertLessEqual(im.width,1280)
    def test_dropbox_failure_never_creates_display_files_or_uses_r2(self):
        storage=Mock();storage.put.side_effect=ValueError('offline')
        with patch('reviews_media.webp_variants') as process:
            with self.assertRaises(ValueError):save_owned(photo(),'image',storage)
            process.assert_not_called()
        self.assertEqual(storage.put.call_count,1)
    def test_existing_asset_is_reused_only_when_hash_matches(self):
        data=photo();metadata={'id':'id:reviewfixture','rev':'a1','size':len(data),'content_hash':content_hash(data)}
        storage=ReviewDropboxStorage({'token':'fixture','root':'/Sportscave Team Folder/03_ASSETS/Reviews'})
        name=hashlib.sha256(data).hexdigest()+'-original.png'
        with patch('dropbox_integration.get_metadata_if_exists',return_value=metadata),patch('dropbox_integration.upload_stream') as upload:
            result=storage.put(name,data);upload.assert_not_called();self.assertEqual(result['size'],len(data))
        with patch('dropbox_integration.get_metadata_if_exists',return_value={**metadata,'content_hash':'0'*64}):
            with self.assertRaises(ValueError):storage.put(name,data)
    def test_video_has_original_plus_webp_posters(self):
        storage=Mock();storage.put.return_value=REF
        with patch('reviews_media.video_poster',return_value=photo()):value=save_owned(b'\x00\x00\x00\x18ftypmp42fixture','video',storage)
        self.assertEqual(value['storage']['video_format'],'mp4');self.assertEqual(len(value['storage']['posters']),2)
        self.assertTrue(storage.put.call_args_list[0].args[0].endswith('-original.mp4'))
    def test_original_images_and_legacy_r2_cannot_be_public_sources(self):
        with self.assertRaises(ValueError):asset(OWNED['storage'],'original','image')
        with self.assertRaises(ValueError):asset({'provider':'r2'},'320','image')

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class DropboxHttpTests(unittest.TestCase):
    setUp=migration.MigrationDatabaseTests.setUp
    cleanup=migration.MigrationDatabaseTests.cleanup
    item=migration.MigrationDatabaseTests.item
    insert=migration.MigrationDatabaseTests.insert
    order=migration.MigrationDatabaseTests.order

    def test_archived_video_is_linked_to_its_exact_review_and_published_idempotently(self):
        from reviews_dropbox_migration import import_archive
        identity=self.prefix+'dropbox';self.created.append(identity)
        source='https://images.judge.me/video.mp4'
        data=f'source_review_id,product_id,rating,body,created_at,status,video_urls\n{identity},{self.pid},5,Synthetic video review,2026-01-01,Published,{source}\n'.encode()
        storage={'provider':'dropbox','original':REF,'video_format':'mp4','posters':{'320':{**REF,'width':320,'height':180},'1280':{**REF,'width':1280,'height':720}}}
        manifest={'version':1,'csv_sha256':hashlib.sha256(data).hexdigest(),'media':[{'row':2,'source_url':source,'kind':'video','storage':storage,'original_mime':'video/mp4','approved':True}]}
        backend=Mock();backend.verify.return_value=True
        first=import_archive(self.store,ADMIN,data,manifest,'fixture.myshopify.com',backend)
        second=import_archive(self.store,ADMIN,data,manifest,'fixture.myshopify.com',backend)
        self.assertEqual((first['inserted'],second['duplicates']),(1,1));self.assertEqual(len(first['published_video_review_ids']),1)
        row=self.store.q('SELECT * FROM sc_reviews WHERE source_review_id=%s',(identity,),True)
        media=self.store.media(row['id']);self.assertEqual(len(media),1);self.assertTrue(media[0]['approved']);self.assertEqual(media[0]['storage'],storage)
        backend.verify.reset_mock()
        with self.assertRaises(ValueError):import_archive(self.store,ADMIN,data+b'\n',manifest,'fixture.myshopify.com',backend)
        backend.verify.assert_not_called()

    def test_video_ranges_and_poster_are_served_from_dropbox_without_private_ids(self):
        from reviews_http import router
        r=self.insert();storage={'provider':'dropbox','video_format':'mp4','original':REF,'posters':{'320':{**REF,'width':320,'height':180},'1280':{**REF,'width':1280,'height':720}}}
        m=self.store.q("INSERT INTO sc_review_media(review_id,kind,source_url,object_key,sha256,size_bytes,status,approved,storage) VALUES(%s,'video','fixture','id:reviewfixture',%s,100,'COPIED',true,%s::jsonb) RETURNING id",(r['id'],'f'*64,json.dumps(storage)),True)
        from reviews_routing import PublicReviews
        self.store.save_settings(ADMIN,{'enabled':True});app=PublicReviews(FastAPI())
        def open_source(ref,start=0,end=None):
            stream=Mock();stream.iter_chunks.side_effect=lambda:iter([b'x'*(end-start+1)]);return stream
        with patch('reviews_http.ReviewsStore',return_value=self.store),patch('reviews_dropbox.ReviewDropboxStorage.open',side_effect=open_source) as fetch,TestClient(app) as client:
            path='/reviews/media/'+str(m['id'])
            response=client.get(path+'?size=original',headers={'Range':'bytes=10-19'})
            self.assertEqual(response.status_code,206);self.assertEqual(response.content,b'x'*10);self.assertEqual(response.headers['Content-Range'],'bytes 10-19/100');self.assertEqual(response.headers['Content-Type'],'video/mp4')
            self.assertEqual(fetch.call_args.args[1:],(10,19))
            image=client.get(path+'?size=320');self.assertEqual(image.headers['Content-Type'],'image/webp')
            before=fetch.call_count
            self.assertEqual(client.get(path,headers={'Range':'bytes=100-'}).status_code,416)
            self.assertEqual(client.head(path).status_code,200);self.assertEqual(fetch.call_count,before)
            data=client.get('/reviews/public',params={'product':self.pid}).json()
            self.assertEqual(data['reviews'][0]['media'][0]['kind'],'video')
            public=json.dumps(data);self.assertNotIn('id:reviewfixture',public);self.assertNotIn('Sportscave Team Folder',public);self.assertNotIn('source_url',public)

if __name__=='__main__':unittest.main()
