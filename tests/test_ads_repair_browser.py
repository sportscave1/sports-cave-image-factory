"""Synthetic browser only: repair Send and collection boundaries."""
from pathlib import Path
from uuid import uuid4
import pytest
pw=pytest.importorskip('playwright.sync_api')


def test_repair_send_once_drafts_and_response_isolation():
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
        def request(kind='status',**extra):
            return page.evaluate("m=>new Promise(r=>listeners[0](m,{id:'fixture'},r))",
                dict(type='project:ad-repair-'+kind,job=jid,repair=rid,chat=url,names=['ad_copy.csv'],**extra))
        assert request()['ready']
        assert not request('send')['found']
        assert page.evaluate('sends')==0
        page.locator('#prompt-textarea').fill('User draft')
        assert not request('send',permit=True)['found']
        assert page.locator('#prompt-textarea').inner_text()=='User draft'
        page.locator('#prompt-textarea').fill('')
        assert request('send',permit=True)['found']
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
