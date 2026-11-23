"""In-memory Dropbox transport exercising the real marketplace storage contract."""
from copy import deepcopy
import json

from marketplace_dropbox import MarketplaceDropboxStorage, ROOT


class FakeResponse:
    def __init__(self, data, metadata, start=0, end=None):
        end = len(data) - 1 if end is None else end
        self.data = data[start:end + 1]
        self.status_code = 206
        self.headers = {'Dropbox-API-Result': json.dumps(metadata),
                        'Content-Range': f'bytes {start}-{end}/{len(data)}'}
        self.closed = False

    def iter_content(self, chunk_size):
        for index in range(0, len(self.data), chunk_size):
            yield self.data[index:index + chunk_size]

    def close(self):
        self.closed = True


class MemoryDropbox:
    def __init__(self):
        self.folders, self.objects, self.paths, self.calls = [], {}, {}, []
        self.fail_upload = ''

    def files_create_folder_v2(self, path, **kwargs):
        self.folders.append(path)

    def files_upload(self, data, path, **kwargs):
        if self.fail_upload and path.endswith(self.fail_upload):
            raise OSError('synthetic storage failure')
        if path in self.paths:
            raise OSError('synthetic path conflict')
        number = len(self.objects) + 1
        metadata = {'id': 'id:synthetic-' + str(number), 'rev': f'{number:016x}',
                    'size': len(data), 'path_display': path}
        self.objects[metadata['id']] = (bytes(data), metadata)
        self.paths[path] = metadata['id']
        return deepcopy(metadata)

    def get(self, url, **kwargs):
        assert url == 'https://content.dropboxapi.com/2/files/download'
        self.calls.append(kwargs)
        headers = kwargs['headers']
        target = json.loads(headers['Dropbox-API-Arg'])
        assert set(target) == {'path'} and target['path'].startswith('rev:')
        found = next((value for value in self.objects.values() if 'rev:' + value[1]['rev'] == target['path']), None)
        if found is None:
            raise KeyError('Missing synthetic revision')
        data, metadata = found
        first, last = map(int, headers['Range'].removeprefix('bytes=').split('-'))
        response = FakeResponse(data, metadata, first, last)
        self.last_response = response
        return response


class MemorySource(MarketplaceDropboxStorage):
    def __init__(self):
        self.backend = MemoryDropbox()
        super().__init__(context={'root': ROOT, 'client': self.backend,
            'namespace': '123', 'token': 'synthetic-not-a-real-token'}, http=self.backend)
