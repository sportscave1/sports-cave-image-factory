$ErrorActionPreference = 'Stop'
# Original-owner reviewed handoff; development export, not an installed release.
$revision = '4e1bc88b6505db1a2b2e92e71902a6df65594c25'
$destination = Join-Path $PSScriptRoot '.local-data\reviewed-helper'
$python = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe'
$script = @'
import hashlib,json,subprocess,sys
from pathlib import Path
revision,destination,repository=sys.argv[1],Path(sys.argv[2]),sys.argv[3]
git=['git','-C',repository]
names=subprocess.check_output(git+['ls-tree','-r','--name-only',revision,'task_recorder'],text=True).splitlines()
if not names:raise RuntimeError('Reviewed commit has no helper package')
manifest={'revision':revision,'files':[]}
for name in names:
    relative=Path(name)
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe dependency path')
    data=subprocess.check_output(git+['show',revision+':'+name])
    path=destination/relative
    if path.exists() and path.read_bytes()!=data:raise RuntimeError('Modified dependency preserved: '+name)
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():path.write_bytes(data)
    manifest['files'].append({'path':name,'sha256':hashlib.sha256(data).hexdigest()})
(destination/'dependency-manifest.json').write_text(json.dumps(manifest,indent=2))
print(str(destination))
'@
$script | & $python -B - $revision $destination (Split-Path $PSScriptRoot -Parent)
if ($LASTEXITCODE -ne 0) { throw 'Reviewed dependency preparation failed' }
