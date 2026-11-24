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


if __name__=='__main__':unittest.main()
