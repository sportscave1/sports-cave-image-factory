"""Actual component + Chromium + isolated HTTP, synthetic metadata only."""
import json
from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import HTMLResponse,JSONResponse,Response
from starlette.routing import Route
from playwright.sync_api import sync_playwright,expect
from tests.benchmark_product_upload_transfer import local_client

ROOT=Path(__file__).resolve().parents[1]
REVIEW='/Synthetic/Review'
LIVE='/Synthetic/Live'


def item(number,name=None,parent=REVIEW):
    return dict(id='id:'+str(number),name=name or f'Art {number}.psd',rev='a1',size=500,
                path_display=parent+'/'+(name or f'Art {number}.psd'),**{'.tag':'file'})


def fixture_app(pages):
    calls=[];fault={'page':None,'repeat':False};roots={'review':{'path':REVIEW},'live':{'path':LIVE}}
    async def html(request):return HTMLResponse((ROOT/'components/product_uploads/index.html').read_text(encoding='utf-8'))
    async def script(request):return Response((ROOT/'components/product_uploads'/request.path_params['name']).read_text(encoding='utf-8'),media_type='text/javascript')
    async def api(request):
        op=request.path_params['operation'];body=await request.json() if request.method=='POST' else {}
        calls.append((op,body))
        if op=='state':return JSONResponse(dict(enabled=True,upload=None))
        if op=='browse':
            assert body['search']==''
            n=int(body.get('page') or 0)
            if fault['page']==n:return JSONResponse({'error':'Synthetic listing interrupted'},status_code=503)
            path=body['path'] or roots[body['root']]['path']
            rows=pages[n] if path==REVIEW else [item(90001,'Scoped file.psd',path)]
            more=path==REVIEW and n<len(pages)-1
            return JSONResponse(dict(roots=roots,path=path,items=rows,has_more=more,
                next_page=str(n if fault['repeat'] else n+1) if more else ''))
        if op in ('select','prepare'):
            return JSONResponse(dict(upload=dict(id=body.get('id','selected'),name='Art 2.psd',
                state='Ready',basic_validated=True,source=item(2),mode='LIVE')))
        return JSONResponse({'error':'Unexpected operation '+op},status_code=400)
    return Starlette(routes=[Route('/',html),Route('/{name}',script),
        Route('/api/product-uploads/{operation}',api,methods=['GET','POST'])]),calls,fault


def app_for(pages):
    return fixture_app(pages)


def test_complete_global_order_search_selection_scopes_and_errors(tmp_path):
    folder=dict(id='id:folder',name='Folder',path_display=REVIEW+'/Folder',**{'.tag':'folder'})
    pages=[[item(10),item(2),item(50,'zebra.psd')],[],[item(1),item(2),item(51,'alpha.psd'),item(52,'ALPINE.psd'),folder]]
    app,calls,fault=app_for(pages)
    with local_client(app) as client,sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1280,'height':900});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(client.base);page.locator('#choose').click()
        expect(page.locator('#picker-status')).to_contain_text('Complete folder metadata loaded.')
        assert page.locator('#picker-items button').all_text_contents()==['alpha.psd','ALPINE.psd','Art 1.psd','Art 2.psd','Art 10.psd','▸ Folder','zebra.psd']
        assert [body['page'] for op,body in calls if op=='browse']==['','1','2']
        assert not any(op in ('select','prepare','preview') for op,_ in calls)
        assert page.get_by_role('button',name='Load more',exact=True).count()==0
        before=len(calls);page.locator('#picker-search').fill('ALP')
        expect(page.locator('#picker-items button')).to_have_count(2);assert len(calls)==before
        page.locator('#picker-search').fill('Art 2');expect(page.locator('#picker-items button')).to_have_count(1)
        page.get_by_role('button',name='Art 2.psd',exact=True).click()
        expect(page.locator('#picker')).not_to_be_visible();expect(page.locator('#stage')).to_have_text('Ready')
        selected=[b for op,b in calls if op=='select'];assert len(selected)==1 and selected[0]['file_id']=='id:2' and selected[0]['revision']=='a1'
        assert len([1 for op,_ in calls if op=='prepare'])==1
        page.locator('#choose').click();page.locator('#picker-search').fill('')
        expect(page.locator('#picker-items button')).to_have_count(7)
        page.get_by_role('button',name='▸ Folder',exact=True).click()
        expect(page.locator('#picker-path')).to_have_attribute('title',REVIEW+'/Folder')
        expect(page.locator('#picker-items button')).to_have_count(1)
        page.locator('#picker-root').select_option('live');expect(page.locator('#picker-path')).to_have_attribute('title',LIVE)
        fault['page']=1;page.locator('#picker-root').select_option('review')
        expect(page.locator('#picker-status')).to_contain_text('Could not load the complete folder listing.')
        assert page.locator('#picker-items button').count()==0
        expect(page.locator('#picker-retry')).to_be_visible()
        fault['page']=None;page.locator('#picker-retry').click();expect(page.locator('#picker-items button')).to_have_count(7)
        fault['repeat']=True;page.locator('#picker-close').click();page.locator('#choose').click()
        expect(page.locator('#picker-status')).to_contain_text('pagination did not finish')
        assert page.locator('#picker-items button').count()==0
        assert not errors
        browser.close()


def test_large_complete_list_scroll_and_search_remain_responsive(tmp_path):
    pages=[[item(n) for n in range(end,end-100,-1)] for end in range(10000,0,-100)]
    app,calls,_=app_for(pages)
    with local_client(app) as client,sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1280,'height':900})
        page.goto(client.base);page.locator('#choose').click()
        expect(page.locator('#picker-status')).to_contain_text('Complete folder metadata loaded.',timeout=30000)
        assert page.locator('#picker-items button').count()<80
        assert len([1 for op,_ in calls if op=='browse'])==100
        result=page.evaluate('''async()=>{const p=document.querySelector('#picker'),times=[],seen=new Map();let prev=performance.now(),peak=0;for(let y=0;y<=p.scrollHeight+p.clientHeight;y+=p.clientHeight*.6){p.scrollTop=y;for(let frame=0;frame<2;frame++){await new Promise(requestAnimationFrame);const now=performance.now();times.push(now-prev);prev=now;}const buttons=[...document.querySelectorAll('#picker-items button')];peak=Math.max(peak,buttons.length);for(const b of buttons)seen.set(Number(b.dataset.pickerIndex),b.textContent);if(p.scrollTop+p.clientHeight>=p.scrollHeight-1)break;}times.sort((a,b)=>a-b);return {names:[...seen].sort((a,b)=>a[0]-b[0]).map(x=>x[1]),timing:{p95:times[Math.floor(times.length*.95)],max:times.at(-1),peakRows:peak,height:p.getBoundingClientRect().height,viewport:innerHeight}};}''')
        assert result['names']==[f'Art {n}.psd' for n in range(1,10001)]
        timing=result['timing'];assert timing['height']<=timing['viewport'] and timing['peakRows']<80
        assert timing['p95']<35,timing
        page.locator('#picker-search').focus();page.keyboard.press('Tab');page.keyboard.press('End')
        expect(page.locator('#picker-items button:focus')).to_have_text('Art 10000.psd')
        page.keyboard.press('Home');expect(page.locator('#picker-items button:focus')).to_have_text('Art 1.psd')
        page.keyboard.press('ArrowDown');expect(page.locator('#picker-items button:focus')).to_have_text('Art 2.psd')
        page.locator('#picker-search').fill('Art 9999.psd');expect(page.locator('#picker-items button')).to_have_count(1)
        assert page.locator('#picker-items button').inner_text()=='Art 9999.psd'
        assert not any(op in ('select','prepare','preview') for op,_ in calls)
        (tmp_path/'picker-performance.json').write_text(json.dumps(timing))
        print('10000-row metadata picker scroll:',json.dumps(timing))
        browser.close()


def test_mobile_virtual_rows_preserve_wrapping_and_keyboard_selection(tmp_path):
    rows=[item(n,f'Artwork {n} with a long filename that wraps on a narrow mobile picker.psd') for n in range(300,0,-1)]
    app,calls,_=app_for([rows[:100],rows[100:200],rows[200:]])
    with local_client(app) as client,sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':390,'height':844})
        page.goto(client.base);page.locator('#choose').click()
        expect(page.locator('#picker-status')).to_contain_text('Complete folder metadata loaded.')
        assert page.locator('#picker-items button').first.bounding_box()['height']>45
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.locator('#picker-search').focus();page.keyboard.press('Tab');page.keyboard.press('End')
        expect(page.locator('#picker-items button:focus')).to_have_text(rows[0]['name'])
        page.keyboard.press('Shift+Tab')
        expect(page.locator('#picker-items button:focus')).to_have_text(rows[1]['name'])
        page.keyboard.press('Enter');expect(page.locator('#picker')).not_to_be_visible()
        assert next(body for op,body in calls if op=='select')['file_id']=='id:299'
        page.screenshot(path=str(tmp_path/'picker-mobile-selection.png'))
        browser.close()
