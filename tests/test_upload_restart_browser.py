"""Real browser, synthetic queue only: both reset icons require a click."""
from pathlib import Path
import os

from playwright.sync_api import sync_playwright


def test_failed_upload_icons_are_small_and_click_only(tmp_path):
    source = (Path(__file__).resolve().parents[1] / 'components/sports_cave_top_bar/index.html').read_text(encoding='utf8')
    css = source[source.index('    #sc-upload-notices'):source.index('    #${ROOT_ID}.sc-has-staff-upload')]
    markup = source[source.index('    <div id="sc-upload-notices"'):source.index('    <div class="sc-os-topbar-actions"')]
    logic = source[source.index('    const uploadNotices ='):source.index('    const state =')]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width': 660, 'height': 580})
            page.route('**/*', lambda route: route.abort())
            page.set_content('<style>body{background:#fafafa;font-family:Arial}#root{background:#171510;padding:14px;display:flex;justify-content:flex-end}'+css+'</style><div id="root"></div>')
            page.evaluate('''({markup,logic}) => {
                const root=document.querySelector('#root');
                root.innerHTML=eval('`'+markup+'`');
                const doc=document,parentWindow=window,listenerController=new AbortController(),listenerOptions={signal:listenerController.signal};
                const state={config:{uploadScope:'fixture',staffUploadProgress:true}},icon=()=>'',later=()=>{};
                window.requests=[];
                let job={id:'fixture-id',title:'Silver & Soul – Lewis Hamilton Wall Art',stage:7,restartable:true,
                         label:'Needs attention',detail:'ChatGPT submitted · timed out.',percent:0,updated_at:'fixture-stamp'};
                parentWindow.fetch=async(url,options)=>{
                    if(options?.method==='POST') {requests.push({url,body:JSON.parse(options.body)});job={...job,stage:0,restartable:false,label:'Restart requested'};}
                    return {ok:true,json:async()=>({online:true,jobs:[job]})};
                };
                eval(logic+';window.refreshFixture=refreshStaffProgress;');
                return refreshFixture();
            }''', dict(markup=markup, logic=logic))
            page.locator('#sc-os-staff-upload-summary').click()
            reset = page.get_by_role('button', name='Restart upload: Silver & Soul – Lewis Hamilton Wall Art', exact=True)
            assert reset.is_visible()
            assert reset.bounding_box()['width'] == 24
            assert page.locator('#sc-os-staff-upload-reset').is_visible()
            page.evaluate('refreshFixture()')
            assert page.evaluate('requests') == []
            output = Path(os.environ.get('SC_TEST_SCREENSHOT_DIR', tmp_path))
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / 'upload-reset.png'))
            reset.click()
            assert page.evaluate('requests') == [dict(url='/api/staff-product-uploads/restart', body=dict(id='fixture-id', updated_at='fixture-stamp'))]
            assert page.locator('#sc-os-staff-upload-reset').is_hidden()
            assert page.get_by_role('button', name='Restart upload:', exact=False).count() == 0
        finally:
            browser.close()
