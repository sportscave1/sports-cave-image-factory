"""Versioned receipt-host preparation and reversible per-user registration.

No process launch, extension installation, data migration or machine-wide keys.
Call activate only after the owning helper has stopped and release is authorized.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
from uuid import uuid4
from task_recorder.store import atomic
from .download_preflight import HOST, inspect_manifest

KEY = 'Software\\Microsoft\\Edge\\NativeMessagingHosts\\' + HOST

class Registry:
    def get(self, view):
        import winreg as w
        try:
            with w.OpenKey(w.HKEY_CURRENT_USER,KEY,0,w.KEY_READ | self.flag(view)) as key:
                value, kind=w.QueryValueEx(key,'')
                return {'value':value,'type':kind}
        except FileNotFoundError:return None

    @staticmethod
    def flag(view):
        import winreg as w
        return {'32':w.KEY_WOW64_32KEY,'64':w.KEY_WOW64_64KEY}[view]

    def put(self, view, record):
        import winreg as w
        if record is None:
            # Remove only our default value, retaining the key and other values.
            try:
                with w.OpenKey(w.HKEY_CURRENT_USER,KEY,0,w.KEY_SET_VALUE | self.flag(view)) as key:w.DeleteValue(key,'')
            except FileNotFoundError:pass
        else:
            with w.CreateKeyEx(w.HKEY_CURRENT_USER,KEY,0,w.KEY_SET_VALUE | self.flag(view)) as key:
                w.SetValueEx(key,'',0,record['type'],record['value'])

def prepare(executable, install, extension_id):
    if not re.fullmatch('[a-p]{32}',extension_id):raise ValueError('Exact installed Edge extension ID required.')
    executable=Path(executable).resolve(strict=True)
    from task_recorder.release import windows_x64
    content=executable.read_bytes(); windows_x64(content)
    digest=hashlib.sha256(content).hexdigest()
    # Immutable binary + mutable session config in a version-specific bridge dir.
    folder=Path(install).resolve()/'download-hosts'/(digest[:20]+'-'+extension_id)
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/'DownloadReceiptHost.exe'
    if target.exists() and target.read_bytes()!=content:raise ValueError('Existing versioned host differs; preserve it.')
    if not target.exists():shutil.copy2(executable,target)
    manifest={'name':HOST,'description':'Sports Cave Task Recorder download receipts','path':str(target),'type':'stdio',
              'allowed_origins':['chrome-extension://'+extension_id+'/']}
    path=folder/'host.json'
    if path.exists() and json.loads(path.read_text())!=manifest:raise ValueError('Existing host manifest differs; preserve it.')
    if not path.exists():atomic(path,manifest)
    assert inspect_manifest(path,extension_id)['ready']
    return folder

def activate(folder, journal_directory, registry=None, journal=None):
    registry=registry or Registry(); folder=Path(folder).resolve(strict=True)
    manifest=json.loads((folder/'host.json').read_text())
    origins=manifest.get('allowed_origins',[])
    if len(origins)!=1:raise ValueError('Exactly one recorder extension is required.')
    extension=origins[0].removeprefix('chrome-extension://').removesuffix('/')
    if not re.fullmatch('[a-p]{32}',extension) or not inspect_manifest(folder/'host.json',extension)['ready']:
        raise ValueError('Host manifest failed validation.')
    journal_directory=Path(journal_directory);journal_directory.mkdir(parents=True,exist_ok=True)
    journal=Path(journal) if journal else journal_directory/('registration-'+str(uuid4())+'.json')
    if journal.exists():raise ValueError('Registration journal already exists; inspect before retrying.')
    record={'key':KEY,'expected':{'value':str(folder/'host.json'),'type':1},
            'before':{view:registry.get(view) for view in ('32','64')},'state':'prepared'}
    atomic(journal,record)  # Durable before any registry mutation.
    try:
        for view in ('32','64'):registry.put(view,record['expected'])
        if any(registry.get(view)!=record['expected'] for view in ('32','64')):raise RuntimeError('Host registration readback differs.')
        record['state']='registered';atomic(journal,record)
    except Exception:
        restore(journal,registry)
        raise
    return journal

def restore(journal, registry=None):
    registry=registry or Registry(); record=json.loads(Path(journal).read_text())
    if record['key']!=KEY:raise ValueError('Unexpected host registration journal.')
    # Preflight every view before restoring any: never overwrite another owner's change.
    for view in ('32','64'):
        if registry.get(view) not in (record['expected'],record['before'][view]):
            raise RuntimeError('Registration changed independently; preserve and inspect before rollback.')
    for view in ('32','64'):
        if registry.get(view)==record['expected']:registry.put(view,record['before'][view])
    record['state']='restored';atomic(Path(journal),record)

def install_bridge(executable, install, data, extension_id, transaction, registry=None):
    """Caller owns the idle-helper boundary. Leaves old code/data untouched."""
    data=Path(data);data.mkdir(parents=True,exist_ok=True)
    config=data/'download-bridge.json';transaction=Path(transaction)
    if transaction.exists():raise ValueError('Bridge transaction already exists; inspect before retrying.')
    folder=prepare(executable,install,extension_id)
    expected={'folder':str(folder),'extension_id':extension_id,
              'sha256':hashlib.sha256((folder/'DownloadReceiptHost.exe').read_bytes()).hexdigest()}
    before=json.loads(config.read_text()) if config.exists() else None
    journal=transaction.parent/'registration-journals'/('registration-'+str(uuid4())+'.json')
    record={'before':before,'expected':expected,'registration':str(journal),'state':'prepared'}
    atomic(transaction,record)
    try:
        activate(folder,journal.parent,registry,journal=journal)
        atomic(config,expected)
        record['state']='configured';atomic(transaction,record)
    except Exception:
        restore_bridge(transaction,data,registry)
        raise
    return folder

def restore_bridge(transaction, data, registry=None):
    transaction=Path(transaction)
    if not transaction.exists():return  # Previous releases had no bridge transaction.
    record=json.loads(transaction.read_text()); config=Path(data)/'download-bridge.json'
    current=json.loads(config.read_text()) if config.exists() else None
    if current not in (record['before'],record['expected']):
        raise RuntimeError('Bridge configuration changed independently; preserve before rollback.')
    if record['registration'] and Path(record['registration']).exists():restore(record['registration'],registry)
    if current==record['expected']:
        if record['before'] is None:config.unlink()
        else:atomic(config,record['before'])
    record['state']='restored';atomic(transaction,record)

def configure_installed(data):
    """Run under the helper instance lock; no registration mutation at startup."""
    path=Path(data)/'download-bridge.json'
    if not path.exists():return {}
    config=json.loads(path.read_text())
    folder=Path(config['folder']).resolve(strict=True)
    executable=folder/'DownloadReceiptHost.exe'
    if hashlib.sha256(executable.read_bytes()).hexdigest()!=config['sha256']:
        raise ValueError('Download host differs from installed configuration; repair the reviewed package.')
    if not inspect_manifest(folder/'host.json',config['extension_id'])['ready']:
        raise ValueError('Download host manifest is incompatible with the configured Edge extension.')
    from .download_bridge import configure
    return configure(data,folder)
