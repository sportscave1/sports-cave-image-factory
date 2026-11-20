"""Archived history remains readable through GitHub's large-file response."""
import base64
import json
from pathlib import Path
from unittest.mock import Mock
from prompt_library import digest
from prompt_releases import GitStore


def test_large_history_uses_exact_blob_and_preserves_original_baseline():
    data = Path('prompts/release_history/ebffbedac545beb011dc654c.json').read_bytes()
    assert len(data) > 1024 * 1024
    store = GitStore()
    store.request = Mock(side_effect=[{'sha':'immutable-blob', 'encoding':'none', 'content':''},
        {'encoding':'base64', 'content':base64.b64encode(data).decode()}])
    text, sha = store.read('prompt-drafts/ebffbedac545beb011dc654c.json', 'saved-history')
    assert sha == 'immutable-blob'
    assert store.request.call_args.args == ('GET', 'git/blobs/immutable-blob')
    versions = json.loads(text)['versions']
    assert len(versions) == 16
    assert digest(versions[0]['text']) == '941229c51de869378dfacaeaf85b64fc7e3a916fa5bfff5840c96d9490077663'
    assert versions[0]['baseline'] is True
    assert versions[-1]['id'] == 'ads-baseline-2-0-two-line-20261120'


def test_small_file_keeps_existing_single_request():
    store = GitStore()
    store.request = Mock(return_value={'sha':'small', 'encoding':'base64', 'content':base64.b64encode(b'Original').decode()})
    assert store.read('prompt.txt', 'saved') == ('Original', 'small')
    store.request.assert_called_once()
