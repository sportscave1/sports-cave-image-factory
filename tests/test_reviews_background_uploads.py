"""Durable upload receipt and deferred processing regression checks."""
import hashlib,io,os,unittest
from unittest.mock import Mock,patch
from PIL import Image
from reviews_media import save_owned,tick_media
from reviews_store import ReviewsStore
from reviews_public_submission import issue,submit
from tests.crm_db_fixture import connect

class BackgroundUploads(unittest.TestCase):
 def photo(self):
  out=io.BytesIO();Image.new('RGB',(40,30),'gold').save(out,'JPEG');return out.getvalue()
 def test_original_is_durable_before_ack_without_display_processing(self):
  storage=Mock();storage.put.return_value={'id':'id:fixture'}
  with patch('reviews_media.webp_variants') as variants,patch('reviews_media.video_poster') as poster:
   row=save_owned(self.photo(),'image',storage,defer_processing=True)
  self.assertEqual(row['storage']['processing'],'pending');storage.put.assert_called_once();variants.assert_not_called();poster.assert_not_called()
 @unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL only')
 def test_queued_original_survives_request_then_worker_builds_display_copies(self):
  objects={}
  class Storage:
   def put(self,name,data):
    objects[name]=data;return {'provider':'dropbox','id':'id:'+name.split('-')[0],'path':name,'rev':'aa','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
   def verify(self,ref):return True
   def open(self,ref):
    stream=Mock();stream.iter_chunks.return_value=[objects[ref['path']]];return stream
  storage=Storage();store=ReviewsStore(connect)
  with patch.dict(os.environ,{'REVIEWS_FORM_SECRET':'synthetic-background-key-'+'x'*32}),patch('reviews_dropbox.ReviewDropboxStorage',return_value=storage):
   identity=submit(store,issue(),{'rating':3,'reviewer_name':'Synthetic background test','body':'Synthetic pending upload','display_consent':True},[{'kind':'image','data':self.photo()}])
   media=store.media(identity)[0];self.assertEqual(media['status'],'QUEUED');self.assertNotIn('variants',media['storage'])
   self.assertEqual(len(objects),1);self.assertEqual(tick_media(store),media['id'])
   completed=store.media(identity)[0];self.assertEqual(completed['status'],'COPIED');self.assertFalse(completed['approved'])
   self.assertEqual(set(completed['storage']['variants']),{'320','640','1280'});self.assertEqual(len(objects),4)
   self.assertEqual(store.get_review(identity)['status'],'PENDING')

class EmailPolish(unittest.TestCase):
 def test_all_five_emails_keep_timing_and_native_buyer_links(self):
  import re,json
  from tests.test_reviews_journey import baseline
  from scripts.prepare_native_review_emails import prepare
  from scripts.polish_post_checkout_emails import polish,BASE
  old=prepare(baseline());new=polish(old)
  for before,after in zip(old['emails'],new['emails']):
   self.assertEqual({k:v for k,v in before.items() if k!='document'},{k:v for k,v in after.items() if k!='document'})
   html=' '.join(x.get('html','') for x in after['document']['middle_sections'])
   self.assertLess(len(re.sub('<[^>]+>',' ',html).split()),100)
   self.assertNotIn('judge.me',html);self.assertNotIn('judgeme',html)
   if after.get('review_request'):self.assertTrue(after['document']['content']['cta_url'].startswith(BASE+'/reviews/request/'))
