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
        page.add_script_tag(content=script.with_name('ad-downloads.js').read_text(encoding='utf8'))
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
        page.evaluate("""j=>document.body.insertAdjacentHTML('beforeend',
            '<div data-message-author-role="user">Restore files for Sports Cave automatic ad job '+j+'</div>'+
            '<article><div data-message-author-role="assistant" data-message-id="restored-files"><a href="/restored">ad_copy.csv</a></div></article>')""",job)
        assert request('ad_copy.csv',recover=True)['response']=='restored-files'
        assert not request('ad_copy.csv',recover=True,response='wrong')['clicked']
        # A saved-chat recovery does not depend on the original prompt still
        # being rendered by ChatGPT's history virtualization.
        page.evaluate("""() => document.body.innerHTML='<article><div data-message-author-role="assistant" data-message-id="existing-files"><a href="/file">ad_copy.csv Spreadsheet</a></div></article>'""")
        assert not request('ad_copy.csv')['clicked']
        assert request('ad_copy.csv',recover=True)['response']=='existing-files'
        assert not request('ad_copy.csv',recover=True,response='wrong')['clicked']
        page.evaluate("""() => document.body.insertAdjacentHTML('afterbegin','<div data-message-author-role="user">Sports Cave automatic ad job 00000000-0000-0000-0000-000000000099</div>')""")
        assert 'different queued job' in request('ad_copy.csv',recover=True)['reason']
        browser.close()


@pytest.mark.parametrize('toast_name', ['file', 'ad_copy.csv'])
def test_work_pasted_brief_requires_bound_chat_and_finished_original_files(toast_name):
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
            document.body.innerHTML='<h4 data-conversation-role="user">You said:</h4><div><button aria-label="Pasted text(1)">Brief</button></div>'+
                '<h4 data-conversation-role="assistant">ChatGPT said:</h4><div><a href="/file">ad_copy.csv Spreadsheet</a><a href="/image">man-cave.jpg Image</a></div>';
        }""")
        page.add_script_tag(content=script.with_name('ad-downloads.js').read_text(encoding='utf8'))
        page.add_script_tag(content=script.read_text(encoding='utf8'))
        def request(**extra):
            return page.evaluate("m=>new Promise(resolve=>listener(m,{id:'fixture'},resolve))",
                                 dict(type='project:ad-artifact',job=job,name='ad_copy.csv',**extra))
        assert not request()['clicked']
        assert not request(chat=url+'wrong')['clicked']
        first=request(chat=url)
        assert first['clicked'] and first['response'].startswith('work-')
        page.evaluate("""() => document.body.insertAdjacentHTML('beforeend','<button aria-label="Stop">Stop</button>')""")
        assert 'still generating' in request(chat=url)['reason']
        page.evaluate("""() => document.querySelector('[aria-label="Stop"]').remove()""")
        assert request(chat=url,response=first['response'])['clicked']
        assert not request(chat=url,response='wrong')['clicked']
        # Work's filename button opens the viewer; only its own Download file
        # button may be invoked, never another card's action.
        page.evaluate("""() => {document.querySelector('h4[data-conversation-role="assistant"]').nextElementSibling.innerHTML=
            '<div><button aria-label="Open preview of ad_copy.csv">ad_copy.csv Spreadsheet</button><button aria-label="Download file">CSV download</button></div>'+
            '<div><button aria-label="Open preview of man-cave.jpg">man-cave.jpg Image</button><button aria-label="Download file">Image download</button></div>';}""")
        first=request(chat=url)
        assert first['clicked']
        assert page.evaluate('clicked.at(-1)')=='CSV download'
        page.evaluate("""() => document.querySelector('h4[data-conversation-role="assistant"]').nextElementSibling.insertAdjacentHTML('beforeend',
          '<table><tr><td>ad_copy.csv</td><td><a href="https://chatgpt.com/library?file_id=libfile_abc123&amp;account_id=personal">Open original</a></td></tr>'+
          '<tr><td>man-cave.jpg</td><td><a href="https://chatgpt.com/library?file_id=libfile_def456">Open original</a></td></tr></table>')""")
        first=request(chat=url)
        assert first['library']=='https://chatgpt.com/library?file_id=libfile_abc123'
        # A second conflicting Library source is not a safe fallback.
        page.evaluate("""() => document.querySelector('tr').insertAdjacentHTML('beforeend','<td><a href="https://chatgpt.com/library?file_id=libfile_999">Other</a></td>')""")
        assert not request(chat=url).get('library')
        page.evaluate("document.querySelector('tr').lastChild.remove()")
        first=request(chat=url)
        page.evaluate("""name => document.body.insertAdjacentHTML('beforeend','<ol><li role="status">Failed to download '+name+'. Please try again later.</li></ol>')""", toast_name)
        status=page.evaluate("m=>new Promise(resolve=>listener(m,{id:'fixture'},resolve))",
            dict(type='project:ad-download-status',job=job,name='ad_copy.csv',chat=url,response=first['response']))
        assert status['error']=='ChatGPT could not download ad_copy.csv'
        unrelated=page.evaluate("m=>new Promise(resolve=>listener(m,{id:'fixture'},resolve))",
            dict(type='project:ad-download-status',job=job,name='man-cave.jpg',chat=url,response=first['response']))
        assert not unrelated['error']
        request(chat=url)  # A stale toast must not contaminate a new attempt.
        status=page.evaluate("m=>new Promise(resolve=>listener(m,{id:'fixture'},resolve))",
            dict(type='project:ad-download-status',job=job,name='ad_copy.csv',chat=url,response=first['response']))
        assert not status['error']
        # ChatGPT creates and promptly revokes a blob for the native download.
        # The next alarm can still transfer its original bytes.
        page.evaluate("""() => {
            window.originalURL=URL.createObjectURL(new Blob(['original csv bytes'],{type:'text/csv'}));
            URL.revokeObjectURL(originalURL);
        }""")
        blob=page.evaluate("""m=>new Promise(resolve=>listener({...m,url:originalURL},{id:'fixture'},resolve))""",
                           dict(type='project:ad-blob',job=job,name='ad_copy.csv',chat=url,response=first['response']))
        import base64
        assert base64.b64decode(blob['data'])==b'original csv bytes'
        wrong=page.evaluate("""m=>new Promise(resolve=>listener({...m,url:originalURL},{id:'fixture'},resolve))""",
                           dict(type='project:ad-blob',job=job,name='man-cave.jpg',chat=url,response=first['response']))
        assert 'error' in wrong
        # The fingerprint survives re-rendering and removal of the original prompt.
        page.evaluate("""() => {document.querySelector('h4').nextElementSibling.remove();document.querySelector('h4').remove();document.body.innerHTML=document.body.innerHTML;}""")
        assert request(recover=True,response=first['response'])['clicked']
        page.evaluate("""() => document.body.insertAdjacentHTML('afterbegin','<h4 data-conversation-role="user">You said:</h4><div>Sports Cave automatic ad job 00000000-0000-0000-0000-000000000099</div>')""")
        assert 'different queued job' in request(recover=True)['reason']
        browser.close()
