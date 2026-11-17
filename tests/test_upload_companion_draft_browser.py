"""Exercise the real contenteditable/paste path with a wholly synthetic ChatGPT page."""
from pathlib import Path
from playwright.sync_api import sync_playwright


def test_restored_draft_is_preserved_and_only_the_upload_prompt_is_sent():
    source=(Path(__file__).resolve().parents[1]/'windows-upload-companion/composer.js').read_text(encoding='utf8')
    project='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project'
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page()
            page.route('**/*',lambda route: route.fulfill(content_type='text/html',body='''
                <style>[contenteditable],.user-body{white-space:pre-wrap}</style>
                <form><div role="textbox" contenteditable="true" aria-label="New chat in SC Mockups/Uploads">Unfinished user draft - keep this safe</div>
                <button type="button" aria-label="Select ChatGPT model" aria-controls="picker" aria-expanded="false">Model</button>
                <button type="button" data-testid="send-button">Send</button></form>
                <div id="picker" role="menu"><div role="menuitem" aria-label="Power">Power</div><div role="status">5 of 6</div></div>
            '''))
            page.goto(project)
            page.evaluate('''() => {
                window.backups=[];window.sent=[];
                window.chrome={runtime:{id:'fixture',onMessage:{addListener:f=>window.receive=f},sendMessage:async m=>{
                    if(m.type==='project:backup-draft')backups.push(m.text);
                    return {ok:true};
                }}};
                const editor=document.querySelector('[contenteditable]'),picker=document.querySelector('[aria-controls]');
                picker.addEventListener('keydown',e=>{if(e.key==='Enter')picker.setAttribute('aria-expanded','true');});
                document.querySelector('[role="menuitem"]').addEventListener('keydown',e=>{if(e.key==='Escape')picker.setAttribute('aria-expanded','false');});
                editor.addEventListener('paste',e=>{e.preventDefault();editor.textContent=e.clipboardData.getData('text/plain');});
                document.querySelector('[data-testid="send-button"]').addEventListener('click',()=>{
                    sent.push(editor.innerText);
                    history.pushState({},'',location.href.replace('/project','/c/01234567-0123-0123-0123-0123456789ab'));
                    const turn=document.createElement('h4');turn.dataset.conversationRole='user';
                    const body=document.createElement('div');body.className='user-body';body.textContent=editor.innerText;document.body.append(turn,body);
                });
            }''')
            page.add_script_tag(content=source)
            prompt='Run this Product Uploads workflow for Fixture.\n'+'Full upload instruction.\n'*2500
            result=page.evaluate('''prompt=>new Promise(resolve=>receive({type:'project:send',id:'a'.repeat(64),prompt,freshUpload:true},{id:'fixture'},resolve))''',prompt)
            assert result['sent'], result
            assert page.evaluate('backups')==['Unfinished user draft - keep this safe']
            assert page.evaluate('sent')==[prompt]
            assert page.locator('#sc-companion-preserved-draft pre').text_content()=='Unfinished user draft - keep this safe'
        finally:
            browser.close()
