"""Freeze an explicitly reconciled checkout. Never commits, pushes or edits application sources in the caller's workspace."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout',type=Path,required=True)
    args=parser.parse_args();checkout=args.checkout.resolve()
    def git(*args):return subprocess.check_output(['git',*args],cwd=checkout)
    base=git('rev-parse','HEAD').decode().strip()
    contracts=json.loads((checkout/'tests/fixtures/table_v3_contracts.json').read_text())
    if base!=contracts['base_revision']:raise RuntimeError('Checkout and audited base differ')
    bundle=ROOT/'docs/table-v3-release'
    previous=json.loads((bundle/'manifest.json').read_text())
    files=set(previous['files'])|{'scripts/package_table_design_v3_release.py',
        'scripts/verify_table_design_v3_release.py','tests/fixtures/table_v3_known_baseline_failures.json',
        'docs/TABLE_DESIGN_V3_RELEASE_REPAIR.md','docs/table-v3-evidence/release-validation.json'}
    shutil.copy2(Path(__file__),checkout/'scripts/package_table_design_v3_release.py')
    assets={item['path'] for item in previous['assets']}
    assets.update(p.relative_to(checkout).as_posix() for p in (checkout/'docs/table-v3-evidence').glob('*.png'))
    files.update(assets)
    tracked=set(git('ls-tree','-r','--name-only','HEAD').decode().splitlines())
    patch=[];outputs=[];asset_records=[]
    for name in sorted(files):
        if Path(name).is_absolute() or '..' in Path(name).parts:raise RuntimeError('Invalid release path')
        target=checkout/name
        if name in assets:
            if not target.exists():
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
            data=target.read_bytes();asset_records.append({'path':name,'sha256':sha(data)})
            (ROOT/name).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,ROOT/name)
        else:
            new=target.read_text(encoding='utf8').replace('\r\n','\n')
            old=git('show','HEAD:'+name).decode('utf8').replace('\r\n','\n') if name in tracked else ''
            if old==new:raise RuntimeError('Unexpected unchanged allowlist entry: '+name)
            diff=difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),
                fromfile='a/'+name if name in tracked else '/dev/null',tofile='b/'+name,n=3)
            patch.extend(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n' for line in diff)
            target.write_text(new,encoding='utf8',newline='');data=target.read_bytes()
            # Only release-owned artifacts are copied to the original workspace.
            if name.startswith(('docs/','scripts/','tests/')):
                (ROOT/name).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,ROOT/name)
        outputs.append({'path':name,'sha256':sha(data)})
    git('add','--',*sorted(files))
    git('diff','--cached','--check')
    actual=set(git('diff','--cached','--name-only').decode().splitlines())
    if actual!=files:raise RuntimeError('Unexpected isolated index contents')
    data=''.join(patch).encode('utf8');bundle.mkdir(exist_ok=True)
    (bundle/'changes.patch').write_bytes(data)
    manifest={'schema_version':2,'status':'candidate','base_revision':base,
        'remote':'https://github.com/sportscave1/sports-cave-image-factory.git',
        'patch_sha256':sha(data),'deployment_script_sha256':sha((ROOT/'scripts/deploy_table_design_v3.ps1').read_bytes()),
        'expected_tree':git('write-tree').decode().strip(),'files':sorted(files),'outputs':outputs,'assets':asset_records,
        'scope':'Presentation only; rebased on verified main. Exact baseline diagnostics recorded; all current behaviour gates mandatory.'}
    (bundle/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    print(f'Frozen candidate: {len(files)} files, base {base}, patch SHA256 {sha(data)}')
    print('Run deploy_table_design_v3.ps1 -VerifyOnly. Finalize manifest status only after that exact candidate passes.')

if __name__=='__main__':main()
