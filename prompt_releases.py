"""Durable prompt drafts in Git, narrow atomic publication, verified Render status.

No application import, shell execution, service creation, or forced Git updates.
"""
import base64
from datetime import datetime, timezone
import json
import os
from urllib.parse import quote
import uuid

import requests

from prompt_library import ROOT, Prompt, catalog, digest, replace_source, validate_text
from prompt_bundle import changes, is_bundle

REPO = 'sportscave1/sports-cave-image-factory'
SERVICE = 'srv-d8kl4on7f7vs73dvavv0'
DRAFT_BRANCH = 'codex/prompt-library-drafts'
MANIFEST = 'prompts/releases.json'


class ReleaseError(RuntimeError):
    pass


class GitStore:
    def __init__(self, token=None, render_token=None, session=None):
        self.token = token if token is not None else os.getenv('PROMPTS_GITHUB_TOKEN', '')
        self.render_token = render_token if render_token is not None else os.getenv('RENDER_API_KEY', '')
        self.session = session or requests.Session()

    def request(self, method, path, body=None, missing=False, render=False):
        token = self.render_token if render else self.token
        if not token:
            raise ReleaseError('Release connection is not configured.' if render else 'Draft storage is not connected.')
        base = 'https://api.render.com/v1/' if render else f'https://api.github.com/repos/{REPO}/'
        headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}
        try:
            response = self.session.request(method, base + path, headers=headers, json=body, timeout=25)
        except requests.RequestException:
            raise ReleaseError('Connection interrupted. Refresh status before retrying; the request may have completed.') from None
        if missing and response.status_code == 404:
            return None
        if not response.ok:
            # Never surface provider bodies, URLs with credentials, or request headers.
            provider = 'Render status connection' if render else 'GitHub connection'
            if response.status_code in (401, 403):
                raise ReleaseError(f'{provider} rejected authentication (HTTP {response.status_code}). Check its server credential and permissions; saved drafts are preserved.')
            raise ReleaseError(f'{provider} returned HTTP {response.status_code}. Refresh before retrying; concurrent edits are preserved.')
        return response.json()

    def head(self, branch='main', missing=False):
        result = self.request('GET', 'git/ref/heads/' + branch, missing=missing)
        return result['object']['sha'] if result else None

    def read(self, path, ref, missing=False):
        row = self.request('GET', 'contents/' + quote(path, safe='/') + '?ref=' + quote(ref, safe=''), missing=missing)
        if row is None:
            return None, None
        return base64.b64decode(row['content']).decode('utf-8'), row['sha']

    def history(self, prompt):
        if not self.head(DRAFT_BRANCH, missing=True):
            return {'versions': []}, None
        text, sha = self.read(f'prompt-drafts/{prompt.key}.json', DRAFT_BRANCH, missing=True)
        return (json.loads(text) if text else {'versions': []}), sha

    def write_history(self, prompt, data, expected_sha):
        if not self.head(DRAFT_BRANCH, missing=True):
            self.request('POST', 'git/refs', {'ref': 'refs/heads/' + DRAFT_BRANCH, 'sha': self.head()})
        body = {'message': f'Save prompt history: {prompt.title} [skip render]',
                'branch': DRAFT_BRANCH,
                'content': base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode()).decode()}
        if expected_sha:
            body['sha'] = expected_sha
        result = self.request('PUT', f'contents/prompt-drafts/{prompt.key}.json', body)
        return result['content']['sha']

    def save(self, prompt, text, note, actor, history, expected_sha):
        sections = changes(prompt, text, catalog()) if is_bundle(prompt) else None
        if sections is not None and not sections:
            raise ValueError('No section changes to save.')
        if sections is None:
            validate_text(prompt.text, text)
        rows = history['versions']
        if rows and rows[-1]['text'] == text:
            raise ValueError('This text is already saved. Select its existing version.')
        if not rows:
            rows = [{'id': uuid.uuid4().hex, 'version': '1.0', 'text': prompt.text,
                     'base_hash': digest(prompt.text), 'baseline': True, 'note': 'Original deployed source',
                     'author': actor, 'created_at': datetime.now(timezone.utc).isoformat()}]
        item = {'id': uuid.uuid4().hex, 'version': f'1.{len(rows)}', 'text': text,
                'base_hash': digest(prompt.text), 'note': str(note)[:1000], 'author': actor,
                'created_at': datetime.now(timezone.utc).isoformat()}
        if sections is not None:
            item['sections'] = sections
        updated = {**history, 'path': prompt.path, 'symbol': prompt.symbol, 'versions': [*rows, item]}
        self.write_history(prompt, updated, expected_sha)
        return item

    def activate(self, prompt, version_id, history, expected_sha):
        item = next(v for v in history['versions'] if v['id'] == version_id)
        if item.get('baseline'):
            raise ReleaseError('Save the original as a new draft before publishing it.')
        if item.get('commit'):
            raise ReleaseError('This version already has a release attempt. Refresh its status before creating another draft.')
        # Publication uses GitHub only. The canonical Render service watches main;
        # its optional monitoring credential must not block an authorized Git push.
        parent = self.head()
        sections = item.get('sections') if is_bundle(prompt) else None
        if is_bundle(prompt) and not sections:
            raise ReleaseError('Save a new entire-prompt draft before publishing.')
        entries = sections or [{'path': prompt.path, 'symbol': prompt.symbol, 'key': prompt.key,
                                'base_hash': item['base_hash'], 'text': item['text']}]
        sources = {}
        for entry in entries:
            path = entry['path']
            if path not in sources:
                sources[path], _ = self.read(path, parent)
            section = Prompt(path, entry['symbol'], prompt.category, '')
            sources[path] = replace_source(section, sources[path], entry['base_hash'], entry['text'])
        manifest_text, _ = self.read(MANIFEST, parent, missing=True)
        manifest = json.loads(manifest_text) if manifest_text else {}
        manifest[prompt.key] = {'version': item['version'], 'id': item['id'], 'hash': digest(item['text']),
                                'path': prompt.path, 'symbol': prompt.symbol}
        for entry in entries:
            manifest[entry['key']] = {'version': item['version'], 'id': item['id'],
                'hash': digest(entry['text']), 'path': entry['path'], 'symbol': entry['symbol']}
        parent_commit = self.request('GET', 'git/commits/' + parent)
        tree = self.request('POST', 'git/trees', {'base_tree': parent_commit['tree']['sha'], 'tree': [
            *[{'path': path, 'mode': '100644', 'type': 'blob', 'content': text}
              for path, text in sources.items()],
            {'path': MANIFEST, 'mode': '100644', 'type': 'blob', 'content': json.dumps(manifest, indent=2)},
        ]})
        commit = self.request('POST', 'git/commits', {'message': f'Activate prompt {prompt.title} v{item["version"]}',
                        'tree': tree['sha'], 'parents': [parent]})['sha']
        # Persist the exact candidate BEFORE main can change. Lost responses are recoverable.
        updated = {**history, 'versions': [{**v, 'commit': commit} if v['id'] == version_id else v
                                           for v in history['versions']]}
        self.write_history(prompt, updated, expected_sha)
        self.request('PATCH', 'git/refs/heads/main', {'sha': commit, 'force': False})
        return commit

    def status(self, prompt, item):
        commit = item.get('commit')
        if not commit:
            return 'Draft'
        # A later deployment can include this prompt unchanged. Inspect its immutable manifest.
        # A running deployment can prove its own prompt version without Render API access.
        try:
            local = json.loads((ROOT / MANIFEST).read_text(encoding='utf-8'))
            current = {p.key: digest(p.text) for p in catalog()}
            active = local.get(prompt.key, {})
            entries = item.get('sections') or [{'key': prompt.key, 'text': item['text']}]
            if (active.get('id') == item['id'] and active.get('hash') == digest(item['text'])
                    and all(current.get(e['key']) == digest(e['text']) for e in entries)):
                return 'Live'
        except (OSError, ValueError):
            pass
        try:
            rows = self.request('GET', f'services/{SERVICE}/deploys?limit=20', render=True) if self.render_token else []
        except ReleaseError:
            compare = self.request('GET', 'compare/' + commit + '...main')
            if compare.get('status') in {'ahead', 'identical'}:
                return 'Published to GitHub - deployment status unavailable; reload after rollout'
            return 'Not published - Git changed; save a new draft'
        exact = None
        for row in rows:
            deploy = row.get('deploy', row)
            sha = deploy.get('commit', {}).get('id')
            if sha == commit:
                exact = deploy.get('status')
            if deploy.get('status') == 'live' and sha:
                text, _ = self.read(MANIFEST, sha, missing=True)
                manifest = json.loads(text) if text else {}
                active = manifest.get(prompt.key, {})
                sections_match = all(manifest.get(entry['key'], {}).get('hash') == digest(entry['text'])
                                     for entry in item.get('sections', []))
                if sections_match and active.get('id') == item['id'] and active.get('hash') == digest(item['text']):
                    return 'Live'
        if exact in {'build_failed', 'update_failed', 'pre_deploy_failed', 'canceled'}:
            return 'Deployment failed'
        if exact == 'deactivated':
            return 'Previous release'
        if exact in {'build_in_progress', 'pre_deploy_in_progress', 'update_in_progress', 'created'}:
            return 'Deploying'
        compare = self.request('GET', 'compare/' + commit + '...main')
        if compare.get('status') in {'ahead', 'identical'}:
            return 'Awaiting deployment' if exact != 'live' else 'Previous release'
        return 'Not published — Git changed; save a new draft'
