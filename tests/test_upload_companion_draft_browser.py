"""Exercise the real contenteditable/paste path with a wholly synthetic ChatGPT page."""
from pathlib import Path
import base64
import hashlib
import pytest
from playwright.sync_api import sync_playwright


@pytest.mark.parametrize('with_reference', [False, True])
@pytest.mark.parametrize('text_attachment', [False, True])
def test_restored_draft_is_preserved_and_only_the_upload_prompt_is_sent(with_reference, text_attachment):
    source=(Path(__file__).resolve().parents[1]/'windows-upload-companion/composer.js').read_text(encoding='utf8')
    project='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project'
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page()
            page.route('**/*',lambda route: route.fulfill(content_type='text/html',body='''
                <style>[contenteditable],.user-body{white-space:pre-wrap}</style>
                <form><div role="textbox" contenteditable="true" aria-label="New chat in SC Mockups/Uploads">Unfinished user draft - keep this safe</div>
                <input type="file">
                <button type="button" aria-label="Select ChatGPT model" aria-controls="picker" aria-expanded="false">Model</button>
                <button type="button" data-testid="send-button">Send</button></form>
                <div id="picker" role="menu"><div role="menuitem" aria-label="Power">Power</div><div role="status">5 of 6</div></div>
            '''))
            page.goto(project)
            page.evaluate('value=>window.useTextAttachment=value',text_attachment)
            page.evaluate('''() => {
                window.backups=[];window.sent=[];window.uploaded=[];
                window.chrome={runtime:{id:'fixture',onMessage:{addListener:f=>window.receive=f},sendMessage:async m=>{
                    if(m.type==='project:backup-draft')backups.push(m.text);
                    return {ok:true};
                }}};
                const editor=document.querySelector('[contenteditable]'),picker=document.querySelector('[aria-controls]');
                picker.addEventListener('keydown',e=>{if(e.key==='Enter')picker.setAttribute('aria-expanded','true');});
                document.querySelector('[role="menuitem"]').addEventListener('keydown',e=>{if(e.key==='Escape')picker.setAttribute('aria-expanded','false');});
                editor.addEventListener('paste',e=>{
                    e.preventDefault();window.promptText=e.clipboardData.getData('text/plain');
                    if(!useTextAttachment){editor.textContent=promptText;return;}
                    editor.textContent='';
                    const card=document.createElement('div'),remove=document.createElement('button'),preview=document.createElement('button');
                    remove.type=preview.type='button';remove.setAttribute('aria-label','Remove pasted text attachment');
                    preview.setAttribute('aria-label',promptText.replace(/\\s+/g,' ').slice(0,70)+'…');
                    card.append(remove,preview);editor.closest('form').append(card);
                });
                document.querySelector('input[type=file]').addEventListener('change',async e=>{
                    const file=e.target.files[0];
                    uploaded.push({name:file.name,type:file.type,bytes:Array.from(new Uint8Array(await file.arrayBuffer()))});
                    const remove=document.createElement('button');remove.type='button';remove.setAttribute('aria-label','Remove image '+file.name);
                    e.target.closest('form').append(remove);
                });
                document.querySelector('[data-testid="send-button"]').addEventListener('click',()=>{
                    sent.push(useTextAttachment?promptText:editor.innerText);
                    history.pushState({},'',location.href.replace('/project','/c/01234567-0123-0123-0123-0123456789ab'));
                    const turn=document.createElement('h4');turn.dataset.conversationRole='user';
                    const body=document.createElement('div');body.className='user-body';body.textContent=editor.innerText;document.body.append(turn,body);
                    if(useTextAttachment){const pasted=document.createElement('button');pasted.setAttribute('aria-label','Pasted text(1).txt');body.append(pasted);}
                    if(uploaded.length){const image=document.createElement('img');image.alt=uploaded[0].name;body.append(image);}
                });
            }''')
            page.add_script_tag(content=source)
            prompt='Run this Product Uploads workflow for Fixture.\n'+'Full upload instruction.\n'*2500
            raw=bytes.fromhex('524946461e000000574542505650384c110000002f00000000071011fd0f4444ff0300')
            reference=dict(name='fixture-black.webp',type='image/webp',size=len(raw),
                           sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(raw).decode()) if with_reference else None
            result=page.evaluate('''({prompt,reference})=>new Promise(resolve=>receive({type:'project:send',id:'a'.repeat(64),prompt,reference,freshUpload:true},{id:'fixture'},resolve))''',dict(prompt=prompt,reference=reference))
            assert result['sent'], result
            assert page.evaluate('backups')==['Unfinished user draft - keep this safe']
            assert page.evaluate('sent')==[prompt]
            assert page.evaluate('uploaded')==([dict(name=reference['name'],type='image/webp',bytes=list(raw))] if with_reference else [])
            assert page.locator('#sc-companion-preserved-draft pre').text_content()=='Unfinished user draft - keep this safe'
        finally:
            browser.close()
