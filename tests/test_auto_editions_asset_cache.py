import hashlib

from auto_editions_asset_cache import AssetCache


def test_cache_reuses_verified_bytes_and_rejects_corruption(tmp_path):
    cache = AssetCache(8)
    source = tmp_path / 'source'; source.write_bytes(b'asset')
    digest = hashlib.sha256(b'asset').hexdigest()
    cache.remember(digest, source)
    out = tmp_path / 'copy'
    assert cache.copy(digest, out) and out.read_bytes() == b'asset'
    cache.entries[digest].write_bytes(b'wrong')
    assert not cache.copy(digest, out)
    assert not cache.entries


def test_cache_bounds_and_wrong_digest(tmp_path):
    cache = AssetCache(5)
    source = tmp_path / 'source'
    source.write_bytes(b'first')
    first = hashlib.sha256(b'first').hexdigest()
    cache.remember(first, source)
    source.write_bytes(b'next')
    second = hashlib.sha256(b'next').hexdigest()
    cache.remember(first, source)
    cache.remember(second, source)
    assert list(cache.entries) == [second]
    source.write_bytes(b'too large')
    cache.remember(hashlib.sha256(source.read_bytes()).hexdigest(), source)
    assert list(cache.entries) == [second]
