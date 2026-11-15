import tempfile
import unittest
from pathlib import Path
from test_foundation import action, atomic, Store, Recording, Repository, Invalid
from desktop_recorder.catalogue import Catalogue

class SavedDurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Repository(self.temp.name, atomic, Store.revision)
        self.now = 0
        self.recording = Recording(self.repo, lambda:self.now)
        self.recording.record({'mode':'prepared','binding':None},indicator_visible=True)
        self.recording.accept(action(),generation=self.recording.generation,privacy='safe')

    def rows(self, repo=None):
        class Legacy:
            def list(self):return [{'id':'legacy','name':'Legacy','duration_ms':19,'revision':'old'}]
        return Catalogue(repo or self.repo,Legacy()).summaries()

    def test_pause_excluded_and_duration_survives_restart_without_revision_change(self):
        self.now=2; self.recording.pause(lambda:None)
        self.now=20; self.recording.resume(indicator_visible=True)
        self.now=23; self.recording.stop()
        saved=self.recording.save('Timed recording')
        before=(self.repo.root/(saved['id']+'.json')).read_bytes()
        restarted=Repository(self.temp.name,atomic,Store.revision)
        row=next(r for r in self.rows(restarted) if r['id']==saved['id'])
        self.assertEqual(row['duration_ms'],5000)
        self.assertEqual(row['revision'],saved['revision'])
        restarted.manage(saved['id'],name='Renamed')
        self.assertEqual(next(r for r in self.rows(restarted) if r['id']==saved['id'])['duration_ms'],5000)
        self.assertEqual((self.repo.root/(saved['id']+'.json')).read_bytes(),before)
        self.assertEqual(self.rows(restarted)[0]['duration_ms'],19)

    def test_old_recording_duration_remains_unknown_and_legacy_unchanged(self):
        task=self.recording.stop()
        saved=self.repo.save(task)
        row=next(r for r in self.rows() if r['id']==saved['id'])
        self.assertIsNone(row['duration_ms'])
        self.assertEqual(row['revision'],saved['revision'])

    def test_duplicate_save_does_not_rewrite_duration_or_actions(self):
        task=self.recording.stop()
        saved=self.repo.save(task,duration_ms=1234)
        path=self.repo.root/(saved['id']+'.json');before=path.read_bytes()
        self.repo.save(task,duration_ms=9999)
        self.assertEqual(self.repo.library()[saved['id']]['duration_ms'],1234)
        self.assertEqual(path.read_bytes(),before)
        for value in (-1,True,1.2,'5'):
            with self.assertRaises(Invalid): self.repo.save(task,duration_ms=value)
