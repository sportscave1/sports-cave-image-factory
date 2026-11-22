"""Durable, serial Codex fallback for the existing Edition Companion.

Only the server's scoped preparation-host outbox is consumed. No shell strings,
new credentials, browser-profile scraping, or additional worker service.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
HOME=Path.home()/'Documents/SportsCaveAutoEditions'
TARGET=HOME/'edition-repair-target.json'
OUTBOX=HOME/'edition-repairs'
LAST_STATUS={'state':'Unknown'}

def executable():
    """Logon workers inherit an older PATH than the desktop app."""
    found=shutil.which('codex')
    if found:return found
    if os.name!='nt':return None
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
            'Get-AppxPackage -Name OpenAI.Codex | Select-Object -ExpandProperty InstallLocation | ConvertTo-Json -Compress'],
            capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:return None
        locations=json.loads(result.stdout)
        for location in locations if isinstance(locations,list) else [locations]:
            path=Path(location)/'app/resources/codex.exe'
            if path.is_file():return str(path)
    except (OSError,ValueError,TypeError,subprocess.TimeoutExpired):pass
    return None

def atomic(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value),encoding='utf-8');os.replace(tmp,path)

def configuration():
    if not TARGET.exists():return None
    data=json.loads(TARGET.read_text(encoding='utf-8'))
    if set(data)!={'thread_id','cwd'} or str(uuid.UUID(data['thread_id']))!=data['thread_id'] or not Path(data['cwd']).is_dir():raise ValueError('Edition repair chat configuration is invalid.')
    return data

def poll(config,host_request):
    global LAST_STATUS
    target=configuration()
    if not target:
        LAST_STATUS={'state':'Unavailable','reason':'Repair chat is not configured.'}
        return False
    OUTBOX.mkdir(exist_ok=True)
    from device_trust import protect
    # Intent stays durable until an acknowledged server receipt. After an
    # uncertain launch, never dispatch the same repair twice.
    for file in OUTBOX.glob('*.dpapi'):
        saved=json.loads(protect(file.read_bytes(),decrypt=True))
        receipt=file.with_suffix('.result.json')
        if not receipt.exists():
            LAST_STATUS={'state':'Running'}
            return True
        result=json.loads(receipt.read_text())
        message=result.get('message')
        verified=isinstance(message,str) and bool(message.strip())
        host_request(config,'/api/auto-editions/onboarding/repair-result',
            {**{k:saved['repair'][k] for k in ('product_gid','request_id','handoff_token')},
             'ok':result['ok'] is True and verified,'message':message[:500] if verified else
                 'Legacy Companion returned no structured repair result. Re-run PSD repair with the upgraded Companion.'})
        file.rename(file.with_suffix('.acknowledged'))
        return True
    binary=executable()
    if not binary:
        LAST_STATUS={'state':'Unavailable','reason':'Codex executable is unavailable to the background companion.'}
        return False
    LAST_STATUS={'state':'Ready'}
    repair=host_request(config,'/api/auto-editions/onboarding/repair-claim',{}).get('repair')
    if not repair:return False
    key=str(uuid.UUID(repair['request_id']))
    if not isinstance(repair.get('prompt'),str) or not 1<=len(repair['prompt'])<=20000:raise ValueError('Bounded edition repair prompt required.')
    state=OUTBOX/(key+'.dpapi')
    if state.exists() or state.with_suffix('.acknowledged').exists():raise ValueError('This repair handoff already has a local receipt.')
    state.write_bytes(protect(json.dumps(dict(repair=repair,target=target,executable=binary)).encode()))
    try:
        subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),str(state)],
            cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except OSError:
        atomic(state.with_suffix('.result.json'),{'ok':False})
    return True

def outcome(path,returncode):
    """A normal CLI exit is not evidence that the PSD repair succeeded."""
    try:
        result=json.loads(path.read_text(encoding='utf-8'))
        if (set(result)!={'outcome','message'} or result['outcome'] not in ('completed','queued','blocked')
                or not isinstance(result['message'],str) or not result['message'].strip()):raise ValueError()
    except (OSError,ValueError,TypeError):
        return dict(ok=False,message='Companion returned no verified repair result. Check the local Codex runtime and retained repair log.')
    return dict(ok=returncode==0 and result['outcome'] in ('completed','queued'),message=result['message'][:500])


def execute(state):
    from device_trust import protect
    saved=json.loads(protect(state.read_bytes(),decrypt=True))
    target=saved['target'];result=dict(ok=False,message='Companion repair process did not complete. The PSD and repair log are retained.')
    # Keep ordinary Codex permission/sandbox configuration. Never bypass it.
    # The desktop can keep the configured chat's writer open indefinitely.
    # Each durable repair gets its own CLI session; the bounded server prompt
    # carries its complete scope and the configured working directory is kept.
    final=state.with_suffix('.final.json')
    command=[saved['executable'],'exec','--json','--output-schema',str(ROOT/'config/auto_editions/repair-result.schema.json'),
             '--output-last-message',str(final),'-']
    prompt=saved['repair']['prompt']+'\nReturn the required JSON result. Use blocked when tools are unavailable or no repair was applied. Use queued only after a durable native preparation/JPG queue acknowledgement, and completed only after verifying Ready/Open. Include the exact blocker in message without paths, credentials or customer data.'
    try:
        with state.with_suffix('.log').open('wb') as log:
            process=subprocess.run(command,input=prompt.encode(),cwd=target['cwd'],
                stdout=log,stderr=log,timeout=5400,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result=outcome(final,process.returncode)
    except (OSError,subprocess.TimeoutExpired):pass
    finally:atomic(state.with_suffix('.result.json'),result)

if __name__=='__main__':execute(Path(sys.argv[1]))
