import hashlib
import pytest
from desktop_recorder.output_manifest import OutputMappingError, collision_name, read_manifest, reconcile

CSV = 'role,filename\nMan Cave,a.png\nOffice,b.png\nLiving Room,c.png\n'


def witnesses(tmp_path):
    result = []
    for index, name in enumerate(['a.png', 'b.png', 'c.png']):
        path = tmp_path / name.replace('.png', ' (2).png')
        path.write_bytes(b'\x89PNG\r\n\x1a\n' + bytes([index]))
        result.append(dict(source_filename=name, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return result


def test_roles_follow_source_witness_not_download_order(tmp_path):
    items = witnesses(tmp_path)
    result = reconcile(CSV, list(reversed(items)))
    assert [r['role'] for r in result] == ['Man Cave', 'Office', 'Living Room']
    assert [r['source_filename'] for r in result] == ['a.png', 'b.png', 'c.png']


@pytest.mark.parametrize('text', [CSV.replace('Office', 'Man Cave'), CSV.replace('b.png', 'a.png'), CSV.replace('a.png', '../a.png'), CSV.replace('a.png', 'C:\\a.png'), CSV.replace('role,filename', 'filename,role'), CSV.replace('b.png', 'b.png,extra')])
def test_invalid_csv_refused(text):
    with pytest.raises(OutputMappingError): read_manifest(text)


def test_friendly_names_do_not_prove_random_csv_aliases(tmp_path):
    items = witnesses(tmp_path)
    with pytest.raises(OutputMappingError, match='no matching source'):
        reconcile(CSV.replace('a.png', 'exec-123.png'), items)


def test_old_or_modified_file_rejected(tmp_path):
    items = witnesses(tmp_path)
    (tmp_path / 'a (2).png').write_bytes(b'old unrelated image')
    with pytest.raises(OutputMappingError, match='changed'): reconcile(CSV, items)


def test_duplicate_outputs_rejected(tmp_path):
    items = witnesses(tmp_path)
    data = (tmp_path / 'a (2).png').read_bytes()
    (tmp_path / 'b (2).png').write_bytes(data)
    items[1]['sha256'] = items[0]['sha256']
    with pytest.raises(OutputMappingError, match='distinct'): reconcile(CSV, items)


def test_only_browser_collision_suffix_is_accepted():
    assert collision_name('random.png', 'random (12).png')
    assert not collision_name('random.png', 'random-old.png')
    assert not collision_name('random.png', 'random.png.crdownload')


def test_corrected_manifest_preserves_original_aliases(tmp_path):
    import json
    from desktop_recorder.output_manifest import export_verified_mapping
    items=witnesses(tmp_path)
    for role,item in zip(['Man Cave','Office','Living Room'],items):item['role']=role
    original=tmp_path/'original.csv';original.write_text(CSV.replace('a.png','exec-a.png').replace('b.png','exec-b.png').replace('c.png','exec-c.png'))
    receipt=dict(request_id='test',conversation='retained',images=items,original_csv=str(original),original_csv_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),mapping_basis='native selected title and exact hash')
    source=tmp_path/'receipt.json';source.write_text(json.dumps(receipt))
    result=export_verified_mapping(source)
    assert 'a (2).png' in __import__('pathlib').Path(result['csv']).read_text()
    assert 'exec-a.png' in original.read_text()
    assert json.loads(__import__('pathlib').Path(result['manifest']).read_text())['original_csv_rows'][0]['filename']=='exec-a.png'
    original.write_text('changed')
    with pytest.raises(OutputMappingError,match='CSV changed'):export_verified_mapping(source)


def upload_inputs(tmp_path):
    items = reconcile(CSV, witnesses(tmp_path))
    manifest = dict(request_id='retained-request', conversation='retained-conversation', images=items)
    bindings = dict(request_id=manifest['request_id'], conversation=manifest['conversation'],
                    directory=str(tmp_path), images=[dict(role=r['role'], filename=r['source_filename'],
                    sha256=r['sha256']) for r in items])
    return manifest, bindings


def test_upload_preflight_returns_role_paths_independent_of_order(tmp_path):
    from desktop_recorder.output_manifest import verify_upload_mapping
    manifest, bindings = upload_inputs(tmp_path)
    manifest['images'].reverse()
    paths = verify_upload_mapping(manifest, bindings)
    assert paths['Man Cave'] == str(tmp_path / 'a (2).png')
    assert paths['Office'] == str(tmp_path / 'b (2).png')


@pytest.mark.parametrize('failure', ['swap', 'missing', 'changed', 'request', 'conversation',
                                    'duplicate_binding', 'duplicate_role', 'outside', 'relative'])
def test_upload_preflight_refuses_before_any_upload(tmp_path, failure):
    from pathlib import Path
    from desktop_recorder.output_manifest import verify_upload_mapping
    manifest, bindings = upload_inputs(tmp_path)
    rows = manifest['images']
    if failure == 'swap':
        rows[0]['role'], rows[1]['role'] = rows[1]['role'], rows[0]['role']
    elif failure == 'missing': Path(rows[0]['path']).unlink()
    elif failure == 'changed': Path(rows[0]['path']).write_bytes(b'changed')
    elif failure in ('request', 'conversation'):
        manifest['request_id' if failure == 'request' else 'conversation'] = 'another'
    elif failure == 'duplicate_binding': bindings['images'].append(dict(bindings['images'][0]))
    elif failure == 'duplicate_role': rows[0]['role'] = rows[1]['role']
    elif failure == 'outside':
        outside = tmp_path / 'outside'; outside.mkdir()
        path = Path(rows[0]['path']); copy = outside / path.name
        copy.write_bytes(path.read_bytes()); rows[0]['path'] = str(copy)
    elif failure == 'relative': bindings['directory'] = '.'
    with pytest.raises(OutputMappingError): verify_upload_mapping(manifest, bindings)


@pytest.mark.parametrize('failure', [None, 'intake', 'incomplete', 'missing_label', 'swap', 'changed', 'old_run', 'missing'])
def test_accepted_upload_requires_current_run_and_exact_originals(tmp_path, failure):
    from pathlib import Path
    from desktop_recorder.output_manifest import verify_upload_receipt
    manifest, bindings = upload_inputs(tmp_path)
    run = tmp_path / 'run'; folder = run / 'uploaded-originals'; folder.mkdir(parents=True)
    originals = {}
    for row, stem in zip(manifest['images'], ['01-man-cave-prompt', '02-office-prompt', '03-living-room-prompt']):
        path = folder / (stem + '.png'); path.write_bytes(Path(row['path']).read_bytes())
        originals[stem + '.txt'] = dict(path=str(path), sha256=row['sha256'])
    receipt = dict(intake='test-intake', synthetic_base=True, originals=originals,
                   readiness=dict(complete=True, ready_count=8, required_count=8, missing_labels=[]))
    first = originals['01-man-cave-prompt.txt']
    if failure == 'intake': receipt['intake'] = 'old-intake'
    elif failure == 'incomplete': receipt['readiness']['ready_count'] = 7
    elif failure == 'missing_label': receipt['readiness']['missing_labels'] = ['Office']
    elif failure == 'swap':
        originals['01-man-cave-prompt.txt'], originals['02-office-prompt.txt'] = originals['02-office-prompt.txt'], first
    elif failure == 'changed': Path(first['path']).write_bytes(b'wrong image')
    elif failure == 'old_run': run = tmp_path / 'another-run'
    elif failure == 'missing': Path(first['path']).unlink()
    if failure:
        with pytest.raises(OutputMappingError):
            verify_upload_receipt(receipt, manifest, bindings, intake='test-intake', run_dir=run)
    else:
        verified = verify_upload_receipt(receipt, manifest, bindings, intake='test-intake', run_dir=run)
        assert verified['synthetic_base'] is True
        assert verified['originals']['Office'] == str(folder / '02-office-prompt.png')
