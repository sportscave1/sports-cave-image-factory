import io
import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch
from product_quiz import DEFAULT,validate,classify,digest
from product_quiz_publish import sync,publish,revert,compile_catalogue,snippets
from product_quiz_api import clean
from uuid import uuid4


def row(pid='1',title='Michael Jordan Wall Art',sport='Basketball',subject='Michael Jordan',**extras):
    return dict(id=pid,shopify_product_id='gid://shopify/Product/'+pid,title=title,status='ACTIVE',handle='edition-'+pid,
      online_store_url='https://sportscaveshop.com/products/edition-'+pid,image_url='https://cdn.shopify.com/test.jpg',
      collections=[dict(title=sport,handle=sport.lower()),dict(title=subject,handle=subject.lower().replace(' ','-'))],**extras)


class MemoryStore:
    def __init__(self): self.states={}; self.rows=[row()]
    @contextmanager
    def lock(self): yield
    def get_state(self,k,fallback=None): return deepcopy(self.states.get(k,fallback))
    def put_state(self,k,v): self.states[k]=deepcopy(v)
    def draft(self): return {'revision':0,'config':deepcopy(DEFAULT)}
    def catalogue_rows(self): return deepcopy(self.rows)


class MemoryAssets:
    def __init__(self): self.objects={};self.writes=[];self.fail=None
    def get(self,path): return deepcopy(self.objects.get(path))
    def put(self,path,body,*args,**kwargs):
        if self.fail and self.fail in path: raise OSError('Injected storage failure')
        self.objects[path]=deepcopy(body);self.writes.append(path);return path


class QuizContracts(unittest.TestCase):
    def test_reconciliation_uses_one_existing_host_without_starting_in_tests(self):
        from product_quiz_worker import enabled,start_app_reconciler
        with patch.dict('os.environ',{'PRODUCT_QUIZ_ENABLED':'true','PRODUCT_QUIZ_RECONCILER_HOST':'app'}):
            self.assertTrue(enabled(role='app'));self.assertFalse(enabled())
        with patch.dict('os.environ',{'PRODUCT_QUIZ_ENABLED':'false'}):
            self.assertFalse(start_app_reconciler())
    def test_empty_reconciliation_snapshot_is_not_treated_as_missing(self):
        from product_quiz_store import QuizStore
        store=QuizStore()
        with patch.object(store,'q',return_value={'value':[]}):
            self.assertEqual(store.get_state('present_product_ids'),[])
        with patch.object(store,'q',return_value=None):
            self.assertIsNone(store.get_state('present_product_ids'))
    def test_navigation_has_one_admin_child_under_developer(self):
        import os_accounts
        from pathlib import Path
        page=os_accounts.PAGE_BY_ROUTE['Product Quiz']
        self.assertEqual(page['parent_key'],'developer');self.assertTrue(page['navigation_child'])
        self.assertEqual(sum(p['route']=='Product Quiz' for p in os_accounts.PAGE_REGISTRY),1)
        self.assertFalse(os_accounts.can_access_page({'role':'worker','is_active':True,'page_permissions':['product_quiz']},'Product Quiz'))
        self.assertTrue(os_accounts.can_access_page({'role':'admin','is_active':True},'Product Quiz'))
        source=(Path(__file__).parents[1]/'app.py').read_text(encoding='utf-8')
        self.assertIn('child_button(children, "Product Quiz", "Product Quiz")',source)
        self.assertIn('key="sidebar-developer-children"',source)
        self.assertIn('elif current_page == "Product Quiz":',source)

    def test_defaults_and_configuration_constraints(self):
        self.assertEqual(validate(DEFAULT),DEFAULT)
        for mutate in (lambda c:c['questions'].reverse(),lambda c:c['rules'].update(max_results=4),lambda c:c['appearance'].update(accent='red'),lambda c:c.update(unknown=True)):
            c=deepcopy(DEFAULT);mutate(c)
            with self.assertRaises(ValueError): validate(c)

    def test_several_sports_and_title_helper(self):
        for fixture,sport in [(row(),'Basketball'),(row('2','Shane Warne Wall Art','Cricket','Shane Warne'),'Cricket'),(row('3','Lewis Hamilton Wall Art','Formula One','Lewis Hamilton'),'Formula One')]:
            p=classify(fixture)
            self.assertEqual(p['status'],'Eligible');self.assertIn(sport,p['sports']);self.assertNotIn('Wall Art',p['title'])

    def test_rivalry_multiple_athletes_and_aliases(self):
        p=classify(row('4','Lewis Hamilton vs Max Verstappen Wall Art','Formula One','Lewis Hamilton'))
        self.assertIn('Lewis Hamilton',p['subjects']);self.assertIn('Max Verstappen',p['subjects'])
        p=classify(row(),{'subjects':['MJ','Michael Jordan']},{'MJ':'Michael Jordan'})
        self.assertEqual(p['subjects'],['Michael Jordan'])

    def test_exclusions_and_ambiguous_facts(self):
        fixture=row();fixture['status']='DRAFT';self.assertEqual(classify(fixture)['status'],'Excluded')
        fixture=row(edition={'exhausted':True});self.assertEqual(classify(fixture)['status'],'Excluded')
        self.assertEqual(classify(row(),{'excluded':True,'reason':'Owner choice'})['reason'],'Owner choice')
        fixture=row(title='Unclassified design',sport='Unknown',subject='Unknown');self.assertEqual(classify(fixture)['status'],'Needs details')
        self.assertEqual(classify(fixture,{'sports':['Tennis'],'subjects':['Verified player']})['status'],'Eligible')

    def test_selling_policy_does_not_use_quantity_alone(self):
        from product_quiz_worker import selling_policy
        def policy(tracked,rule,quantity,more=False):
            return {'variants':{'pageInfo':{'hasNextPage':more},'nodes':[{'inventoryQuantity':quantity,'inventoryPolicy':rule,'inventoryItem':{'tracked':tracked}}]}}
        self.assertIs(selling_policy(policy(True,'CONTINUE',0)),True)
        self.assertIs(selling_policy(policy(False,'DENY',0)),True)
        self.assertIs(selling_policy(policy(True,'DENY',0)),False)
        self.assertIsNone(selling_policy(policy(True,'DENY',0,True)))
        self.assertIsNone(selling_policy(policy(None,'DENY',0)))
        fixture=row();fixture['quiz_sellable']=False;self.assertEqual(classify(fixture)['status'],'Excluded')

    def test_private_metadata_never_reaches_public_shards(self):
        fixture=row();fixture['private_path']='dropbox://private';fixture['email']='private@example.test'
        public,_=compile_catalogue([fixture],{},{});encoded=json.dumps(public)
        self.assertNotIn('dropbox',encoded);self.assertNotIn('@',encoded);self.assertNotIn('raw_json',encoded)

    def test_catalogue_incremental_shards_and_dynamic_products(self):
        store=MemoryStore();assets=MemoryAssets();sync(store,assets)
        count=len([p for p in assets.writes if p.startswith('catalogue/')])
        sync(store,assets)
        self.assertEqual(len([p for p in assets.writes if p.startswith('catalogue/')]),count)
        store.rows.append(row('2','Shane Warne Wall Art','Cricket','Shane Warne'));sync(store,assets)
        self.assertIn('Cricket',assets.objects['catalogue.json']['sports'])
        store.rows[0]['status']='ARCHIVED';sync(store,assets)
        self.assertNotIn('Basketball',assets.objects['catalogue.json']['sports'])

    @patch('product_quiz_publish.asset_base',return_value='https://assets.example.test')
    def test_draft_publish_revert_and_failures(self,_base):
        store=MemoryStore();assets=MemoryAssets();sync(store,assets)
        first=publish(store,assets,DEFAULT)
        changed=deepcopy(DEFAULT);changed['appearance']['title']='Choose your edition'
        self.assertEqual(assets.objects['manifest.json']['version'],digest(DEFAULT))
        for fail in ('config/','runtime/','loader.js','manifest.json'):
            assets.fail=fail
            with self.assertRaises(OSError): publish(store,assets,changed)
            self.assertEqual(assets.objects['manifest.json'],{k:v for k,v in first.items() if k!='loader_url'})
        assets.fail=None;second=publish(store,assets,changed)
        self.assertNotEqual(first['version'],second['version'])
        revert(store,assets);self.assertEqual(assets.objects['manifest.json']['version'],first['version'])
        with self.assertRaises(ValueError): publish(store,assets,DEFAULT,expected_revision=9)
        wrong=deepcopy(DEFAULT);wrong['collections']={'basketball':'Cricket'}
        with self.assertRaises(ValueError): publish(store,assets,wrong)

    def test_analytics_rejects_pii_unknown_fields_and_fake_purchase(self):
        event=dict(event_id=str(uuid4()),session_id=str(uuid4()),version='a'*24,type='started',step='',source='page',product_id='')
        self.assertEqual(clean(event),event)
        with self.assertRaises(ValueError): clean({**event,'email':'person@example.test'})
        with self.assertRaises(ValueError): clean({**event,'type':'purchased'})
        with self.assertRaises(ValueError): clean({**event,'source':'person@example.test'})

    def test_anonymous_ingest_cors_limits_and_duplicate_acknowledgement(self):
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.testclient import TestClient
        from product_quiz_api import ingest
        seen=set()
        def insert(event):
            duplicate=event['event_id'] in seen;seen.add(event['event_id']);return not duplicate
        event=dict(event_id=str(uuid4()),session_id=str(uuid4()),version='a'*24,type='started',step='',source='page',product_id='')
        with patch.dict('os.environ',{'PRODUCT_QUIZ_ENABLED':'true'}),patch('product_quiz_store.QuizStore.event',side_effect=insert):
            with TestClient(Starlette(routes=[Route('/events',ingest,methods=['POST','OPTIONS'])])) as client:
                self.assertEqual(client.post('/events',json=event).status_code,403)
                headers={'Origin':'https://sportscaveshop.com'}
                self.assertEqual(client.options('/events',headers=headers).status_code,204)
                self.assertFalse(client.post('/events',headers=headers,json=event).json()['duplicate'])
                self.assertTrue(client.post('/events',headers=headers,json=event).json()['duplicate'])
                self.assertEqual(client.post('/events',headers=headers,content='x'*3000).status_code,413)
                self.assertEqual(client.post('/events',headers=headers,json={**event,'email':'private@example.test'}).status_code,400)

    def test_render_public_assets_allowlist_cache_cors_and_private_isolation(self):
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.testclient import TestClient
        from product_quiz_api import asset
        data={'body':b'{"version":"published"}','etag':'"public-only"'}
        with patch('product_quiz_api.public_bytes',return_value=data) as read:
            with TestClient(Starlette(routes=[Route('/product-quiz/{asset:path}',asset,methods=['GET','HEAD','OPTIONS'])])) as client:
                for path in ('draft.json','admin','../../private-artwork.psd','config/private.json','catalogue/a.json','runtime/'+('a'*24)+'.js/private'):
                    self.assertEqual(client.get('/product-quiz/'+path).status_code,404)
                read.assert_not_called()
                response=client.get('/product-quiz/manifest.json')
                self.assertEqual(response.status_code,200);self.assertEqual(response.json(),{'version':'published'})
                self.assertEqual(response.headers['access-control-allow-origin'],'*')
                self.assertNotIn('set-cookie',response.headers)
                self.assertIn('max-age=60',response.headers['cache-control'])
                self.assertEqual(client.get('/product-quiz/manifest.json',headers={'If-None-Match':'"public-only"'}).status_code,304)
                self.assertEqual(client.get('/product-quiz/manifest.json',headers={'If-None-Match':'W/"public-only"'}).status_code,304)
                self.assertEqual(client.get('/product-quiz/manifest.json',headers={'If-None-Match':'"old", W/"public-only"'}).status_code,304)
                self.assertEqual(client.head('/product-quiz/manifest.json').content,b'')
                response=client.get('/product-quiz/config/'+('a'*24)+'.json')
                self.assertIn('immutable',response.headers['cache-control'])
                self.assertEqual(client.post('/product-quiz/manifest.json').status_code,405)
                self.assertEqual(client.options('/product-quiz/manifest.json').status_code,204)

    def test_render_public_assets_use_private_durable_storage_and_fail_closed(self):
        from product_quiz_api import public_bytes,_ASSETS
        from types import SimpleNamespace
        _ASSETS.clear()
        path='catalogue/'+('b'*24)+'.json'
        body=io.BytesIO(b'{"title":"Published quiz"}')
        client=unittest.mock.Mock()
        client.get_object.return_value={'Body':body}
        with patch('product_quiz_publish.Assets',return_value=SimpleNamespace(client=client,bucket='existing-private-assets')):
            self.assertEqual(public_bytes(path)['body'],b'{"title":"Published quiz"}')
            client.get_object.assert_called_once_with(Bucket='existing-private-assets',Key='product-quiz/'+path)
            public_bytes(path);client.get_object.assert_called_once()
        _ASSETS.clear()
        client.get_object.return_value={'Body':io.BytesIO(b'x'*250001)}
        with patch('product_quiz_publish.Assets',return_value=SimpleNamespace(client=client,bucket='existing-private-assets')):
            with self.assertRaises(ValueError):public_bytes(path)
        _ASSETS.clear()

    def test_unpublished_config_hash_cannot_be_read(self):
        from product_quiz_api import public_bytes,_ASSETS
        from types import SimpleNamespace
        _ASSETS.clear()
        manifest={'config':'config/'+('a'*24)+'.json','runtime':'runtime/'+('a'*24)+'.js'}
        client=unittest.mock.Mock()
        client.get_object.return_value={'Body':io.BytesIO(json.dumps(manifest).encode())}
        with patch('product_quiz_publish.Assets',return_value=SimpleNamespace(client=client,bucket='private-assets')):
            with self.assertRaises(FileNotFoundError):public_bytes('config/'+('b'*24)+'.json')
            self.assertEqual(client.get_object.call_count,1)
            self.assertEqual(client.get_object.call_args.kwargs['Key'],'product-quiz/manifest.json')
        _ASSETS.clear()

    def test_snippets_are_minimal_and_manual(self):
        embeds=snippets('https://assets.example.test')
        for code in embeds.values():
            self.assertNotIn('iframe',code);self.assertIn('loader.js',code);self.assertLess(len(code),300)

    def test_isolated_editor_renders_and_saves_the_visible_draft(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('''
import streamlit as st
from copy import deepcopy
from tests.test_product_quiz import MemoryStore
from product_quiz import DEFAULT
from product_quiz_publish import compile_catalogue
from product_quiz_page import render_page
class FixtureStore(MemoryStore):
    def draft(self): return self.states.get('draft',{'revision':0,'config':deepcopy(DEFAULT)})
    def save(self,config,revision):
        self.states['draft']={'revision':revision+1,'config':deepcopy(config)}
        return self.states['draft']
if 'fixture_store' not in st.session_state:
    store=FixtureStore()
    _,review=compile_catalogue(store.rows,{},{})
    store.states['catalogue_status']={'products':review}
    st.session_state['fixture_store']=store
render_page({'role':'admin','is_active':True},store=st.session_state['fixture_store'])
''',default_timeout=10).run()
        self.assertEqual(list(app.exception),[])
        self.assertEqual([t.label for t in app.tabs],['Questions & answers','Matching rules','Catalogue','Appearance','Preview & publish','Analytics','Install'])
        next(t for t in app.text_input if t.label=='Title').set_value('Your next edition')
        next(b for b in app.button if b.label=='Save draft').click().run()
        self.assertEqual(list(app.exception),[])
        self.assertEqual(app.session_state['fixture_store'].draft()['config']['appearance']['title'],'Your next edition')


if __name__=='__main__': unittest.main()
