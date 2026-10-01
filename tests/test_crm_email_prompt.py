from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from crm_email_prompt import retain,handoff,build_email,fingerprint,COMPONENTS
from crm_campaign_prompt import build
from crm_prompt_readers import reference_image,PromptReader
from crm_image_prompt import image_prompt
from tests.test_crm_prompt_helper import DOC,Reader,inputs,NOW,PRODUCT

class EmailPromptTests(unittest.TestCase):
 def setUp(self):
  self.editor={'id':'campaign-a','recovery_seed':'stable-session','name':'Current title','document':deepcopy(DOC)}
  self.reader=Reader();self.state={}
  self.value=retain(self.state,self.editor,inputs(),build(inputs(),DOC,self.reader,NOW))
  self.catalogue=Mock();self.catalogue.resolve.return_value=[]
 def generate(self,**kwargs):return build_email(self.value,self.editor,self.reader,self.catalogue,**kwargs)
 def test_campaign_session_scope_and_no_editor_writes(self):
  before=deepcopy(self.editor);self.assertEqual(handoff(self.state,self.editor),self.value)
  self.assertIsNone(handoff(self.state,{**self.editor,'recovery_seed':'different'}))
  self.editor['id']='saved-id';self.assertIsNotNone(handoff(self.state,self.editor))
  self.editor['id']=before['id'];self.generate();self.assertEqual(self.editor,before)
 def test_latest_fields_and_input_changes_invalidate(self):
  old=fingerprint(self.editor,self.value,'Let AI decide',[],'')
  self.editor['document']['content']['subject']='New subject λ'
  result=self.generate();self.assertEqual(result['context']['current_campaign']['subject'],'New subject λ')
  self.assertNotEqual(old,fingerprint(self.editor,self.value,'Let AI decide',[],''))
  self.assertNotEqual(old,fingerprint(self.editor,self.value,'Choose components',['CTA'],'New direction'))
 def test_no_implicit_customer_or_audience_context(self):
  self.editor['document']['customer_email']='private@example.test'
  self.value['context']['secret']='credential'
  result=self.generate()['prompt'];self.assertNotIn('private@example.test',result);self.assertNotIn('credential',result);self.assertNotIn('1085',result)
 def test_manual_components_no_catalogue_reads(self):
  result=self.generate(mode='Choose components',components=['Headline','CTA'])
  self.catalogue.resolve.assert_not_called();self.catalogue.search.assert_not_called()
  self.assertEqual(result['context']['build']['components'],['Headline','CTA']);self.assertEqual(len(COMPONENTS),10)
  for kwargs in ({'mode':'bad'},{'mode':'Choose components'},{'components':['Unknown']},{'direction':'x'*801}):
   with self.assertRaises(ValueError):self.generate(**kwargs)
 def test_auto_product_boundary_and_live_recheck(self):
  self.reader.product=Mock(wraps=self.reader.product);self.generate()
  self.reader.product.assert_called_once_with(PRODUCT['id'])
  self.catalogue.resolve.assert_called_once_with([PRODUCT['id']],'AU',fresh=True);self.catalogue.search.assert_not_called()
 def test_collection_bounded_and_deduplicated(self):
  data={**inputs(),'kind':'Collection','target':{'id':'gid://shopify/Collection/2','title':'Racing'}}
  self.value=retain(self.state,self.editor,data,build(data,DOC,self.reader,NOW))
  self.catalogue.search.return_value={'rows':[{'id':str(i)} for i in range(20)]}
  self.generate();self.catalogue.search.assert_called_once_with('',0,True,'gid://shopify/Collection/2')
  self.assertEqual(len(self.catalogue.resolve.call_args.args[0]),12)
 def test_catalogue_rejects_unrelated_invalid_and_wrong_market_facts(self):
  from crm_catalogue import FIELDS
  good={k:'' for k in FIELDS};good.update(id=PRODUCT['id'],title='Brock',status='ACTIVE',
   url='https://www.sportscaveshop.com/products/brock',image='https://cdn.shopify.com/brock.jpg',
   price='100',currency='AUD',market='AU',edition=None)
  self.catalogue.resolve.return_value=[good,deepcopy(good),{**good,'id':'unrelated'},{**good,'currency':'USD'},{**good,'price':''},{**good,'status':'ARCHIVED'}]
  result=self.generate()['context']['catalogue_candidates'];self.assertEqual(result,[good])
 def test_copy_preflight_retains_context_before_browser_result(self):
  from crm_prompt_copy import copy_prompt
  callback=Mock(return_value='verified prompt')
  fake_component=Mock(return_value={'type':'prepare','event':'unique'})
  with patch('crm_prompt_copy.st.session_state',{}),patch('crm_prompt_copy.components.declare_component',return_value=fake_component),patch('crm_prompt_copy.st.rerun') as rerun:
   copy_prompt('ready','copy-key',revalidate=callback)
   callback.assert_called_once();rerun.assert_called_once_with(scope='fragment')
 def test_public_reference_image_validation(self):
  good='https://cdn.shopify.com/s/files/art.jpg?v=1';self.assertEqual(reference_image(good),good)
  for bad in ('http://cdn.shopify.com/a.jpg','https://admin.shopify.com/a.jpg','https://cdn.shopify.com/a.jpg?token=secret','data:image/png;base64,a'):
   self.assertEqual(reference_image(bad),'')
  shop=Mock();shop.products.return_value=[{'id':PRODUCT['id'],'title':'Brock','featuredImage':{'url':good}}]
  result=PromptReader(shop,Mock()).product(PRODUCT['id']);self.assertEqual(result['reference_image_url'],good)
  shop.products.assert_called_once_with([PRODUCT['id']],fresh=True,public_context=True)
 def test_image_upload_handoff_uses_verified_destination(self):
  result=image_prompt(self.editor['document'],self.editor['name'],self.value)
  self.assertIn('https://www.sportscaveshop.com/products/brock',result)
  self.assertIn('General promotion / product spotlight',result);self.assertIn('Current title',result)
  self.assertNotIn('1085',result)
 def test_contract_dynamic_sections_compatibility_and_visual_rules(self):
  result=self.generate()['prompt']
  for expected in ('BODY ONLY','<=60 KB','HTML SECTION 1','IMAGE — INSERT HERE','CATALOGUE — INSERT HERE',
    '320px','600px','60–140','2–7','2–4','actual pixels','all four','4:3','1200x900','6–10mm','4000–4700K','8–15%','3–6%',
    'no JavaScript carousel','native Image poster','unknown facts','at most two','no image overlays'):
   self.assertIn(expected.lower(),result.lower())
 def test_dialog_open_is_local_no_reader_or_catalogue(self):
  from streamlit.testing.v1 import AppTest
  app=AppTest.from_string("""
import streamlit as st
from unittest.mock import patch
from tests.test_crm_email_prompt import EmailPromptTests
from crm_email_prompt_ui import email_prompt_dialog
fixture=EmailPromptTests();fixture.setUp()
st.session_state.update(fixture.state)
with patch('crm_prompt_readers.PromptReader',side_effect=AssertionError('no reads')),patch('crm_catalogue.Catalogue',side_effect=AssertionError('no reads')):
 email_prompt_dialog(None,fixture.editor,'fixture_')
""").run()
  self.assertFalse(app.exception);self.assertEqual(app.segmented_control[0].value,'Let AI decide')
  self.assertTrue(any(b.label=='Build email prompt' for b in app.button))
 def test_editor_control_no_new_vertical_section(self):
  source=Path('crm_email_prompt_ui.py').read_text(encoding='utf-8')
  self.assertIn('height:0!important',source);self.assertNotIn('st.spinner',source);self.assertNotIn('sc-email-loading',source)
  self.assertNotIn('st.expander',source[:source.index('@st.dialog')])

if __name__=='__main__':unittest.main()
