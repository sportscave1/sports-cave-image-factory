"""Synthetic final payload/layout evidence. No provider or customer operations."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--sections')
    args=parser.parse_args()
    target=Path(args.output);target.mkdir(parents=True,exist_ok=True)
    from tests.test_crm_campaign_sections import sectioned
    from tests.test_crm_resend_marketing import ENV
    from crm_campaign_content import settings
    from crm_campaign_sections import section_defaults
    from crm_email_size import render_production,analyze_rendered_email
    cfg=settings(ENV);cfg['email_defaults']=section_defaults(cfg)
    if args.sections:cfg['email_defaults']=json.loads(Path(args.sections).read_text(encoding='utf-8'))
    message=render_production(sectioned(),cfg)
    (target/'payload.json').write_text(json.dumps(message,ensure_ascii=False,indent=2),encoding='utf-8')
    (target/'email.html').write_text(message['html'],encoding='utf-8')
    from playwright.sync_api import sync_playwright
    measurements=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(service_workers='block',java_script_enabled=False)
        import re
        from crm_thumbnail_render import image_url
        approved={url for url in re.findall(r'src="([^"]+)"',message['html']) if image_url(url)}
        def route_asset(route):
            if route.request.url not in approved:return route.abort()
            response=route.fetch(max_redirects=0,timeout=10000)
            assert response.status==200
            route.fulfill(response=response)
        context.route('**/*',route_asset)
        page=context.new_page()
        for width in (320,390,600,1000):
            page.set_viewport_size({'width':width,'height':800})
            page.set_content(message['html'])
            bounds=page.locator('img[alt="Sports Cave"]').bounding_box()
            assert page.locator('img[alt="Sports Cave"]').evaluate('(img)=>img.naturalWidth')>0
            overflow=page.evaluate('document.documentElement.scrollWidth>window.innerWidth')
            assert bounds and bounds['width']==180 and bounds['height']==54,(width,bounds)
            assert not overflow,(width,'horizontal overflow')
            measurements.append({'viewport':width,'logo':bounds,'overflow':overflow})
            page.screenshot(path=str(target/f'email-{width}.png'),full_page=True)
        browser.close()
    size=analyze_rendered_email(message['html'],message['text'])
    assert size['status']=='SAFE',size
    assert message['html'].count('sports-cave-email-logo-360.png')==1
    from crm_email_size import REPRESENTATIVE_UNSUBSCRIBE
    from html import escape
    assert message['html'].count('href="'+escape(REPRESENTATIVE_UNSUBSCRIBE,quote=True)+'"')==1
    result={'layout':measurements,'size':size}
    (target/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
