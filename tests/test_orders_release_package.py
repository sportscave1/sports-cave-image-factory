from io import BytesIO
from zipfile import ZipFile
import json,re
import requests

def test_downloaded_release_contains_every_declared_runtime_script(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Packaging must be offline')))
    from upload_companion_page import extension_package
    with ZipFile(BytesIO(extension_package())) as package:
        manifest=json.loads(package.read('manifest.json'))
        assert manifest['version']=='1.7.55'
        names=set(package.namelist())
        for content in manifest['content_scripts']:
            assert set(content['js'])<=names
        worker=package.read(manifest['background']['service_worker']).decode()
        for args in re.findall(r'importScripts\(([^)]+)\)',worker):
            assert set(re.findall(r"['\"]([^'\"]+)['\"]",args))<=names
        assert {'orders-progress.js','prodigi-wait.js'}<=names
        assert {'inbox-queue.js','inbox-page.js'}<=names
        assert {'prodigi-signin.js','prodigi-signin-page.js'}<=names
