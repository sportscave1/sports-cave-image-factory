import ast
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock
import os_accounts as accounts
import psd_directory as psd
from psd_mapping_store import PostgresMappings,MappingConflict
PID='gid://shopify/Product/1'
META={'.tag':'file','id':'id:one','name':'Art.psd','path_display':psd.ROOT+'/Art.psd'}
VA={'id':'test-va','role':'worker','is_active':True,'page_permissions':['files','attach_missing_psd']}
ADMIN={'id':'test-admin','role':'admin','is_active':True}

class Cursor:
    def __init__(self,rows=None):self.rows=rows or {};self.calls=[];self.write=None
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,args=()):
        self.calls.append((sql,args));self.last=sql
        if sql.startswith('INSERT INTO public.product_psd_mappings'):
            self.write={'shopify_product_gid':args[0],'dropbox_file_id':args[1],'file_path':args[2],'source':'manual','actor_id':args[4]}
    def fetchall(self):
        if 'FROM edition_products' in self.last:return [{'product_title':'Art','shopify_handle':'art'}]
        return list(self.rows.values())
    def fetchone(self):return self.write

class VaAttachmentTests(unittest.TestCase):
    def store(self,rows=None):
        self.cur=Cursor(rows);connection=Mock();connection.cursor.return_value=self.cur
        return PostgresMappings(connect=lambda:nullcontext(connection))
    def existing(self,pid=PID,fid='id:old',source='manual'):
        return {pid:{'shopify_product_gid':pid,'dropbox_file_id':fid,'file_path':META['path_display'],'source':source}}
    def test_explicit_capability_requires_files_active_account_and_does_not_grant_other_power(self):
        self.assertTrue(accounts.can_attach_missing_psd(VA));self.assertTrue(accounts.can_attach_missing_psd(ADMIN))
        for user in [{**VA,'page_permissions':['files']},{**VA,'page_permissions':['attach_missing_psd']},{**VA,'is_active':False}]:self.assertFalse(accounts.can_attach_missing_psd(user))
        self.assertFalse(accounts.is_admin(VA));self.assertFalse(accounts.can_delete_files(VA))
    def test_permission_storage_is_opt_in_and_accounts_ui_exposes_existing_checkbox(self):
        cur=Mock();selected=accounts.PostgresAccountStore._replace_permissions(cur,'test-va',['files','attach_missing_psd'])
        self.assertIn('attach_missing_psd',selected)
        self.assertNotIn('attach_missing_psd',accounts.PostgresAccountStore._replace_permissions(cur,'test-va',['files']))
        tree=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8'))
        field=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_account_permission_fields')
        source=ast.get_source_segment((Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8'),field)
        self.assertIn('Attach Missing PSD',source);self.assertIn('ATTACH_MISSING_PSD_CAPABILITY in selected',source)
    def test_actual_account_permission_widget_is_off_by_default_and_selectable(self):
        from streamlit.testing.v1 import AppTest
        source=(Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8')
        tree=ast.parse(source);field=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_account_permission_fields')
        script='import streamlit as st\nimport os_accounts\n'+ast.get_source_segment(source,field)+"\nchosen=_account_permission_fields('va-test',['files'])\nst.json(chosen)\n"
        page=AppTest.from_string(script).run()
        checkbox=next(box for box in page.checkbox if box.label=='Attach Missing PSD')
        self.assertFalse(checkbox.value);self.assertFalse(page.exception)
        checkbox.check().run()
        self.assertTrue(next(box for box in page.checkbox if box.label=='Attach Missing PSD').value)
        self.assertIn('attach_missing_psd',page.json[0].value)

    def test_only_admin_can_grant_capability_through_account_service(self):
        store=Mock()
        for actor in [VA,None,{**ADMIN,'is_active':False}]:
            with self.assertRaisesRegex(PermissionError,'Only an administrator'):
                accounts.create_worker_account(username='local-va',display_name='Local VA',password='Test-Password-2026!',page_keys=['files','attach_missing_psd'],actor=actor,store=store)
            store.create_user.assert_not_called()
            with self.assertRaises(PermissionError):
                accounts.update_worker_account('local-va',username='local-va',display_name='Local VA',is_active=True,page_keys=['files','attach_missing_psd'],actor=actor,store=store)
            store.update_worker.assert_not_called()
        accounts.create_worker_account(username='local-va',display_name='Local VA',password='Test-Password-2026!',page_keys=['files','attach_missing_psd'],actor=ADMIN,store=store)
        self.assertIn('attach_missing_psd',store.create_user.call_args.kwargs['page_keys'])

    def test_authorised_va_can_attach_missing_with_actor_audit(self):
        store=self.store();result=store.attach(PID,META,VA)
        self.assertEqual(result['dropbox_file_id'],'id:one');self.assertEqual(result['actor_id'],'test-va')
        self.assertTrue(self.cur.calls[0][0].startswith('LOCK TABLE'))
        audits=[args for sql,args in self.cur.calls if 'INSERT INTO public.product_psd_mapping_audit' in sql]
        self.assertEqual(len(audits),1);self.assertEqual(audits[0][1:3],('attach','test-va'));self.assertIsNone(audits[0][3])
    def test_va_cannot_overwrite_even_same_file_or_racing_existing_mapping(self):
        for source in ['manual','automatic']:
            for fid in ['id:old','id:one']:
                store=self.store(self.existing(fid=fid,source=source))
                with self.assertRaisesRegex(PermissionError,'Only an administrator'):store.attach(PID,META,VA)
                self.assertIsNone(self.cur.write)
        for flags in [{'expected_file_id':'id:old'},{'confirm_replace':True}]:
            store=self.store()
            with self.assertRaises(PermissionError):store.attach(PID,META,VA,**flags)
            self.assertEqual(self.cur.calls,[])
    def test_duplicate_review_mismatch_unapproved_and_missing_actor_rejected(self):
        store=self.store(self.existing('gid://shopify/Product/2','id:one'))
        with self.assertRaisesRegex(MappingConflict,'another product'):store.attach(PID,META,VA)
        self.assertIsNone(self.cur.write)
        for meta in [{**META,'path_display':psd.ROOT+'/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/Art.psd'},{**META,'name':'Art.jpg','path_display':psd.ROOT+'/Art.jpg'}]:
            store=self.store()
            with self.assertRaises(ValueError):store.attach(PID,meta,VA)
            self.assertEqual(self.cur.calls,[])
        store=self.store()
        with self.assertRaisesRegex(ValueError,'explicit confirmation'):store.attach(PID,{**META,'name':'Different.psd','path_display':psd.ROOT+'/Different.psd'},VA)
        self.assertIsNone(self.cur.write)
        self.assertTrue(store.attach(PID,{**META,'name':'Different.psd','path_display':psd.ROOT+'/Different.psd'},VA,confirm_mismatch=True))
        store=self.store()
        with self.assertRaises(PermissionError):store.attach(PID,META,{**VA,'id':''})
        self.assertIsNone(self.cur.write)
    def test_admin_replacement_still_requires_expected_id_and_confirmation(self):
        store=self.store(self.existing())
        with self.assertRaises(MappingConflict):store.attach(PID,META,ADMIN)
        with self.assertRaises(MappingConflict):store.attach(PID,META,ADMIN,expected_file_id='id:old')
        result=store.attach(PID,META,ADMIN,expected_file_id='id:old',confirm_replace=True)
        self.assertEqual(result['source'],'manual')
        audit=[args for sql,args in self.cur.calls if 'INSERT INTO public.product_psd_mapping_audit' in sql][-1]
        self.assertEqual(audit[1:3],('replace','test-admin'))

if __name__=='__main__':unittest.main()
