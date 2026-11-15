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

REPO=Path(__file__).resolve().parents[1]
SITE='http://127.0.0.1:18967';LOCAL='http://127.0.0.1:18938'
LABEL='edit-'+uuid.uuid4().hex[:8]
ROOT=Path.home()/'AppData/Local/SportsCaveOS/TaskRecorderEditing-64cdf0b0'/LABEL
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
    (ROOT/'production-readonly-before.json').write_text(json.dumps(before,indent=2))
    try:
        with psycopg.connect('postgresql://postgres:synthetic-recorder-only@127.0.0.1:55439/postgres',autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier('recorder_bench_64cdf0b0_'+LABEL.replace('-','_'))))
        log=(ROOT/'preview.log').open('w',encoding='utf-8')
        process=subprocess.Popen([sys.executable,'-X','utf8',str(REPO/'scripts/task_recorder_preview.py'),
            '--root',str(ROOT/'os'),'--port','18967','--benchmark-account',LABEL],cwd=REPO,stdout=log,stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        bridge=Bridge(ROOT/'helper',18938,preview=True)
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
            await panel.locator('#name').fill('Disposable editor source')
            await panel.locator('#website').fill(LOCAL+'/demo')
            await panel.locator('#record').click();await mode('recording')
            initial_file=ROOT/'original-image.txt';initial_file.write_text('Synthetic original image')
            replacement_file=ROOT/'replacement-image.txt';replacement_file.write_text('Synthetic replacement image')
            bridge.runner.file_selector=lambda:str(initial_file)
            async def demonstrate():
                p=bridge.runner.page
                await p.goto(LOCAL+'/demo/form');await p.get_by_label('Product name',exact=True).fill('Original product')
                await p.get_by_label('Headline',exact=True).fill('Wrong headline')
                await p.get_by_label('Destination URL',exact=True).fill('https://example.com/original')
                await p.get_by_label('Category',exact=True).select_option('sport')
                await p.get_by_label('Approved',exact=True).check()
                await p.get_by_label('Image',exact=True).click()
                await p.locator('#uploadStatus').filter(has_text='Upload ready').wait_for()
                await p.get_by_role('button',name='Reveal delayed content',exact=True).click()
                await p.get_by_label('Product name',exact=True).fill('Accidental mistake')
                await p.get_by_role('button',name='Save demo product',exact=True).click()
                await p.get_by_role('link',name='Home',exact=True).click()
            await engine(demonstrate)
            await panel.locator('#stop').click();await mode('stopped')
            original=bridge.runner.draft;oid=original['id'];source=bridge.runner.store.tasks
            saved_before={suffix:(source/(oid+suffix)).read_bytes() for suffix in ('.json','.meta')}
            (ROOT/'source.json').write_text(json.dumps(original,indent=2))
            row=panel.locator(f'tr[data-task-id="{oid}"]')
            await row.get_by_role('button',name='Edit Disposable editor source',exact=True).click()
            editor=panel.locator('#stepEditor');await editor.wait_for(state='visible')
            assert await editor.get_by_label('Edited copy name',exact=True).input_value()=='Disposable editor source — edited'
            # Trim both ends: retain the form navigation through the local Save.
            start=next(i for i,s in enumerate(original['steps']) if s['action']=='navigate' and s.get('value')==LOCAL+'/demo/form')
            end=next(i for i,s in enumerate(original['steps']) if s['action']=='click' and s['locator']['value']=='Save demo product')
            await editor.get_by_label('Keep from step',exact=True).fill(str(start+1))
            await editor.get_by_label('through step',exact=True).fill(str(end+1))
            await editor.get_by_role('button',name='Keep this range',exact=True).click()
            items=editor.locator('.editor-steps > li')
            assert await items.count()==end-start+1
            # Value edits, delete a selected mistake, Undo, then delete it again.
            product=items.filter(has=panel.locator('strong').filter(has_text='Enter text in “Product name”')).first
            await product.locator('input[type=text]').fill('Edited product')
            mistaken=items.filter(has=panel.locator('input[value="Accidental mistake"]'))
            # Live input.value is not its HTML attribute; select by recorded step order instead.
            mistake_index=next(i-start for i,s in enumerate(original['steps']) if s.get('value')=='Accidental mistake')
            await items.nth(mistake_index).locator('input[type=checkbox]').check()
            await editor.get_by_role('button',name='Delete selected',exact=True).click()
            count=await items.count();await editor.get_by_role('button',name='Undo',exact=True).click();assert await items.count()==count+1
            await items.nth(mistake_index).locator('input[type=checkbox]').check()
            await editor.get_by_role('button',name='Delete selected',exact=True).click()
            # Replace the headline by actually recording in the existing engine.
            headline=items.filter(has=panel.locator('strong').filter(has_text='Enter text in “Headline”')).first
            await headline.get_by_role('button',name='Replace by recording',exact=True).click();await mode('recording')
            async def replacement():await bridge.runner.page.get_by_label('Headline',exact=True).fill('Replacement headline')
            await engine(replacement)
            await editor.get_by_role('button',name='Stop replacement',exact=True).click()
            await editor.get_by_role('button',name='Use reviewed replacement',exact=True).wait_for()
            # Exclude the initial browser navigation; retain only the replacement fill.
            await editor.locator('.editor-capture li').first.locator('input').uncheck()
            await editor.get_by_role('button',name='Use reviewed replacement',exact=True).click()
            assert await items.filter(has=panel.locator('strong').filter(has_text='Enter text in “Headline”')).count()==1
            destination=items.filter(has=panel.locator('strong').filter(has_text='Destination URL')).first
            await destination.locator('input[type=text]').fill('https://example.com/edited?category=sport')
            category=items.filter(has=panel.locator('strong').filter(has_text='Choose in “Category”')).first
            await category.locator('input[type=text]').fill('art')
            approved=items.filter(has=panel.locator('strong').filter(has_text='Set checkbox “Approved”')).first
            await approved.locator('input[type=checkbox]').last.uncheck()
            bridge.runner.file_selector=lambda:str(replacement_file)
            upload=items.filter(has=panel.locator('strong').filter(has_text='Choose file for “Image”')).first
            await upload.get_by_role('button',name='Choose file on PC',exact=True).click()
            # Add the supported readiness check after reveal, before submission.
            reveal=await items.filter(has=panel.locator('strong').filter(has_text='Click “Reveal delayed content”')).get_attribute('data-step')
            await editor.get_by_label('Text or website address',exact=True).fill('Continue after delay')
            await editor.get_by_label('Insert after step',exact=True).fill(reveal)
            await editor.get_by_role('button',name='Add readiness check',exact=True).click()
            await page.screenshot(path=str(ROOT/'editor-ready.png'),full_page=True)
            await editor.get_by_label('Readiness check',exact=True).select_option('wait_url')
            await editor.get_by_label('Text or website address',exact=True).fill(LOCAL+'/demo/form')
            await editor.get_by_label('Insert after step',exact=True).fill('1')
            await editor.get_by_role('button',name='Add readiness check',exact=True).click()
            # Per-step failure retains editor values; fixing it can then save.
            await destination.locator('input[type=text]').fill('https://example.com/?token=private')
            await editor.get_by_role('button',name='Save edited copy',exact=True).click()
            await editor.locator('.editor-error').filter(has_text='authentication').wait_for()
            await destination.locator('input[type=text]').fill('https://example.com/edited?category=sport')
            await page.screenshot(path=str(ROOT/'editor.png'),full_page=True)
            await editor.get_by_role('button',name='Save edited copy',exact=True).click()
            await editor.wait_for(state='hidden')
            edited=next(t for t in bridge.runner.store.list() if t['name']=='Disposable editor source — edited')
            eid=edited['id'];assert edited['result']=='Never run' and edited['duration_ms'] is None
            assert {suffix:(source/(oid+suffix)).read_bytes() for suffix in saved_before}==saved_before
            await page.reload();await panel.locator('#pc').filter(has_text='Connected').wait_for()
            edited_row=panel.locator(f'tr[data-task-id="{eid}"]')
            await edited_row.get_by_role('button',name='Play Disposable editor source — edited',exact=True).click()
            assert await row.get_by_role('button',name='Edit Disposable editor source',exact=True).is_disabled()
            await mode('running','completed');await mode('completed')
            async def result():return json.loads(await bridge.runner.page.locator('#result').inner_text())
            actual=await engine(result)
            assert actual=={'product':'Edited product','headline':'Replacement headline','url':'https://example.com/edited?category=sport',
                            'category':'art','approved':False,'file':'replacement-image.txt','submissions':1},actual
            await panel.locator('#message').filter(has_text='Completed').wait_for()
            await page.screenshot(path=str(ROOT/'saved-copy.png'),full_page=True)
            async def screenshot():await bridge.runner.page.screenshot(path=str(ROOT/'playback-result.png'))
            await engine(screenshot)
            assert {suffix:(source/(oid+suffix)).read_bytes() for suffix in saved_before}==saved_before
            after_production=protected_files()
            (ROOT/'production-readonly-after.json').write_text(json.dumps(after_production,indent=2))
            installed=lambda snapshot:{k:v for k,v in snapshot.items() if 'TaskRecorderHelper' in k}
            assert installed(after_production)==installed(before),'Installed production helper source changed concurrently'
            # The user may use/delete live recordings concurrently. Observe only;
            # never restore them or confuse that activity with this isolated run.
            external_changes=[k for k in set(before)|set(after_production) if before.get(k)!=after_production.get(k)]
            # Download the local package; never execute its installer.
            response=await page.request.get(SITE+'/task-recorder/setup.zip');assert response.ok
            content=await response.body();archive=zipfile.ZipFile(io.BytesIO(content))
            assert 'task_recorder/editing.py' in archive.namelist() and 'task_recorder/editor.js' in archive.namelist()
            assert b'protocol=4' in archive.read('task_recorder/device.py')
            (ROOT/'SportsCaveTaskRecorder-local-editor.zip').write_bytes(content)
            assert not errors,errors
            (ROOT/'evidence.json').write_text(json.dumps({'original_id':oid,'edited_id':eid,'result':actual,'original_unchanged':True,
                'trim_delete_undo_replacement_readiness':True,'refresh_persistence':True,'production_helper_source_unchanged':True,
                'concurrent_live_data_changes_observed':len(external_changes),
                'local_helper_protocol':bridge.agent.snapshot()['protocol'],'package_prepared_not_installed':True},indent=2))
            print('PASS full OS/auth/PC approval/Record/Stop/Edit values/trim/delete/Undo/record replacement/readiness/per-step privacy error/Save copy/refresh/actual Play result/original preserved',flush=True)
            print('Evidence: '+str(ROOT),flush=True)
            await browser.close()
    finally:
        if bridge:
            if thread and thread.is_alive():await asyncio.to_thread(bridge.shutdown)
            await asyncio.to_thread(bridge.close)
            if thread:thread.join()
        if process:
            # Kill only the isolated preview process tree started by this trial.
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) if sys.platform=='win32' else process.terminate()
        if log:log.close()


if __name__=='__main__':asyncio.run(main())
