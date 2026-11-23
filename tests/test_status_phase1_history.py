import pytest
from tests.status_phase1_history import artwork_baseline


def test_rejects_substituted_historical_source(tmp_path, monkeypatch):
    source = tmp_path / 'substitute.py'
    source.write_text('raise RuntimeError("wrong source")')
    monkeypatch.setenv('STATUS_TEST_ARTWORK_BASELINE', str(source))
    with pytest.raises(ValueError, match='digest mismatch'):
        artwork_baseline(tmp_path)
