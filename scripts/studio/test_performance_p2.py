"""Focused checks for optimized capability scope and ordered input boundary."""
import unittest,time
from unittest.mock import patch
import studio,preview_input
import test_v6

class PerformanceScopeTests(unittest.TestCase):
    def setUp(self):
        fixture=test_v6.V6Tests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fixture=fixture;self.server=fixture.server()
        self.grant=self.server.workspace_grant(fixture.draft['id'])
    def call(self):
        return self.server.workspace_request({**self.grant,'command':{'action':'editor-files'}})
    def test_workspace_validates_without_building_full_catalog(self):
        with patch.object(self.server,'catalog',side_effect=AssertionError('Full catalog on hot path')):
            self.assertTrue(self.call()['files'])
        with studio.locked(self.fixture.home) as file:
            registry=studio.read(file);registry['tasks'][0]['owner']='other';studio.atomic(file,registry)
        with self.assertRaises(RuntimeError):self.call()
    def test_grant_cannot_redirect_to_reassigned_task(self):
        self.server.workspace_grants[self.grant['capability']]['task']='other'
        with self.assertRaises((RuntimeError,ValueError)):self.call()
    def test_expired_grant_still_fails_before_dispatch(self):
        self.server.workspace_grants[self.grant['capability']]['expires']=time.monotonic()-1
        with self.assertRaises(ValueError):self.call()
class FreshIdentityTests(unittest.TestCase):
    def test_fresh_identity_rejects_branch_common_dir_and_nested_root(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[2]
        branch=studio.git(root,'branch','--show-current')
        if not branch:self.skipTest('A registered editor worktree requires an attached branch')
        registry={'common_dir':studio.common(root)};task={'worktree_path':str(root),'branch':branch}
        self.assertEqual(studio.identity(registry,task),root)
        with self.assertRaises(RuntimeError):studio.identity(registry,{**task,'branch':'wrong-branch'})
        with self.assertRaises(RuntimeError):studio.identity({**registry,'common_dir':str(root.parent)},task)
        with self.assertRaises(RuntimeError):studio.identity(registry,{**task,'worktree_path':str(root/'scripts')})
        with patch.object(studio,'git',return_value=registry['common_dir']+'\n'+str(root)+'\nHEAD'):
            with self.assertRaises(RuntimeError):studio.identity(registry,{**task,'branch':'HEAD'})

class InputBatchTests(unittest.TestCase):
    def test_order_and_copy(self):
        data={'page':'orders','events':[{'action':'text','text':'ab'},{'action':'key','key':'Tab'},{'action':'scroll','delta':400},{'action':'key','key':'Enter'}]}
        result=preview_input.validate_batch(data);self.assertEqual(result,data['events']);self.assertIsNot(result[0],data['events'][0])
    def test_rejects_arbitrary_and_oversized_operations(self):
        for event in ({'action':'evaluate','script':'evil'},{'action':'key','key':'Control+L'},{'action':'text','text':'x'*2001},{'action':'scroll','delta':True},{'action':'scroll','delta':901},{'action':'text','text':'ok','url':'https://example.invalid'}):
            with self.assertRaises(ValueError):preview_input.validate_batch({'page':'orders','events':[event]})
        for events in ([],[{'action':'key','key':'Tab'}]*9,[{'action':'key','key':'Enter'},{'action':'text','text':'after submit'}],[{'action':'text','text':'a'*1500},{'action':'text','text':'b'*1500}]):
            with self.assertRaises(ValueError):preview_input.validate_batch({'page':'orders','events':events})
if __name__=='__main__':unittest.main()
