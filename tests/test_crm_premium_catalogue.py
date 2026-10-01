from copy import deepcopy
from pathlib import Path
import unittest
from crm_catalogue import catalogue_html,desktop_columns,validate_snapshot
from crm_middle_sections import middle_sections,validate_middle,render_middle
from crm_campaign_html import import_html
from crm_campaign_content import render_campaign
from tests.test_crm_modular_catalogue import catalogue_doc
from tests.test_crm_catalogue_presentation import Markup
from tests.fixtures.crm_catalogue_old_renderer import catalogue_html as old_html

class PremiumCatalogueTests(unittest.TestCase):
 def section(self,n):
  section=deepcopy(catalogue_doc()['middle_sections'][-1]);base=section['products'][0]
  section['products']=[{**deepcopy(base),'id':'gid://shopify/Product/'+str(i+1),'title':'63 Years Later: Ryan Fox Open Championship Wall Art','url':'https://www.sportscaveshop.com/products/art-'+str(i)} for i in range(n)]
  return section
 def test_count_selects_hero_not_saved_columns(self):
  for columns in (1,2):
   s=self.section(1);s['settings']['columns']=columns
   h=catalogue_html(s);self.assertIn('width="552"',h);self.assertNotIn('sc-cat-item',h)
  s=self.section(2);s['products'][1]['status']='DRAFT';self.assertIn('width="552"',catalogue_html(s))
 def test_counts_and_two_up_fallback(self):
  for n,c in ((2,2),(3,3),(4,4),(5,3),(6,3),(7,4),(12,4)):
   s=self.section(n);s['settings']['columns']=1;h=catalogue_html(s)
   self.assertEqual(desktop_columns(s['products']),c);self.assertEqual(h.count('class="sc-cat-item sc-cat-'+str(c)+'"'),n)
   self.assertNotIn('sc-stack',h);self.assertIn('width:50%',h)
   self.assertEqual(len(Markup(h).images),n)
  s=self.section(4);s['products'][0]['title']='Very long product identity '*8;self.assertEqual(desktop_columns(s['products']),2)
 def test_alt_and_aspect_ratio(self):
  s=self.section(1);p=s['products'][0]
  for alt,expected in (('Verified framed collector print','Verified framed collector print'),('image',p['title']),('',p['title'])):
   p['image_alt']=alt;img=Markup(catalogue_html(s)).images[0][0]
   self.assertEqual(img['alt'],expected);self.assertIn('height:auto',img['style']);self.assertNotIn('height',img)
   self.assertNotIn('object-fit',img['style']);validate_snapshot(p)
 def test_optional_copy_escaping_runtime_defaults_no_mutation(self):
  doc=catalogue_doc();before=deepcopy(doc);s=middle_sections(doc)[-1]
  self.assertEqual(s['settings']['headline'],'');self.assertEqual(s['settings']['subtext'],'');self.assertEqual(doc,before)
  s['settings'].update(headline='<Own & collect>',subtext='<script>not HTML</script>')
  h=catalogue_html(s);self.assertIn('&lt;Own &amp; collect&gt;',h);self.assertNotIn('<script>',h)
  validate_middle([s]);s['settings']['headline']='x'*81
  with self.assertRaises(ValueError):validate_middle([s])
 def test_sanitizer_trust_is_specific(self):
  h=catalogue_html(self.section(4));safe=import_html(h,trusted_catalogue=True)[0]
  self.assertIn('class="sc-cat-item sc-cat-4"',safe);self.assertIn('<!--[if mso]>',safe)
  self.assertNotIn('sc-cat-item',import_html(h)[0]);self.assertNotIn('<!--[if mso]>',import_html(h)[0])
  for source in ('<div class="sc-cat-item sc-cat-4">x</div>','<table class="sc-cat-item evil">x</table>'):
   self.assertNotIn('class=',import_html(source,trusted_catalogue=True)[0])
  self.assertIn('class="sc-stack"',import_html('<table><tr><td class="sc-stack">x</td></tr></table>')[0])
 def test_size_and_meaningful_images_off(self):
  for n in (1,2,4,6,12):
   s=self.section(n);h=catalogue_html(s);old=old_html(s)
   self.assertLess(len(h.encode()),len(old.encode())*1.6)
   self.assertLess(len(h.encode()),40000)
   _,text,checks=import_html(h,images_off=True,trusted_catalogue=True)
   self.assertIn('Ryan Fox',text);self.assertIn('LIMITED TO 100',text);self.assertIn('#037 / 100',text);self.assertIn('64 REMAINING',text)
   self.assertIn('https://',text);self.assertTrue(all(checks.values()))
   print('Catalogue bytes count=%s old=%s new=%s'%(n,len(old.encode()),len(h.encode())))
 def test_render_is_local_and_toggles_remain_authoritative(self):
  from unittest.mock import patch
  s=self.section(1)
  with patch('requests.sessions.Session.request',side_effect=AssertionError('No network')),patch('crm_catalogue.Catalogue.resolve',side_effect=AssertionError('No fresh reads')):
   for field,absent in (('image','<img'),('title','Ryan Fox'),('price','A$85'),('limit','LIMITED TO'),('next','#037'),('remaining','REMAINING'),('cta','View the Edition')):
    cfg=deepcopy(s);cfg['settings']['display'][field]=False
    h=catalogue_html(cfg)
    if field=='title':h=import_html(h,images_off=True)[1]
    self.assertNotIn(absent,h)
 def test_no_unsupported_features_and_wrapper_rules(self):
  doc=catalogue_doc();doc['middle_sections'][-1]=self.section(4);h=render_campaign(doc)['html']
  self.assertIn('(min-width:540px)',h);self.assertIn('.sc-cat-4{width:25%',h);self.assertIn('.sc-stack{display:block',h)
  for word in ('<script','<svg','<iframe','scroll-snap','object-fit','shipping icon','authenticity icon','carousel','base64'):
   self.assertNotIn(word,h)

if __name__=='__main__':unittest.main()
