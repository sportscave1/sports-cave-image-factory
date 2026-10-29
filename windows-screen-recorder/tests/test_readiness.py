import copy
import hashlib
import json
import subprocess
import sys
import pytest
from desktop_recorder.contract import Invalid
from desktop_recorder.readiness import inspect, fingerprint, load_document


@pytest.fixture
def prepared(tmp_path):
    files = []
    for i in range(8):
        path = tmp_path/f'{i}.webp'
        path.write_bytes(f'OFFLINE CONTRACT BYTES {i}'.encode())
        files.append(dict(role=f'role-{i}', id=f'file-{i}', revision=f'rev-{i}',
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), local_path=str(path),
            destination_path=f'/RecorderNonproduction/offline/{i}.webp'))
    prompt = tmp_path/'prompt.txt'; prompt.write_text('OFFLINE ONLY — never send', encoding='utf-8')
    manifest = dict(store=dict(id='offline', domain='offline-dev.myshopify.com', kind='development'),
        destination=dict(namespace_id='offline', root='/RecorderNonproduction/offline', test_only=True),
        target=dict(id='offline-draft', store_id='offline', state='DRAFT', isolated=True),
        browser=dict(family='edge', profile='offline', extension_instance='offline', file_url_access=True,
            conversation_url='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b-sc-mockups-uploads/c/6ae2d62d-1338-83ec-8619-6ea3635a7fa0',
            source_url='http://127.0.0.1:18963/?page=product_uploads',
            mapping_url='http://127.0.0.1:18963/?page=edition_ops'), files=files,
        prompt=dict(path=str(prompt), sha256=hashlib.sha256(prompt.read_bytes()).hexdigest()))
    return manifest


def approval(manifest):
    return dict(manifest_sha256=fingerprint(manifest), evidence_id='OFFLINE TEST ONLY',
                required_roles=[f'role-{i}' for i in range(8)])


def test_local_pass_never_authorizes_external_effect(prepared):
    result = inspect(prepared, approval(prepared))
    assert result['files_checked'] == 8 and result['local_contract_passed']
    assert not result['may_send'] and not result['external_ready']
    assert result == inspect(prepared, approval(prepared))


@pytest.mark.parametrize('field', ['store', 'destination', 'target', 'browser', 'files', 'prompt'])
def test_missing_sections_fail_closed(prepared, field):
    del prepared[field]
    with pytest.raises(Invalid): inspect(prepared, approval(prepared))


@pytest.mark.parametrize('section,field,value', [
    ('store','id','SPORTSCAVE-NB'), ('store','domain','sportscave-nb.myshopify.com'),
    ('store','kind','production'), ('store','domain','https://offline-dev.myshopify.com'),
    ('destination','test_only',False), ('destination','namespace_id',''),
    ('destination','root','/Sportscave Team Folder/04_OUTPUT'),
    ('destination','root','/RecorderNonproduction/../production'),
    ('target','isolated',False), ('target','state','ACTIVE'), ('target','store_id','other'),
    ('browser','family','unknown'), ('browser','profile',''), ('browser','file_url_access',False),
    ('browser','conversation_url','https://chatgpt.com/c/6ae2d62d-1338-83ec-8619-6ea3635a7fa0'),
    ('browser','source_url','https://sports-cave-image-factory.onrender.com/?page=product_uploads'),
    ('browser','mapping_url','http://127.0.0.1:18964/?page=edition_ops'),
    ('browser','mapping_url','http://127.0.0.1:18963/?page=edition_ops#other'),
    ('browser','mapping_url','http://evil.example/?page=edition_ops'),
])
def test_invalid_or_production_values_refused_even_if_manifest_approved(prepared, section, field, value):
    prepared[section][field] = value
    with pytest.raises(Invalid): inspect(prepared, approval(prepared))


@pytest.mark.parametrize('damage', ['missing','changed','swapped','duplicate_id','duplicate_path',
    'duplicate_role','duplicate_hash','missing_revision','simulated_revision','outside','traversal','seven','nine'])
def test_files_fail_closed(prepared, damage):
    from pathlib import Path
    files = prepared['files']; first = files[0]
    if damage == 'missing': Path(first['local_path']).unlink()
    elif damage == 'changed': Path(first['local_path']).write_bytes(b'CHANGED')
    elif damage == 'swapped': first['local_path'],files[1]['local_path'] = files[1]['local_path'],first['local_path']
    elif damage.startswith('duplicate_'):
        field = dict(id='id',path='local_path',role='role',hash='sha256')[damage[10:]]
        files[1][field] = first[field]
    elif damage == 'missing_revision': del first['revision']
    elif damage == 'simulated_revision': first['revision'] = 'local-only'
    elif damage == 'outside': first['destination_path'] = '/production/0.webp'
    elif damage == 'traversal': first['destination_path'] = '/RecorderNonproduction/offline/../0.webp'
    elif damage == 'seven': files.pop()
    elif damage == 'nine': files.append(copy.deepcopy(first))
    with pytest.raises(Invalid): inspect(prepared, approval(prepared))


@pytest.mark.parametrize('field', ['profile','extension_instance','conversation_url','mapping_url'])
def test_changed_approved_identity_refused(prepared, field):
    reviewed = approval(prepared)
    prepared['browser'][field] += '-changed'
    with pytest.raises(Invalid, match='approval'): inspect(prepared, reviewed)


def test_stale_prompt_and_missing_approval(prepared):
    from pathlib import Path
    with pytest.raises(Invalid): inspect(prepared, {})
    reviewed = approval(prepared)
    Path(prepared['prompt']['path']).write_text('stale clipboard', encoding='utf-8')
    with pytest.raises(Invalid): inspect(prepared, reviewed)


def test_cli_missing_environment_is_structured_refusal(tmp_path):
    manifest = tmp_path/'missing.json'; manifest.write_text('{}')
    result = subprocess.run([sys.executable, '-m', 'desktop_recorder.readiness',
        '--manifest', str(manifest), '--approval', str(manifest)], capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stdout)['may_send'] is False


@pytest.mark.parametrize('content', ['', '{"store":1,"store":2}', 'x'*(2*1024*1024+1)], ids=['empty','duplicate','oversized'])
def test_ambiguous_or_oversized_document_refused(tmp_path, content):
    path=tmp_path/'manifest.json'; path.write_text(content)
    with pytest.raises(Invalid): load_document(path)


def test_encoded_destination_escape_refused(prepared):
    prepared['files'][0]['destination_path']='/RecorderNonproduction/offline/%2e%2e%2fproduction.webp'
    with pytest.raises(Invalid): inspect(prepared,approval(prepared))
