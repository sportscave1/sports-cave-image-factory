import json
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
import test_phase2 as phase
from test_foundation import action, Invalid
from desktop_recorder.coordinator import Coordinator
from desktop_recorder.coordinator import action_log


class RecoveryTests(unittest.TestCase):
    setUp = phase.Phase2Tests.setUp
    start = phase.Phase2Tests.start
    event = phase.Phase2Tests.event

    def failed_run(self, returned=True):
        self.start()
        a = action()
        a.update(version=2, kind='set_text', requires=['uia.value.v2'], value='synthetic')
        a['target'].update(control_type='Edit', name='Test field', scope=[])
        self.event(a)
        self.c.apply(phase.command('stop'))
        saved = self.c.apply(phase.command('save', {'name':'Recovery fixture'}))['last_saved']
        self.saved = dict(id=saved['id'], revision=saved['revision'])
        self.c.apply(phase.command('play', self.saved))
        self.c.apply(phase.command('play_ready'))
        if returned:
            self.c.apply(phase.command('play_result',dict(step=0,verified=False,message='Synthetic verification failure')))
        return self.c.playback.run

    def payload(self, run):
        return dict(run_id=run['id'], revision=run['revision'], step=0,
                    evidence='Checked synthetic field and reset it.', reviewed=True)

    def test_review_preserves_history_and_never_dispatches(self):
        run = self.failed_run()
        task_path = self.c.repository.root / (run['task_id']+'.json')
        original = task_path.read_bytes()
        self.assertEqual(len(self.c.state()['reviews']),1)
        cmd = phase.command('reconcile', self.payload(run))
        state = self.c.apply(cmd)
        self.assertEqual(state['run']['state'],'stopped')
        self.assertEqual(state['instruction']['kind'],'disarm')
        self.assertEqual(state['reviews'],[])
        self.assertEqual(state['run']['results'],[])
        self.assertEqual(task_path.read_bytes(),original)
        self.c.apply(cmd)  # Duplicate receipt must not execute anything.
        self.c.apply(phase.command('play',self.saved))
        self.assertEqual(self.c.native_instruction['kind'],'arm')

    def test_inflight_cannot_be_reviewed(self):
        run=self.failed_run(returned=False)
        self.assertEqual(self.c.state()['reviews'],[])
        with self.assertRaises(Invalid): self.c.apply(phase.command('reconcile',self.payload(run)))
        with self.assertRaises(Invalid): self.c.apply(phase.command('inspect_task',self.saved))
        self.assertEqual(self.c.playback.run['state'],'uncertain')

    def test_crash_recovery_is_reviewable_but_never_replayed(self):
        run=self.failed_run(returned=False)
        self.c=Coordinator(Path(self.tmp.name))
        self.assertIsNone(self.c.native_instruction)
        self.assertEqual(len(self.c.state()['reviews']),1)
        self.c.apply(phase.command('reconcile',self.payload(run)))
        journal=json.loads((self.c.playback.root/(run['id']+'.json')).read_text())
        self.assertEqual(journal['state'],'stopped')
        self.assertFalse(journal['result_received'])
        self.assertEqual(journal['results'],[])
        self.assertEqual(self.c.recovered_runs[0]['state'],'stopped')

    def test_stale_or_unreviewed_requests_cannot_clear_failure(self):
        run=self.failed_run()
        for changes in ({'reviewed':False},{'step':True},{'step':1},{'revision':'old'},
                        {'evidence':''},{'evidence':'x'*501}):
            with self.assertRaises(Invalid):
                self.c.apply(phase.command('reconcile',{**self.payload(run),**changes}))
        self.assertEqual(len(self.c.state()['reviews']),1)

    def test_failed_journal_write_keeps_review_available(self):
        run=self.failed_run()
        with patch.object(self.c.repository,'atomic',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.c.apply(phase.command('reconcile',self.payload(run)))
        self.assertEqual(len(self.c.state()['reviews']),1)
        self.assertEqual(self.c.playback.run['state'],'uncertain')

    def test_log_is_bounded_and_does_not_copy_field_contents(self):
        run=self.failed_run()
        task=self.c.repository.get(run['task_id'])
        task['actions'] *= 20
        lines=action_log(task)
        self.assertEqual(len(lines),13)
        self.assertEqual(lines[0],'Latest 12 of 20 actions')
        self.assertNotIn('synthetic','\n'.join(lines))
        self.assertIn('20. Set text: Test field',lines[-1])

    def test_log_distinguishes_confirmed_and_pending_actions(self):
        run=self.failed_run(returned=False)
        task=self.c.repository.get(run['task_id'])
        self.assertIn('awaiting confirmation',action_log(task,run)[0])
        self.c.playback.acknowledge(0,verified=True)
        self.assertIn('verified',action_log(task,self.c.playback.run)[0])

    def test_only_selected_task_preview_is_transmitted_without_execution(self):
        run=self.failed_run()
        task=self.c.repository.get(run['task_id'])
        copy={**task,'id':str(uuid4()),'name':'Second fixture'}
        self.c.repository.atomic(self.c.repository.root/(copy['id']+'.json'),copy)
        state=self.c.apply(phase.command('inspect_task',dict(id=copy['id'],revision=self.c.repository.revision(copy))))
        previews=[row for row in state['tasks'] if 'action_log' in row]
        self.assertEqual([row['id'] for row in previews],[copy['id']])
        self.assertEqual(state['instruction']['kind'],'disarm')
        self.assertEqual(self.c.playback.run['id'],run['id'])
        self.assertEqual(self.c.playback.run['state'],'uncertain')
