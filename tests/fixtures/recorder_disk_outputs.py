"""Disk-backed boundary for recorder Save all tests; never contacts Dropbox."""
from copy import deepcopy
from pathlib import Path, PurePosixPath
import shutil
import os
import uuid

import auto_editions as ae
from tests.fixtures.product_upload_outputs_provider import Outputs


class DiskOutputs(Outputs):
    def __init__(self, directory):
        super().__init__()
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.files[self.base + '/Hockey'] = dict(
            id='id:recorder-hockey', name='Hockey', path_display=self.base + '/Hockey',
            **{'.tag': 'folder'})

    def local_path(self, path):
        if not path.startswith(self.base + '/'):
            raise ValueError('Outside isolated output collection')
        parts = PurePosixPath(path[len(self.base) + 1:]).parts
        if not parts or any(p in ('', '.', '..') or ':' in p or '\\' in p for p in parts):
            raise ValueError('Invalid isolated output path')
        local = self.directory.joinpath(*parts).resolve()
        if not local.is_relative_to(self.directory):
            raise ValueError('Outside isolated output directory')
        # The worktree plus descriptive product filenames can exceed MAX_PATH.
        # Scope validation above uses the ordinary resolved path first.
        if os.name == 'nt' and not str(local).startswith('\\\\?\\'):
            return Path('\\\\?\\' + str(local))
        return local

    def get_metadata_if_exists(self, token, path):
        value = self.files.get(path)
        if value is None:
            value = next((v for v in self.files.values() if v['id'] == path), None)
        if value is None:
            return None
        value = deepcopy(value)
        if value['.tag'] == 'file':
            local = self.local_path(value['path_display'])
            if not local.is_file():
                return None
            value.update(size=local.stat().st_size, content_hash=ae.file_hash(local, dropbox=True))
        return value

    def create_folder(self, token, parent, name, conflict='cancel'):
        path = self.join_upload_path(parent, name)
        local = self.local_path(path)
        if local.exists() or path in self.files:
            return None
        local.mkdir(parents=True)
        return super().create_folder(token, parent, name, conflict)

    def upload_batch(self, token, target, items, **kwargs):
        if kwargs.get('conflict') != 'cancel':
            raise ValueError('Test saver never overwrites files')
        successes, failures = [], []
        for item in items:
            name = item['relative_path']
            path = self.join_upload_path(target, name)
            local = self.local_path(path)
            self.calls.append(('upload', path))
            if self.fail_once in (name, '*'):
                self.fail_once = None
                failures.append(dict(relative_path=name, error='Controlled local failure'))
                continue
            local.parent.mkdir(parents=True, exist_ok=True)
            try:
                with local.open('xb') as out, Path(item['local_path']).open('rb') as source:
                    shutil.copyfileobj(source, out)
            except FileExistsError:
                failures.append(dict(relative_path=name, error='Existing output not overwritten'))
                continue
            parent = path.rsplit('/', 1)[0]
            self.files.setdefault(parent, dict(id='id:' + uuid.uuid4().hex,
                name=parent.rsplit('/', 1)[-1], path_display=parent, **{'.tag': 'folder'}))
            metadata = dict(id='id:' + uuid.uuid4().hex, name=local.name,
                path_display=path, rev='local-only', size=local.stat().st_size,
                content_hash=ae.file_hash(local, dropbox=True), **{'.tag': 'file'})
            self.files[path] = metadata
            kwargs['progress_callback'](1, 1, name, metadata['size'], metadata['size'])
            successes.append(dict(relative_path=name, metadata=deepcopy(metadata)))
        return dict(successes=successes, failures=failures)
