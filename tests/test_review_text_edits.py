"""Customer-requested text corrections: synthetic local SQL and OS form only."""
from contextlib import contextmanager
import json
import os
import unittest
import uuid
from unittest.mock import Mock,patch
from reviews_store import ReviewsStore
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN,WORKER


class AccessAndUiTests(unittest.TestCase):
    def test_edit_requires_reviews_access_before_storage(self):
        connection=Mock();store=ReviewsStore(connection)
        with self.assertRaises(PermissionError):
            store.edit_text(WORKER,str(uuid.uuid4()),title='',body='',reason='Customer request',expected_updated_at='1')
        connection.assert_not_called()

    def test_form_opens_from_row_and_preserves_initial_version(self):
        from streamlit.testing.v1 import AppTest
        identity='00000000-0000-0000-0000-000000000001'
        script='''
import streamlit as st
from unittest.mock import Mock,patch
from reviews_page import render_page
from tests.test_crm import ADMIN
r=dict(id="00000000-0000-0000-0000-000000000001",created_at="2026-01-01",updated_at="original",reviewer_name="Synthetic collector",rating=4,title="Original title",body="Original words",verified_purchase=False,source="csv",status="PUBLISHED",product_title="Fixture product")
store=st.session_state.setdefault('fixture_store',Mock());store.connect=None
if not isinstance(store.get_review.return_value,dict):store.get_review.return_value=r
summary=dict(average=4,total=1,recent=0,five_rate=0,attention=1)
with patch('reviews_page.read',side_effect=lambda state,key,*args:(summary if key[0]=='summary' else [r],'READY')),patch('reviews_page.acknowledge_visible'):
 render_page(ADMIN,store=store)
'''
        app=AppTest.from_string(script).run()
        self.assertEqual(len(app.exception),0)
        app.button(key='review_edit_'+identity).click().run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any(v.label=='Review text' for v in app.text_area))
        # AppTest reruns whole scripts rather than a browser's dialog fragment.
        form_script=script[:script.index('summary=')]+'''\nfrom reviews_page import edit_review
edit_review.__wrapped__(store,ADMIN,r['id'])
'''
        app=AppTest.from_string(form_script).run()
        next(v for v in app.text_input if v.label=='Review title').set_value('')
        next(v for v in app.text_area if v.label=='Review text').set_value('')
        next(v for v in app.text_input if v.label=='Reason for edit').set_value('Customer requested text removal')
        app.session_state['fixture_store'].get_review.return_value['updated_at']='newer'
        next(v for v in app.button if v.label=='Save changes').click().run()
        self.assertEqual(len(app.exception),0)
        call=app.session_state['fixture_store'].edit_text.call_args
        self.assertEqual(call.kwargs,dict(title='',body='',reason='Customer requested text removal',expected_updated_at='original'))


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class EditTests(unittest.TestCase):
    def setUp(self):
        self.store=ReviewsStore(connect);self.identity=str(uuid.uuid4())
        self.store.q("INSERT INTO sc_reviews(id,source,reviewer_name,rating,dedupe_key,title,body,status) VALUES(%s,'csv','Synthetic reviewer',4,%s,'Original title','Original review','PUBLISHED')",(self.identity,self.identity))
        self.before=self.store.get_review(self.identity)
        self.addCleanup(lambda:self.store.q("UPDATE sc_reviews SET status='ARCHIVED' WHERE id=%s",(self.identity,)))

    def edit(self,**extra):
        return self.store.edit_text(ADMIN,self.identity,**dict(title='',body='',reason='Customer requested removal',expected_updated_at=self.before['updated_at'],**extra))

    def audits(self):return self.store.q("SELECT * FROM sc_review_audit WHERE review_id=%s AND action LIKE 'edit:%%'",(self.identity,))

    def test_rating_only_retains_identity_totals_and_arrival_and_records_original(self):
        count=self.store.aggregate()
        with patch('reviews_rewards.register') as rewards,patch('reviews_public_cache.CACHE.invalidate') as invalidated:
            self.assertTrue(self.edit());rewards.assert_not_called();invalidated.assert_called_once()
        row=self.store.get_review(self.identity)
        for key in ('rating','status','reviewer_name','created_at','source','dedupe_key','notification_received_at'):
            self.assertEqual(row[key],self.before[key])
        self.assertEqual((row['title'],row['body']),('',''));self.assertEqual(self.store.aggregate(),count)
        audit=self.audits()[0];change=json.loads(audit['action'][5:])
        self.assertEqual(audit['actor'],ADMIN['id']);self.assertEqual(change['before'],{'title':'Original title','body':'Original review'})
        self.assertEqual(change['after'],{'title':'','body':''});self.assertEqual(change['rating'],4)

    def test_stale_save_is_rejected_and_noop_does_not_add_audit(self):
        self.assertFalse(self.store.edit_text(ADMIN,self.identity,title=self.before['title'],body=self.before['body'],reason='Customer requested correction',expected_updated_at=self.before['updated_at']))
        self.assertEqual(self.audits(),[])
        self.store.q("UPDATE sc_reviews SET updated_at=now(),body='Newer customer text' WHERE id=%s",(self.identity,))
        with self.assertRaisesRegex(ValueError,'changed'):self.edit()
        self.assertEqual(self.store.get_review(self.identity)['body'],'Newer customer text');self.assertEqual(self.audits(),[])

    def test_validation_and_sanitization(self):
        with self.assertRaises(ValueError):self.store.edit_text(ADMIN,self.identity,title='',body='',reason='',expected_updated_at=self.before['updated_at'])
        self.store.edit_text(ADMIN,self.identity,title='<b>Correction</b>',body='<script>bad()</script>Approved text',reason='Customer correction',expected_updated_at=self.before['updated_at'])
        self.assertEqual(self.store.get_review(self.identity)['body'],'Approved text')
        self.assertEqual(self.store.get_review(self.identity)['title'],'Correction')

    def test_failed_audit_rolls_back_text(self):
        original=self.store.db
        @contextmanager
        def broken_audit():
            with original() as conn:
                def execute(sql,args=()):
                    if sql.startswith('INSERT INTO sc_review_audit'):raise RuntimeError('Synthetic audit failure')
                    return conn.execute(sql,args)
                yield Mock(execute=execute)
        with patch.object(self.store,'db',broken_audit):
            with self.assertRaises(RuntimeError):self.edit()
        self.assertEqual(self.store.get_review(self.identity)['body'],'Original review');self.assertEqual(self.audits(),[])
