"""Synthetic browser only: repair Send and collection boundaries."""
from pathlib import Path
from uuid import uuid4
import pytest
pw=pytest.importorskip('playwright.sync_api')


@pytest.mark.parametrize('paragraph_paste', [False, True])
@pytest.mark.parametrize('mode', [None, 'complete_missing'])
def test_repair_send_once_drafts_and_response_isolation(paragraph_paste, mode):
    root=Path(__file__).resolve().parents[1]/'windows-upload-companion'
    jid,rid=str(uuid4()),str(uuid4())
    url='https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/c/'+jid
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page()
        page.route('**/*',lambda r:r.fulfill(content_type='text/html',body='<html><body></body></html>'))
        page.goto(url)
        page.evaluate("""j=>{
          window.listeners=[];window.sends=0;
          window.chrome={runtime:{id:'fixture',onMessage:{addListener:f=>listeners.push(f)}}};
          document.body.innerHTML='<div id="turns"><div data-message-author-role="user">Sports Cave automatic ad job '+j+'</div>'+
            '<article><div data-message-author-role="assistant" data-message-id="old"><a href="/old">ad_copy.csv</a></div></article></div>'+
            '<form><div id="prompt-textarea" contenteditable="true"></div><button type="button" aria-label="Send">Send</button></form>';
          document.querySelector('button').onclick=()=>{
            sends++;const n=document.createElement('div');n.dataset.messageAuthorRole='user';
            n.textContent=document.querySelector('#prompt-textarea').innerText;document.querySelector('#turns').append(n);
            document.querySelector('#prompt-textarea').textContent='';
          };
        }""",jid)
        page.add_script_tag(content=(root/'ad-repair.js').read_text())
        if paragraph_paste:
            # Work turns each pasted newline into a paragraph. innerText then
            # contains two newlines, unlike the string inserted by execCommand.
            page.evaluate("""() => {
              document.execCommand=(command,ui,text)=>{
                const node=document.querySelector('#prompt-textarea');
                node.replaceChildren(...text.split('\\n').map(line=>{
                  const p=document.createElement('p');p.textContent=line;return p;
                }));return true;
              };
              document.querySelector('button').disabled=true;
              setTimeout(()=>document.querySelector('button').disabled=false,4000);
            }""")
        def request(kind='status',**extra):
            return page.evaluate("m=>new Promise(r=>listeners[0](m,{id:'fixture'},r))",
                dict(type='project:ad-repair-'+kind,job=jid,repair=rid,chat=url,names=['ad_copy.csv'],mode=mode,**extra))
        assert request()['ready']
        assert not request('send')['found']
        assert page.evaluate('sends')==0
        page.locator('#prompt-textarea').fill('User draft')
        assert not request('send',permit=True)['found']
        assert page.locator('#prompt-textarea').inner_text()=='User draft'
        page.locator('#prompt-textarea').fill('')
        assert request('send',permit=True)['found']
        sent_prompt=page.locator('#turns [data-message-author-role="user"]').last.inner_text()
        if mode == 'complete_missing':
            assert 'Complete ONLY these missing deliverables: ad_copy.csv' in sent_prompt
            assert 'Do not restart the job or regenerate completed artwork' in sent_prompt
            assert 'Do not retry, rephrase around or bypass a provider safety or policy rejection' in sent_prompt
        else:
            assert 'download recovery only' in sent_prompt
            assert 'do not generate, recreate, redraw, restyle or replace an image' in sent_prompt
            assert 'change the three-line footer' in sent_prompt
            assert 'otherwise recreate' not in sent_prompt
            assert 'all four required files exist' in sent_prompt
            assert 'end with SC_AD_BLOCKED:' in sent_prompt
        assert request('send',permit=True)['found']
        assert page.evaluate('sends')==1
        # Even if virtualized history hides the sent marker, the session journal
        # refuses a repeated permit. The server also consumes it durably.
        page.evaluate("document.querySelector('#turns').lastChild.remove()")
        assert not request('send',permit=True)['found']
        assert page.evaluate('sends')==1
        page.evaluate("""m=>{
          const n=document.createElement('div');n.dataset.messageAuthorRole='user';n.textContent='Sports Cave automatic ad job '+m.j+' SC_AD_REPAIR: '+m.r;
          document.querySelector('#turns').append(n);
          document.querySelector('#turns').insertAdjacentHTML('beforeend','<article><div data-message-author-role="assistant" data-message-id="repaired"><a href="/new">ad_copy.csv</a></div></article>');
          document.addEventListener('click',e=>e.preventDefault());
        }""",dict(j=jid,r=rid))
        page.add_script_tag(content=(root/'ad-downloads.js').read_text())
        page.add_script_tag(content=(root/'ad-artifacts.js').read_text())
        result=page.evaluate("m=>new Promise(r=>listeners[1](m,{id:'fixture'},r))",
            dict(type='project:ad-artifact',job=jid,name='ad_copy.csv',repair=rid,chat=url,recover=True))
        assert result['response']=='repaired'
        # Never fall back to old broken files when the repair marker is absent.
        result=page.evaluate("m=>new Promise(r=>listeners[1](m,{id:'fixture'},r))",
            dict(type='project:ad-artifact',job=jid,name='ad_copy.csv',repair=str(uuid4()),chat=url,recover=True))
        assert not result['clicked']
        browser.close()


def test_only_exact_prepared_draft_can_continue_after_content_restart():
    root=Path(__file__).resolve().parents[1]/'windows-upload-companion'
    jid,rid=str(uuid4()),str(uuid4())
    url='https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/c/'+jid
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page()
        page.route('**/*',lambda r:r.fulfill(content_type='text/html',body='<html><body></body></html>'))
        page.goto(url)
        page.evaluate("""() => {
          window.sends=0;
          window.chrome={runtime:{id:'fixture',onMessage:{addListener:f=>window.listener=f}}};
          document.body.innerHTML='<div id="turns"></div><form><div id="prompt-textarea" contenteditable="true"></div><button type="button" aria-label="Send" disabled>Send</button></form>';
          document.querySelector('button').onclick=()=>{
            sends++;document.querySelector('#turns').textContent='';
            const n=document.createElement('div');n.dataset.messageAuthorRole='user';
            n.textContent=document.querySelector('#prompt-textarea').innerText;
            document.querySelector('#turns').append(n);document.querySelector('#prompt-textarea').textContent='';
          };
          window.realNow=Date.now;let clock=1000;Date.now=()=>clock+=121000;
        }""")
        page.add_script_tag(content=(root/'ad-repair.js').read_text())
        def request(kind='status',**extra):
            return page.evaluate("m=>new Promise(r=>listener(m,{id:'fixture'},r))",
                dict(type='project:ad-repair-'+kind,job=jid,repair=rid,chat=url,names=['ad_copy.csv'],**extra))
        assert not request('send',permit=True)['found']
        assert request()['staged']
        assert page.evaluate('sends')==0
        page.evaluate("Date.now=realNow;document.querySelector('button').disabled=false")
        # Simulate reinjection/restart with the saved draft and session journal.
        page.add_script_tag(content=(root/'ad-repair.js').read_text())
        draft=page.locator('#prompt-textarea').inner_text()
        page.locator('#prompt-textarea').fill(draft+' user edit')
        assert not request()['staged']
        assert not request('send',resume=True)['found']
        page.locator('#prompt-textarea').fill(draft)
        assert request()['staged']
        assert request('send',resume=True)['found']
        assert request('send',resume=True)['found']
        assert page.evaluate('sends')==1
        page.evaluate("document.querySelector('#turns').replaceChildren()")
        assert not request('send',resume=True)['found']
        assert page.evaluate('sends')==1
        browser.close()
