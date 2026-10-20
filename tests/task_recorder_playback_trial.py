"""Disposable full OS/auth/relay/visible Windows helper editing trial; local only.
Run: python -m tests.task_recorder_editing_trial. Never installs a helper.
"""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from urllib.parse import urlencode
import psycopg
from psycopg import sql
from playwright.async_api import async_playwright
from task_recorder.server import Bridge
from tests.task_recorder_playback_fixture import fixture_server

REPO=Path(__file__).resolve().parents[1]
SITE='http://127.0.0.1:18968';LOCAL='http://127.0.0.1:18939'
LABEL='play-'+uuid.uuid4().hex[:8]
ROOT=Path.home()/'AppData/Local/SportsCaveOS/TaskRecorderPlayback-64cdf0b0'/LABEL
ROOT.mkdir(parents=True)


def protected_files():
    base=Path.home()/'AppData/Local/SportsCaveOS'
    files=list((base/'TaskRecorderV1/tasks').glob('*'))
    files += [base/'TaskRecorderV1/local-private.json']
    files += [p for p in (base/'TaskRecorderHelper/app/task_recorder').glob('*') if p.is_file()]
    files += list((base/'TaskRecorderHelper').glob('*.cmd'))+list((base/'TaskRecorderHelper').glob('*.vbs'))
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}


async def until(predicate,timeout=30):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        result=predicate()
        if result:return result
        await asyncio.sleep(.05)
    raise AssertionError('Local trial condition timed out')


async def main():
    before=protected_files();bridge=None;thread=None;process=None;log=None
    fixture, fixture_thread = fixture_server()
    (ROOT/'production-readonly-before.json').write_text(json.dumps(before,indent=2))
    try:
        with psycopg.connect('postgresql://postgres:synthetic-recorder-only@127.0.0.1:55439/postgres',autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier('recorder_bench_64cdf0b0_'+LABEL.replace('-','_'))))
        log=(ROOT/'preview.log').open('w',encoding='utf-8')
        process=subprocess.Popen([sys.executable,'-X','utf8',str(REPO/'scripts/task_recorder_preview.py'),
            '--root',str(ROOT/'os'),'--port','18968','--benchmark-account',LABEL],cwd=REPO,stdout=log,stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        bridge=Bridge(ROOT/'helper',18939,preview=True)
        thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
        async def engine(fn):return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(fn(),bridge.loop))
        async def mode(*expected):await until(lambda:bridge.runner.mode in expected)
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True)
            page=await browser.new_page(viewport={'width':1280,'height':950});page.set_default_timeout(20000)
            import httpx
            async with httpx.AsyncClient() as client:
                async def ready():
                    for _ in range(150):
                        try:
                            if (await client.get(SITE+'/task-recorder/panel')).status_code==403:return
                        except httpx.HTTPError:pass
                        if process.poll() is not None:raise AssertionError('Preview failed; see '+str(ROOT/'preview.log'))
                        await asyncio.sleep(.2)
                    raise AssertionError('Preview startup timed out')
                await ready()
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(SITE+'/?page=task_recorder')
            await page.get_by_placeholder('Username or email',exact=True).fill('recorder-'+LABEL+'@example.invalid')
            await page.get_by_placeholder('Password',exact=True).fill('RecorderPreview-Only-2026')
            await page.get_by_role('button',name='Sign in',exact=True).click()
            panel=page.frame_locator('iframe[src="/task-recorder/panel"]')
            await panel.locator('#pair').click()
            await panel.locator('#code').filter(has_text=__import__('re').compile('[A-Z2-9]{4}-')).wait_for()
            code=await panel.locator('#code').inner_text();pc=await browser.new_page()
            await pc.goto(LOCAL+'/pair#'+urlencode({'origin':SITE,'code':code}))
            await pc.get_by_label('PC name',exact=True).fill('Isolated editing PC')
            await pc.get_by_role('button',name='Continue',exact=True).click()
            await pc.get_by_role('button',name='Approve connection on this PC',exact=True).click()
            await pc.locator('#message').filter(has_text='PC connected').wait_for();await pc.close()
            await panel.locator('#pc').filter(has_text='Connected').wait_for(timeout=35000)
            await panel.locator('#name').fill('Playback source and mockup fixture')
            await panel.locator('#website').fill('http://127.0.0.1:18970/?page=product_uploads')
            await panel.locator('#record').click();await mode('recording')
            psd=ROOT/'synthetic.psd';psd.write_bytes(b'Synthetic source; no customer artwork')
            bridge.runner.file_selector=lambda:str(psd)
            async def demonstrate():
                p=bridge.runner.page
                await p.get_by_label('Choose PSD',exact=True).click()
                await p.locator('#source').filter(has_text='synthetic.psd').wait_for()
                await p.get_by_label('Product name',exact=True).fill('Local sample')
                await p.get_by_label('Category',exact=True).select_option('art')
                await p.get_by_label('Approved',exact=True).check()
                await p.get_by_role('button',name='Generate Mockups',exact=True).click()
                f=p.frame_locator('iframe[title="Black frame prompt"]')
                await f.get_by_role('button',name='Copy Black Frame Prompt',exact=True).click()
                await f.get_by_text('Copied',exact=True).wait_for()
                await f.get_by_label('Note',exact=True).fill('Flushed final value')
            await engine(demonstrate)
            await panel.locator('#stop').click();await mode('stopped')
            original=bridge.runner.draft;oid=original['id']
            assert not __import__('task_recorder.attention',fromlist=['issues']).issues(original),original
            assert any(s.get('value')=='Flushed final value' for s in original['steps']),original
            assert any(s.get('locator',{}).get('frames') for s in original['steps'])
            actions=[s['action'] for s in original['steps']]
            assert actions.index('fill') < actions.index('select'), original
            (ROOT/'recording.json').write_text(json.dumps(original,indent=2))
            saved=(bridge.runner.store.tasks/(oid+'.json')).read_bytes()
            await asyncio.to_thread(bridge.shutdown);await asyncio.to_thread(bridge.close);thread.join()
            bridge=Bridge(ROOT/'helper',18939,preview=True)
            thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
            await page.reload();await panel.locator('#pc').filter(has_text='Connected').wait_for(timeout=35000)
            row=panel.locator(f'tr[data-task-id="{oid}"]')
            await row.get_by_role('button',name='Play Playback source and mockup fixture',exact=True).click()
            await mode('running','completed');await mode('completed')
            async def result():
                p=bridge.runner.page
                await p.context.grant_permissions(['clipboard-read','clipboard-write'],origin='http://127.0.0.1:18970')
                return {'product':await p.get_by_label('Product name',exact=True).input_value(),
                        'category':await p.get_by_label('Category',exact=True).input_value(),
                        'approved':await p.get_by_label('Approved',exact=True).is_checked(),
                        'source':await p.locator('#source').inner_text(),
                        'generated':await p.locator('#generated').inner_text(),
                        'note':await p.frame_locator('iframe[title="Black frame prompt"]').get_by_label('Note',exact=True).input_value(),
                        'clipboard':await p.evaluate('navigator.clipboard.readText()')}
            actual=await engine(result)
            assert actual=={'product':'Local sample','category':'art','approved':True,'source':'synthetic.psd',
                           'generated':'Mockups generated: 1','note':'Flushed final value','clipboard':'Synthetic black frame prompt'},actual
            assert (bridge.runner.store.tasks/(oid+'.json')).read_bytes()==saved
            await panel.locator('#message').filter(has_text='Completed').wait_for()
            await page.screenshot(path=str(ROOT/'completed-ui.png'),full_page=True)
            async def shot():await bridge.runner.page.screenshot(path=str(ROOT/'playback-result.png'))
            await engine(shot)
            after=protected_files()
            assert {k:v for k,v in before.items() if 'TaskRecorderHelper' in k}=={k:v for k,v in after.items() if 'TaskRecorderHelper' in k}
            (ROOT/'evidence.json').write_text(json.dumps({'recording_id':oid,'revision':bridge.runner.store.revision(original),
                'steps':len(original['steps']),'result':actual,'restart_persistence':True,'saved_sequence_unchanged':True,
                'run':json.loads(bridge.runner.store.journal.read_text()),'installed_helper_unchanged':True},indent=2))
            assert not errors,errors
            print('PASS actual OS UI Record / Stop-save / helper restart / reload / Play / source, mockups, clipboard and final frame input',flush=True)
            print('Evidence: '+str(ROOT),flush=True)
            await browser.close()
    finally:
        fixture.shutdown();fixture.server_close();fixture_thread.join()
        if bridge:
            if thread and thread.is_alive():await asyncio.to_thread(bridge.shutdown)
            await asyncio.to_thread(bridge.close)
            if thread:thread.join()
        if process:
            # Kill only the isolated preview process tree started by this trial.
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) if sys.platform=='win32' else process.terminate()
        if log:log.close()


if __name__=='__main__':asyncio.run(main())
