"""Shared modular editor actions: synthetic documents and offline persistence."""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock,patch
from crm_middle_sections import apply_event,middle_sections,commit_middle,render_middle
from crm_campaign_content import validate_document,render_campaign
from crm_template_library import apply_template,section_source
from crm_wall_preview_template import source as wall_source,IDENTITY,NAME
from tests.test_crm_modular_catalogue import catalogue_doc

class ModularBuilderTests(unittest.TestCase):
    def setUp(self):
        self.doc=catalogue_doc()
        self.doc['middle_sections'][0]['name']='Collector Experience'
        self.doc['middle_sections'][-1]['settings'].update(smart=True,smart_count=7,headline='Continue Your Collection')
        self.before=deepcopy(self.doc)
        self.row=dict(id=IDENTITY,name=NAME,version=1,builtin=True)

    def event(self,action,**kwargs):
        apply_event(self.doc,dict(type=action,base=[s['id'] for s in middle_sections(self.doc)],**kwargs),resolve_insert=lambda _:dict(html=wall_source(),name=NAME))

    def test_add_wall_after_catalogue_is_only_insertion(self):
        self.event('add',kind='template',template_id=IDENTITY,version=1)
        self.assertEqual(self.doc['middle_sections'][:-1],self.before['middle_sections'])
        self.assertEqual(self.doc['middle_sections'][-1]['html'],wall_source())
        for key in self.before.keys()-{'middle_sections','custom_html'}:self.assertEqual(self.doc[key],self.before[key])
        self.assertNotIn('template_ref',self.doc.keys()-self.before.keys())
        validate_document(self.doc)

    def test_multiple_html_edit_insert_reorder_duplicate_hide_delete_roundtrip(self):
        originals=deepcopy(self.doc['middle_sections'])
        self.event('add',kind='html',position=1,new_id='new-one')
        self.event('add',kind='html',new_id='new-two')
        source='<table role="presentation"><tr><td style="color:#123456;padding:9px"><a href="https://example.com/art">Independent &amp; complete</a></td></tr></table>'
        self.event('html',id='new-one',html=source)
        self.event('html',id='new-two',html='<p>Second independent section</p>')
        self.event('rename',id='new-one',name='Custom copy')
        self.event('duplicate',id='new-one',new_id='copy-one')
        self.event('html',id='copy-one',html='<p>Copy changed</p>')
        self.event('visible',id='new-two',visible=False)
        order=[s['id'] for s in self.doc['middle_sections']][::-1]
        self.event('order',ids=order)
        self.event('remove',id='copy-one',confirmed=True)
        stored=json.loads(json.dumps(self.doc));validate_document(stored)
        self.assertEqual(stored,self.doc)
        by_id={s['id']:s for s in stored['middle_sections']}
        for s in originals:self.assertEqual(by_id[s['id']],s)
        self.assertEqual(by_id['new-one']['html'],source)
        self.assertFalse(by_id['new-two']['visible'])
        html=render_middle(stored)[0]
        self.assertIn('color:#123456',html);self.assertNotIn('Second independent section',html)

    def test_add_preserves_even_empty_hidden_html_and_no_confirmation(self):
        commit_middle(self.doc,[dict(id='empty',type='html',html_number=1,html='',visible=False,name='Keep empty')])
        self.event('add',kind='template',confirmed=False)
        self.assertEqual(self.doc['middle_sections'][0],dict(id='empty',type='html',html_number=1,html='',visible=False,name='Keep empty'))
        self.assertEqual(len(self.doc['middle_sections']),2)

    def test_group_inserts_at_position_with_new_ids_and_no_template_mutation(self):
        group=deepcopy(self.before['middle_sections']);original=deepcopy(group)
        apply_event(self.doc,dict(type='add',kind='template',position=1,new_ids=['copy-html','copy-cat'],base=[s['id'] for s in group]),resolve_insert=lambda _:dict(sections=group))
        self.assertEqual([s['id'] for s in self.doc['middle_sections']],[group[0]['id'],'copy-html','copy-cat',group[1]['id']])
        self.assertEqual(group,original)
        self.doc['middle_sections'][2]['settings']['smart_count']=2
        self.assertEqual(group[1]['settings']['smart_count'],7)

    def test_bad_positions_and_failed_batch_are_atomic(self):
        for position in (-1,99,True,'1'):
            with self.assertRaises(ValueError):self.event('add',kind='html',position=position)
            self.assertEqual(self.doc,self.before)
        with self.assertRaises(ValueError):self.event('batch',events=[dict(type='add',kind='html',new_id='new',base=[s['id'] for s in self.doc['middle_sections']]),dict(type='order',base=['bad'],ids=[])])
        self.assertEqual(self.doc,self.before)

    def test_full_template_requires_explicit_confirmation_and_preserves_settings(self):
        with patch('crm_template_library.rows',return_value=[self.row]),patch('crm_template_library.source',return_value='<p>Replacement body</p>'):
            with self.assertRaisesRegex(ValueError,'Confirm'):apply_template(None,self.doc,IDENTITY,1)
            self.assertEqual(self.doc,self.before)
            apply_template(None,self.doc,IDENTITY,1,confirmed=True)
        self.assertEqual(len(self.doc['middle_sections']),1)
        self.assertEqual(self.doc['middle_sections'][0]['html'],'<p>Replacement body</p>')
        for key in self.before.keys()-{'middle_sections','custom_html','copy_reviewed','template_ref','content_mode'}:self.assertEqual(self.doc[key],self.before[key])

    def test_section_source_uses_edited_builtin_and_only_saved_middle(self):
        with patch('crm_template_library.source',return_value='<p>Edited builtin</p>'):
            self.assertEqual(section_source(None,self.row)['html'],'<p>Edited builtin</p>')
        body=deepcopy(self.doc['middle_sections'])
        with patch('crm_campaign_library.template_sections',return_value=body):
            resolved=section_source(None,{**self.row,'builtin':False})
        self.assertEqual(resolved['sections'],body);self.assertEqual(resolved['html'],'')

    def test_custom_button_is_independent_html(self):
        self.event('add',kind='button',position=1)
        button=self.doc['middle_sections'][1]
        self.assertEqual(button['type'],'html');self.assertEqual(button['name'],'Custom Button')
        self.event('html',id=button['id'],html='<p>Completely custom button source</p>')
        self.assertEqual(self.doc['middle_sections'][0],self.before['middle_sections'][0])

    def test_customer_preview_and_frozen_test_live_payload_preserve_order(self):
        from crm_checkout_preview import document as preview_document
        from crm_abandoned_checkout import hydrate
        from tests.test_crm_wall_preview_template import checkout_data
        from tests.test_crm_send_flow import CFG
        from crm_campaign_dispatch import payload
        from types import SimpleNamespace
        self.doc['middle_sections'][-1]['settings']['smart']=False
        self.event('html',id=self.doc['middle_sections'][0]['id'],html='<p>FIRST Collector Experience</p>')
        self.event('add',kind='template')
        self.event('add',kind='html',new_id='last-copy')
        self.event('html',id='last-copy',html='<p>LAST Additional content</p>')
        before=deepcopy(self.doc)
        for document in (preview_document(self.doc,checkout_data())[0],hydrate(self.doc,checkout_data())):
            for production in (False,True):
                message=render_campaign(document,CFG,production=production,unsubscribe_url='https://example.test/unsubscribe')
                positions=[message['html'].index(t) for t in ('FIRST Collector Experience','Artwork 1','See It On Your Wall','LAST Additional content')]
                self.assertEqual(positions,sorted(positions))
                if production:
                    outgoing=payload(message,dict(address='fixture@example.test',unsubscribe_url='https://example.test/unsubscribe',message=message),SimpleNamespace(sender='Sports Cave <sender@example.test>',reply_to='support@example.test'))
                    self.assertIn('LAST Additional content',outgoing['html'])
        self.assertEqual(self.doc,before)

    def test_preview_uses_bound_trigger_without_draft_identity(self):
        from crm_automation_store import AutomationStore
        from crm_lifestyle_images import source
        store=AutomationStore(Mock());store.preview_trigger='abandoned';store.preview_shop=Mock()
        doc=deepcopy(self.doc);commit_middle(doc,[dict(id='image-only',type='html',html_number=1,visible=True,html=source(2))])
        with patch('crm_abandoned_checkout.preview_context',return_value=(None,'')),patch('crm_checkout_preview.document',return_value=(doc,'')):
            store.preview_document(doc)

if __name__=='__main__':unittest.main()
