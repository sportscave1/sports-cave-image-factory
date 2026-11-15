"""Offline follow-up binding and durable at-most-once journal.

This module never sends input, calls a provider, or authorizes a store. A future
native adapter must independently establish a nonproduction destination, usable
files and fresh trusted observations before using it. Caller-supplied metadata
is NOT proof of that authority. No native dispatch currently uses this module.
Acknowledgement is distinct from business success and Mapping completion.
"""
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .contract import Invalid


FIELDS = frozenset({
    'browser', 'profile', 'extension_instance', 'conversation_url',
    'source_url', 'mapping_url', 'store_id', 'product_id', 'save_token',
    'prompt_sha256', 'files_sha256', 'recording_revision', 'coverage',
})
DIGEST = re.compile(r'[a-f0-9]{64}')
CHAT = re.compile(r'https://chatgpt\.com/g/g-p-6a387a17627081918e1700ec2783a12b(?:-sc-mockups-uploads)?/c/[a-f0-9-]{36}')


def canonical(binding):
    if not isinstance(binding, dict) or set(binding) != FIELDS:
        raise Invalid('Complete exact follow-up binding required.')
    if any(not isinstance(v, str) or not v or len(v) > 2048 for v in binding.values()):
        raise Invalid('Invalid follow-up binding value.')
    if binding['coverage'] not in ('simulated', 'isolated-nonproduction'):
        raise Invalid('Production and unverified coverage cannot be admitted.')
    if binding['browser'] not in ('chrome', 'edge'):
        raise Invalid('Unsupported follow-up browser.')
    if not CHAT.fullmatch(binding['conversation_url']):
        raise Invalid('Exact SC Mockups/Uploads conversation required.')
    for key in ('prompt_sha256', 'files_sha256', 'recording_revision'):
        if not DIGEST.fullmatch(binding[key]):
            raise Invalid('Invalid follow-up digest.')
    return json.dumps(binding, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def verify_prepared(expected, observed, full_prompt):
    """Compare trusted observations; does not manufacture them from file presence."""
    if canonical(expected) != canonical(observed):
        raise Invalid('Follow-up browser, destination, files or identity changed.')
    if not isinstance(full_prompt, str) or not 1 <= len(full_prompt) <= 1048576:
        raise Invalid('Complete prompt is unavailable.')
    digest = hashlib.sha256(full_prompt.replace('\r\n', '\n').encode('utf-8')).hexdigest()
    if digest != expected['prompt_sha256']:
        raise Invalid('Full prompt differs from saved prompt; nothing may be sent.')


def logical_key(binding):
    canonical(binding)
    # Neither a new run ID, browser/profile, conversation nor revised prompt can
    # authorize repeating the same product/save. Any change conflicts below.
    return hashlib.sha256(json.dumps([binding[k] for k in
        ('store_id', 'product_id', 'save_token')], separators=(',', ':')).encode()).hexdigest()


class FollowupJournal:
    def __init__(self, path):
        self.path = Path(path)
        db = self._connect()
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS followups '
                           '(id TEXT PRIMARY KEY, binding TEXT NOT NULL, acknowledgement TEXT)')
        finally:
            db.close()

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def reserve(self, binding):
        """Persist before any effect. No automatic release, reset or resend API."""
        encoded, key = canonical(binding), logical_key(binding)
        db = self._connect()
        try:
            with db:
                db.execute('INSERT INTO followups VALUES (?,?,NULL)', (key, encoded))
        except sqlite3.IntegrityError as error:
            raise Invalid('Follow-up already attempted; recover acknowledgement, never resend.') from error
        finally:
            db.close()

    @staticmethod
    def _acknowledgement(binding, observation):
        canonical(binding)
        required = {'conversation_url', 'prompt_sha256', 'profile', 'extension_instance',
                    'message_id', 'matching_user_messages', 'coverage'}
        if not isinstance(observation, dict) or set(observation) != required:
            raise Invalid('Complete acknowledgement evidence required.')
        for key in required - {'message_id', 'matching_user_messages'}:
            if observation[key] != binding[key]:
                raise Invalid('Acknowledgement identity mismatch.')
        if (type(observation['matching_user_messages']) is not int
                or observation['matching_user_messages'] != 1
                or not isinstance(observation['message_id'], str)
                or not observation['message_id'] or len(observation['message_id']) > 256):
            raise Invalid('One uniquely identified matching user message required.')
        return json.dumps(observation, sort_keys=True, separators=(',', ':'))

    def acknowledge(self, binding, observation):
        """Persist one matching observed user message. Never infer business success."""
        encoded, key = canonical(binding), logical_key(binding)
        ack = self._acknowledgement(binding, observation)
        db = self._connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT binding,acknowledgement FROM followups WHERE id=?', (key,)).fetchone()
                if row is None or row[0] != encoded:
                    raise Invalid('No matching durable attempt; recovery cannot infer submission.')
                if row[1] is not None and row[1] != ack:
                    raise Invalid('Conflicting acknowledgement; inspect without resending.')
                if row[1] is None:
                    db.execute('UPDATE followups SET acknowledgement=? WHERE id=?', (ack, key))
        finally:
            db.close()

    def recover(self, binding):
        """Read-only query; unknown outcome raises and never changes the attempt."""
        encoded, key = canonical(binding), logical_key(binding)
        db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            row = db.execute('SELECT binding,acknowledgement FROM followups WHERE id=?', (key,)).fetchone()
        finally:
            db.close()
        if row is None or row[0] != encoded or row[1] is None:
            raise Invalid('Acknowledgement unavailable or mismatched; do not resend.')
        try:
            observation = json.loads(row[1])
            self._acknowledgement(binding, observation)
            return observation
        except (ValueError, TypeError) as error:
            raise Invalid('Corrupt acknowledgement; do not resend.') from error
