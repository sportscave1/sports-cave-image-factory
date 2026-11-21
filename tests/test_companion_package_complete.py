import io
import json
from zipfile import ZipFile

from upload_companion_page import extension_package


def test_download_contains_every_manifest_script():
    with ZipFile(io.BytesIO(extension_package())) as bundle:
        manifest=json.loads(bundle.read('manifest.json'))
        required={manifest['background']['service_worker']}
        for script in manifest['content_scripts']:
            required.update(script['js'])
        assert required.issubset(bundle.namelist())
        assert {'queue-wake.js','ad-repair.js'}.issubset(bundle.namelist())
