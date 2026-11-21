"""Publish one allowlisted website settings file through the existing Git connection."""
import base64
import json
from uuid import uuid4

from marketplace import SITE_PATH, site_config, now
from prompt_releases import GitStore, ReleaseError


def publish_website(draft, client=None):
    client = client or GitStore()
    parent = client.head()
    source, sha = client.read(SITE_PATH, parent)
    current = json.loads(source)
    target = site_config(draft['config'])
    # Reconcile an interrupted request before considering a second publish.
    if draft.get('release_id') and current.get('release_id') == draft['release_id']:
        if {k: v for k, v in current.items() if k != 'release_id'} != {k: v for k, v in target.items() if k != 'release_id'}:
            raise ReleaseError('The published release does not match this draft. Reload before publishing.')
        return {'commit': parent, 'release_id': current['release_id'], 'published_at': now()}
    if current != draft['base']:
        raise ReleaseError('The live website changed. Reload its settings before publishing this draft.')
    if {k: v for k, v in target.items() if k != 'release_id'} == {k: v for k, v in current.items() if k != 'release_id'}:
        raise ValueError('Save a website change before publishing.')
    target = {**target, 'release_id': draft.get('release_id') or str(uuid4())}
    content = json.dumps(target, ensure_ascii=False, indent=2) + '\n'
    result = client.request('PUT', 'contents/' + SITE_PATH, {
        'branch': 'main', 'sha': sha, 'message': 'Publish Sports Cave Marketplace website',
        'content': base64.b64encode(content.encode()).decode('ascii')})
    return {'commit': result['commit']['sha'], 'release_id': target['release_id'], 'published_at': now()}
