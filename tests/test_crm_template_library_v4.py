"""Local source fidelity, copy independence and optimistic library edits."""
from copy import deepcopy
import os
import unittest
import uuid
from unittest.mock import patch,Mock
from crm_template_library import rows,source,apply_template,save_builtin,group_for,GROUPS,PREFIX
from crm_campaign_content import new_document
from crm_middle_sections import middle_sections,commit_middle
from crm_automation_store import AutomationStore
from crm_template_cache import invalidate
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN


class GroupTests(unittest.TestCase):
    def test_names_and_metadata(self):
        for name,expected in [('Thank You Email','Post Purchase'),('Collector Welcome','Welcome Series'),('Recovery Email','Abandoned Checkout'),('Collector Re-engagement','Win Back'),('Frame-synced banner','Lifestyle & Product'),('Wall Preview','Lifestyle & Product'),('Miscellaneous','Other Templates')]:
            self.assertEqual(group_for(dict(id='test',name=name)),expected)
        self.assertEqual(group_for(dict(name='Welcome',content={'library_group':'Other Templates'})),'Other Templates')
        self.assertEqual(GROUPS[0],'Defaults')

    def test_metadata_does_not_fetch_sources(self):
        store=Mock(connect=object(),email_mode='automation',preview_trigger='post_purchase')
        store.html_library.return_value=[];store.q.return_value=[]
        self.assertGreater(len(rows(store)),5)
        store.get.assert_not_called();store.state.assert_not_called()


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable loopback SQL required')
class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.store=AutomationStore(connect);self.store.preview_trigger='post_purchase';invalidate()
        self.ids=[];self.builtins=[]

    def tearDown(self):
        for identity in self.ids:
            row=self.store.get('templates',identity)
            self.store.archive_design(ADMIN,identity,row['version'])
        for identity in self.builtins:self.store.q('DELETE FROM crm_runtime_state WHERE key=%s',(PREFIX+identity,))
        invalidate()

    def create(self,html):
        doc=new_document();doc.update(content_mode='HTML',custom_html=html)
        row=self.store.save_design(ADMIN,'V4 '+uuid.uuid4().hex,doc,library_group='Other Templates');self.ids.append(row['id']);return row

    def test_source_snapshot_independence_and_confirmation(self):
        html='<!--[if mso]><table><tr><td><![endif]--><p style="color:#123456">{{ first_name }} &amp; &#9733;</p><!--[if mso]></td></tr></table><![endif]-->'
        row=self.create(html);doc=new_document();doc.update(content_mode='HTML',custom_html='<p>Keep my edit</p>')
        doc['content'].update(subject='My subject',preheader='My preview');doc['html_sections']={'header':'<p>Old header</p>','footer':'<p>Old footer</p>'}
        before=deepcopy(doc)
        with self.assertRaisesRegex(ValueError,'Confirm'):apply_template(self.store,doc,row['id'],1)
        self.assertEqual(doc,before)
        apply_template(self.store,doc,row['id'],1,confirmed=True)
        self.assertEqual(middle_sections(doc)[0]['html'],html)
        for field in ('content','html_sections','audience','market'):self.assertEqual(doc[field],before[field])
        snapshot=deepcopy(doc)
        template=new_document();template.update(content_mode='HTML',custom_html='<p>Updated library</p>')
        self.store.save_design(ADMIN,row['name'],template,row['id'],1)
        self.assertEqual(doc,snapshot)
        doc['middle_sections'][0]['html']='<p>Independent edit</p>'
        meta=next(r for r in rows(self.store) if r['id']==row['id'])
        self.assertEqual(source(self.store,meta),'<p>Updated library</p>')
        self.assertEqual(group_for(meta),'Other Templates')

    def test_builtin_edit_keeps_identity_and_merge_markers(self):
        row=next(r for r in rows(self.store) if str(r['id']).endswith('post_purchase-1'));self.builtins.append(row['id'])
        html=source(self.store,row);doc=new_document();doc['content'].update(subject='Keep subject',preheader='Keep preview')
        apply_template(self.store,doc,row['id'],row['version'])
        snapshot=deepcopy(doc)
        save_builtin(self.store,ADMIN,row,row['name'],html+'<!-- reusable edit -->','Post Purchase')
        latest=next(r for r in rows(self.store) if r['id']==row['id'])
        self.assertEqual(latest['version'],row['version']+1)
        self.assertEqual(source(self.store,latest),html+'<!-- reusable edit -->')
        self.assertEqual(doc,snapshot);self.assertEqual(doc['content']['subject'],'Keep subject')
        self.assertEqual(doc['content']['preheader'],'Keep preview')
        with self.assertRaisesRegex(ValueError,'changed elsewhere'):save_builtin(self.store,ADMIN,row,'Conflict',html,'Post Purchase')

    def test_structured_hidden_sections_preserved_and_detached(self):
        template=new_document();template['content_mode']='HTML'
        commit_middle(template,[dict(id='first',type='html',html_number=1,visible=True,html='<p>Visible</p>'),dict(id='hidden',type='html',html_number=2,visible=False,html='<style>@media(max-width:600px){p{color:red}}</style><p>Hidden</p>')])
        row=self.store.save_design(ADMIN,'Structured '+uuid.uuid4().hex,template,library_group='Welcome Series');self.ids.append(row['id'])
        doc=new_document();apply_template(self.store,doc,row['id'],1)
        self.assertEqual([s['html'] for s in middle_sections(doc)],[s['html'] for s in template['middle_sections']])
        self.assertFalse(doc['middle_sections'][1]['visible'])
        self.assertNotEqual(doc['middle_sections'][0]['id'],'first')
        self.assertEqual(self.store.template_document(self.store.get('templates',row['id']))['middle_sections'],template['middle_sections'])


if __name__=='__main__':unittest.main()
