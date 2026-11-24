"""Synthetic Dropbox derivative ownership, size and persistence checks."""
import hashlib
import io
import json
import unittest
from unittest.mock import Mock
from PIL import Image
from reviews_display_media import carousel_copy,ensure_carousel


class CarouselMediaTests(unittest.TestCase):
    def source(self):
        output=io.BytesIO();Image.new('RGB',(1280,960),'#ac712e').save(output,'WEBP',quality=82)
        return output.getvalue()
    def test_carousel_is_bounded_webp_and_detail_is_not_replaced(self):
        body=self.source();display=carousel_copy(body)
        with Image.open(io.BytesIO(display['data'])) as image:
            self.assertEqual(image.format,'WEBP');self.assertEqual(image.size,(640,480))
        self.assertLess(len(display['data']),90000)
        ref={'id':'id:synthetic','rev':'one','size':len(body),'sha256':hashlib.sha256(body).hexdigest()}
        owned={'provider':'dropbox','original':{**ref,'id':'id:original'},'variants':{'1280':ref,'320':ref}}
        storage=Mock();stream=Mock();stream.iter_chunks.return_value=[body];storage.open.return_value=stream
        storage.put.side_effect=lambda name,data:{**ref,'id':'id:640','sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
        store=Mock();store.q.side_effect=lambda sql,args,one:{'storage':{**owned,'variants':{**owned['variants'],'640':json.loads(args[1])}}}
        result=ensure_carousel(store,'fixture',{'kind':'image','storage':owned},storage)
        self.assertEqual(result['original'],owned['original']);self.assertEqual(result['variants']['1280'],ref)
        self.assertEqual(result['variants']['640']['width'],640)
        self.assertEqual(store.q.call_args.args[1][0],['variants','640'])
        self.assertIn("r.status='PUBLISHED'",store.q.call_args.args[0]);self.assertIn('m.approved=true',store.q.call_args.args[0])
        stream.close.assert_called_once()
        before=storage.open.call_count
        self.assertEqual(ensure_carousel(store,'fixture',{'kind':'image','storage':result},storage),result)
        self.assertEqual(storage.open.call_count,before)
    def test_corrupt_or_oversized_sources_cannot_be_written(self):
        with self.assertRaises(ValueError):carousel_copy(b'x'*(1024*1024+1))
        body=self.source();ref={'id':'id:synthetic','rev':'one','size':len(body),'sha256':'0'*64}
        storage=Mock();storage.open.return_value.iter_chunks.return_value=[body]
        with self.assertRaises(ValueError):ensure_carousel(Mock(),'fixture',{'kind':'image','storage':{'provider':'dropbox','original':ref,'variants':{'1280':ref}}},storage)
        storage.put.assert_not_called();storage.open.return_value.close.assert_called_once()


class DeliveryCacheTests(unittest.TestCase):
    def test_cache_is_bounded_and_expires(self):
        from reviews_display_cache import ImageCache
        clock=Mock(return_value=0);cache=ImageCache(byte_limit=5,limit=2,clock=clock)
        cache.put('a',b'123');cache.put('b',b'45');self.assertEqual(cache.bytes,5)
        cache.put('c',b'67');self.assertIsNone(cache.get('a'));self.assertLessEqual(cache.bytes,5)
        clock.return_value=901;self.assertIsNone(cache.get('c'))
    def test_image_is_downloaded_once_but_hidden_media_still_returns_404(self):
        from unittest.mock import patch
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from reviews_http import router
        from reviews_public_cache import CACHE
        from reviews_display_cache import CACHE as images
        CACHE.invalidate();images.rows.clear();images.bytes=0
        output=io.BytesIO();Image.new('RGB',(20,20),'red').save(output,'WEBP');body=output.getvalue()
        ref={'provider':'dropbox','id':'id:syntheticdelivery','rev':'a1','size':len(body),'sha256':hashlib.sha256(body).hexdigest()}
        store=Mock();store.connect='fixture';store.settings.return_value={'enabled':True};store.q.return_value={'kind':'image','storage':{'provider':'dropbox','variants':{'320':ref,'640':ref}}}
        storage=Mock();storage.open.return_value.iter_chunks.return_value=[body]
        app=FastAPI();app.include_router(router);client=TestClient(app)
        url='/reviews/media/'+'c'*32+'?size=320'
        with patch('reviews_http.ReviewsStore',return_value=store),patch('reviews_http.allow_rate',return_value=True),patch('reviews_dropbox.ReviewDropboxStorage',return_value=storage):
            self.assertEqual(client.get(url).content,body);self.assertEqual(client.get(url).content,body)
            storage.open.assert_called_once()
            delivery=url.replace('size=320','size=640&delivery=dropbox')
            with patch('reviews_display_media.temporary_display_link',return_value='https://dl.dropboxusercontent.com/apitl/synthetic'):
                response=client.get(delivery,follow_redirects=False)
                self.assertEqual(response.status_code,307);self.assertNotIn('etag',response.headers)
            CACHE.invalidate()
            with patch('reviews_display_media.temporary_display_link',side_effect=ValueError('unavailable')):
                self.assertEqual(client.get(delivery).content,body)
            CACHE.invalidate();store.q.return_value=None
            self.assertEqual(client.get(url).status_code,404)
            storage.open.assert_called_once()
    def test_temporary_delivery_checks_pinned_receipt_and_dropbox_host(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from reviews_display_media import temporary_display_link
        ref={'provider':'dropbox','id':'id:synthetic','rev':'a1','size':10,'sha256':'f'*64}
        result=SimpleNamespace(metadata=SimpleNamespace(id=ref['id'],rev='a1',size=10),link='https://dl.dropboxusercontent.com/apitl/synthetic')
        client=Mock();client.files_get_temporary_link.return_value=result
        with patch('reviews_dropbox.ReviewDropboxStorage',return_value=SimpleNamespace(context={'client':client})):
            self.assertEqual(temporary_display_link(ref),result.link)
            result.metadata.rev='b2'
            with self.assertRaises(ValueError):temporary_display_link(ref)
            result.metadata.rev='a1';result.link='https://unrelated.example/image'
            with self.assertRaises(ValueError):temporary_display_link(ref)


if __name__=='__main__':unittest.main()
