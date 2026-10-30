"""Real local relay regression: Stop must publish a metadata-only transition."""
import importlib.util
from pathlib import Path
import uuid
import sys
import os
import unittest

# This integration fixture requires a separately provisioned disposable database.
# Ordinary offline recorder checks must not try a historical database indefinitely.
if os.environ.get('SC_RECORDER_METADATA_POSTGRES_TEST') != '1':
    raise unittest.SkipTest('Set SC_RECORDER_METADATA_POSTGRES_TEST=1 only with the local recorder metadata fixture provisioned')

source = Path(__file__).resolve().parents[2] / 'tests/test_task_recorder_relay.py'
sys.path.append(str(source.parents[1]))
spec = importlib.util.spec_from_file_location('local_relay_fixture', source)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
# Use the preserved isolated metadata fixture, never production.
fixture.DSN = fixture.DSN.rsplit('/', 1)[0] + '/recorder_metadata_20261022'
from psycopg.conninfo import conninfo_to_dict
settings = conninfo_to_dict(fixture.DSN)
if settings.get('host') not in {'localhost', '127.0.0.1', '::1'} or settings.get('dbname') != 'recorder_metadata_20261022':
    raise RuntimeError('Recorder metadata tests require the isolated loopback database')
fixture.connect = lambda: fixture.psycopg.connect(fixture.DSN, row_factory=fixture.dict_row, connect_timeout=3)


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
