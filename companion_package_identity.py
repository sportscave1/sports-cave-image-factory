"""Versioned preparation/transport identity; contains no paths or capabilities."""
import hashlib
import json
from pathlib import Path
import auto_editions as ae

PROTOCOL=1
CHUNK=8*1024*1024
BLOCK=4*1024*1024


def generation():
    root=Path(__file__).parent
    names=('data/auto_editions_template.json','scripts/photoshop/prepare_auto_editions.jsx',
           'scripts/photoshop/inspect_psd_editions.jsx','auto_editions_onboarding.py',
           'scripts/prepare_auto_editions.py','auto_editions.py','auto_editions_colour.py')
    return ae.fingerprint(dict(contract=1,files={name:hashlib.sha256((root/name).read_text(encoding='utf-8-sig').replace('\r\n','\n').encode()).hexdigest() for name in names}))


def describe(path):
    import zipfile
    path=Path(path)
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo('manifest.json').file_size>1024*1024:raise ValueError('Bounded manifest required.')
        manifest=ae.validate_manifest(json.loads(archive.read('manifest.json')))
    chunks=[];digest=hashlib.sha256()
    with path.open('rb') as source:
        while data:=source.read(CHUNK):
            digest.update(data);chunks.append(hashlib.sha256(data).hexdigest())
    return dict(protocol=PROTOCOL,bytes=path.stat().st_size,sha256=digest.hexdigest(),
                preparation_hash=ae.fingerprint(manifest),generation=generation(),manifest=manifest,chunks=chunks)


def validate(value,context):
    import re
    from auto_editions_package import MAX_PACKAGE_BYTES
    fields={'protocol','bytes','sha256','preparation_hash','generation','manifest','chunks'}
    if not isinstance(value,dict) or set(value)!=fields or value['protocol']!=PROTOCOL:
        raise ValueError('Unsupported resumable package protocol.')
    if type(value['bytes']) is not int or not 0<value['bytes']<=MAX_PACKAGE_BYTES:raise ValueError('Invalid package size.')
    if not isinstance(value['chunks'],list) or len(value['chunks'])!=(value['bytes']+CHUNK-1)//CHUNK:raise ValueError('Invalid chunk inventory.')
    if any(not re.fullmatch('[a-f0-9]{64}',str(h)) for h in [value['sha256'],value['preparation_hash'],value['generation']]+value['chunks']):
        raise ValueError('Exact package fingerprints required.')
    manifest=ae.validate_manifest(value['manifest'])
    if (ae.fingerprint(manifest)!=value['preparation_hash'] or manifest['source']!=context['source']
        or manifest['edition_total']!=context['total'] or value['generation']!=generation()
        or context.get('reset_id') and manifest.get('reset_request_id')!=context['reset_id']):
        raise ValueError('Source, edition run, template or output fingerprint changed.')
    if len(json.dumps(value))>1024*1024:raise ValueError('Bounded package descriptor required.')
    return value
