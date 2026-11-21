from copy import deepcopy
from types import SimpleNamespace
import pytest
import product_upload_mapping as mapping
from product_upload_dropbox import ROOTS

@pytest.mark.parametrize('change', ['none', 'content_hash', 'size', 'id', 'path_display', 'unverified'])
def test_recovered_move_requires_verified_identical_bytes(monkeypatch, change):
    source = dict(id='id:original', rev='old', content_hash='a'*64, size=100,
                  path_display=ROOTS['review']+'/original.psd')
    current = dict(source, rev='moved', path_display=ROOTS['live']+'/original.psd')
    row = {'data': {'source': source, 'staff_mapping': {'verified': True, 'source': deepcopy(source)}}}
    monkeypatch.setattr(mapping, 'operation', lambda row: {'source': source})
    if change == 'unverified': row['data']['staff_mapping']['verified'] = False
    elif change != 'none': current[change] = 101 if change == 'size' else 'different'
    service = object.__new__(mapping.Mapping)
    service.provider = SimpleNamespace(metadata_if_present=lambda _: current)
    if change == 'none':
        assert service.source(row) == current
        assert source['rev'] == 'old'
    else:
        with pytest.raises(ValueError, match='captured PSD changed'):
            service.source(row)
