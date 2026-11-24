"""Recovery identities must remain fresh without replenishing existing retries."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
from unittest.mock import patch
import pytest
import recovery_revision_cache as cache


def test_performance_edit_preserves_existing_recovery_revision():
    source=Path(__file__).resolve().parents[1]/'auto_editions_recovery.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==cache.OPTIMISED_RECOVERY_HASH
    assert cache.file_digest(source)==cache.PREVIOUS_RECOVERY_HASH


def test_change_invalidates_hash_even_with_restored_mtime(tmp_path):
    source=tmp_path/'source.py';source.write_bytes(b'original')
    first=cache.file_digest(source);stat=source.stat()
    source.write_bytes(b'modified')
    os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert cache.file_digest(source)==hashlib.sha256(b'modified').hexdigest()!=first
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert set(pool.map(lambda _:cache.file_digest(source),range(12)))=={cache.file_digest(source)}


def test_fresh_scan_rechecks_bytes_and_exception_releases_snapshot(tmp_path):
    source=tmp_path/'source.py';source.write_bytes(b'original')
    with pytest.raises(RuntimeError),cache.source_snapshot():
        first=cache.file_digest(source)
        raise RuntimeError('synthetic scan failure')
    assert cache._snapshot.get() is None
    stat=source.stat();source.write_bytes(b'modified')
    os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    with cache.source_snapshot():
        assert cache.file_digest(source)!=first


def test_changed_recovery_policy_is_not_translated_to_old_revision(tmp_path):
    source=tmp_path/'auto_editions_recovery.py';source.write_bytes(b'changed recovery policy')
    assert cache.file_digest(source)==hashlib.sha256(source.read_bytes()).hexdigest()


def test_mid_read_change_fails_closed_and_next_read_recovers(tmp_path):
    source=tmp_path/'source.py';source.write_bytes(b'original')
    read=Path.read_bytes
    def changed(path):
        value=read(path);path.write_bytes(b'modified');return value
    with patch.object(Path,'read_bytes',changed),pytest.raises(OSError,match='source changed'):
        cache.file_digest(source)
    assert cache.file_digest(source)==hashlib.sha256(b'modified').hexdigest()


def test_repeated_read_avoids_source_transfer_and_cache_is_bounded(tmp_path):
    source=tmp_path/'source.py';source.write_bytes(b'unchanged')
    with cache.source_snapshot(),patch.object(Path,'read_bytes',autospec=True,return_value=b'unchanged') as read:
        assert len({cache.file_digest(source) for _ in range(12)})==1
        assert read.call_count==1
    with cache.source_snapshot():
        for number in range(140):
            path=tmp_path/str(number);path.write_bytes(b'data');cache.file_digest(path)
        assert len(cache._snapshot.get())==128
    assert cache._snapshot.get() is None
