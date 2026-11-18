"""Offline synthetic ChatGPT attachment DOM; never connects to a live account."""
from pathlib import Path
import pytest

playwright = pytest.importorskip('playwright.sync_api')


def test_edge_attachment_matching_waits_and_isolates_the_original_turn():
    job='00000000-0000-0000-0000-000000000001'
    url='https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/c/'+job
    script=Path(__file__).resolve().parents[1]/'windows-upload-companion/ad-artifacts.js'
    with playwright.sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page()
        page.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html',body='<html><body></body></html>'))
        page.goto(url)
        page.evaluate("""() => {
            window.chrome={runtime:{id:'fixture',onMessage:{addListener:fn=>window.listener=fn}}};
            window.clicked=[];
            document.addEventListener('click',event=>{event.preventDefault();clicked.push(event.target.textContent);});
        }""")
        page.add_script_tag(content=script.read_text(encoding='utf8'))
        def request(name, **extra):
            return page.evaluate("m=>new Promise(resolve=>listener(m,{id:'fixture'},resolve))",
                                 dict(type='project:ad-artifact',job=job,name=name,**extra))
        page.evaluate("j=>document.body.innerHTML='<div data-message-author-role=\"user\">Sports Cave automatic ad job '+j+'</div>'",job)
        assert not request('ad_copy.csv')['clicked']
        page.evaluate("""() => document.body.insertAdjacentHTML('beforeend',
            '<article><div data-message-author-role="assistant" data-message-id="copy-response"><a href="/file">ad_copy.csv Spreadsheet</a></div></article>')""")
        assert request('ad_copy.csv')['response']=='copy-response'
        assert not request('man-cave.jpg')['clicked']
        page.evaluate("""() => document.body.insertAdjacentHTML('beforeend',
            '<article><div data-message-author-role="assistant" data-message-id="image-response"><a href="/file">man-cave.jpg Image</a></div></article>')""")
        assert request('man-cave.jpg')['response']=='image-response'
        assert not request('man-cave.jpg',response='wrong-response')['clicked']
        page.evaluate("""() => document.body.insertAdjacentHTML('beforeend',
            '<div data-message-author-role="user">Another unrelated request</div><article><div data-message-author-role="assistant" data-message-id="other"><a href="/file">collector-hallway.jpg</a></div></article>')""")
        assert not request('collector-hallway.jpg')['clicked']
        page.evaluate("""() => document.querySelector('article').insertAdjacentHTML('beforeend','<a href="/file">ad_copy.csv</a>')""")
        assert 'Ambiguous' in request('ad_copy.csv')['reason']
        assert len(page.evaluate('clicked'))==2
        # A saved-chat recovery does not depend on the original prompt still
        # being rendered by ChatGPT's history virtualization.
        page.evaluate("""() => document.body.innerHTML='<article><div data-message-author-role="assistant" data-message-id="existing-files"><a href="/file">ad_copy.csv Spreadsheet</a></div></article>'""")
        assert not request('ad_copy.csv')['clicked']
        assert request('ad_copy.csv',recover=True)['response']=='existing-files'
        assert not request('ad_copy.csv',recover=True,response='wrong')['clicked']
        page.evaluate("""() => document.body.insertAdjacentHTML('afterbegin','<div data-message-author-role="user">Sports Cave automatic ad job 00000000-0000-0000-0000-000000000099</div>')""")
        assert 'different queued job' in request('ad_copy.csv',recover=True)['reason']
        browser.close()
