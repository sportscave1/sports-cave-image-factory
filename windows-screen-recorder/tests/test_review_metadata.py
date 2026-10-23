"""Real local relay regression: Stop must publish a metadata-only transition."""
import importlib.util
from pathlib import Path
import uuid
import sys

source = Path(__file__).resolve().parents[2] / 'tests/test_task_recorder_relay.py'
sys.path.append(str(source.parents[1]))
spec = importlib.util.spec_from_file_location('local_relay_fixture', source)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
# Use the preserved isolated metadata fixture, never production.
fixture.DSN = fixture.DSN.rsplit('/', 1)[0] + '/recorder_metadata_20261022'


class ReviewMetadata(fixture.RelayTests):
    def test_stop_review_ack_advances_sequence_without_snapshot_change(self):
        with fixture.connect() as conn:
            conn.execute('UPDATE task_recorder_private.devices SET needs_review=true WHERE id=%s', (self.device,))
        command = str(uuid.uuid4())
        self.relay.enqueue(self.owner, self.device, command, 'stop', {})
        self.poll()
        before = self.relay.devices(self.owner)[0]
        self.poll(acks=[{'id': command, 'status': 'applied', 'receipt': {}}])
        after = self.relay.devices(self.owner)[0]
        self.assertFalse(after['needs_review'])
        self.assertEqual(before['state'], after['state'])
        self.assertGreater(after['seq'], before['seq'], 'Compact poll observers must see acknowledged Stop metadata')
