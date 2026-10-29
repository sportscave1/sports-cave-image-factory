from pathlib import Path
import pytest
from PIL import Image
from tests.fixtures.recorder_disk_outputs import DiskOutputs


def test_actual_webp_bytes_missing_ack_and_no_overwrite(tmp_path):
    api = DiskOutputs(tmp_path / 'destination')
    folder = api.create_folder('local', api.base + '/Hockey', 'Recorder test')
    source = tmp_path / 'source.webp'
    Image.new('RGB', (32, 24), 'navy').save(source, 'WEBP')
    item = dict(relative_path='WEBP/image.webp', local_path=source, size=source.stat().st_size)
    target = folder['path_display']
    options = dict(conflict='cancel', progress_callback=lambda *a: None)
    api.fail_once = item['relative_path']
    assert api.upload_batch('local', target, [item], **options)['failures']
    local = api.local_path(target + '/' + item['relative_path'])
    assert not local.exists()
    receipt = api.upload_batch('local', target, [item], **options)
    assert len(receipt['successes']) == 1 and not receipt['failures']
    assert local.read_bytes() == source.read_bytes()
    with Image.open(local) as image:
        assert image.format == 'WEBP' and image.size == (32, 24)
    before = local.stat().st_mtime_ns
    assert api.upload_batch('local', target, [item], **options)['failures']
    assert local.stat().st_mtime_ns == before
    metadata = receipt['successes'][0]['metadata']
    assert api.get_metadata_if_exists('local', metadata['id']) == metadata
    local.write_bytes(b'changed test bytes')
    assert api.get_metadata_if_exists('local', metadata['id'])['content_hash'] != metadata['content_hash']


@pytest.mark.parametrize('suffix', ['../escape', 'Hockey/../../escape', 'Hockey/C:/escape', 'Hockey/a\\b'])
def test_output_scope_is_closed(tmp_path, suffix):
    api = DiskOutputs(tmp_path)
    with pytest.raises(ValueError):
        api.local_path(api.base + '/' + suffix)


def test_long_windows_destination_preserves_bytes(tmp_path):
    api = DiskOutputs(tmp_path)
    target = api.base + '/Hockey/' + 'product-' * 12
    source = tmp_path / 'source.webp'
    Image.new('RGB', (32, 24), 'navy').save(source, 'WEBP')
    name = 'WEBP/' + 'lifestyle-' * 10 + '.webp'
    receipt = api.upload_batch('local', target,
        [dict(relative_path=name, local_path=source, size=source.stat().st_size)],
        conflict='cancel', progress_callback=lambda *a: None)
    assert not receipt['failures']
    assert api.local_path(target + '/' + name).read_bytes() == source.read_bytes()
