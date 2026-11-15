"""Isolated screenshot subprocess: inert sample email, deny-by-default network."""
from io import BytesIO
from pathlib import Path
import json
import os
import sys
import subprocess
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode


def image_url(value):
    from crm_tracking import public_https, store_host
    if not public_https(value):return None
    url = urlsplit(value)
    if not url.path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):return None
    query = parse_qs(url.query)
    if set(query) - {'width','height','crop','format','v'}:return None
    if ((url.hostname == 'cdn.shopify.com' and url.path.startswith('/s/files/')) or
            (store_host(url.hostname) and url.path.startswith('/cdn/shop/files/'))):
        return urlunsplit(('https', url.netloc, url.path, urlencode({'width':320, **({'v':query['v'][0]} if 'v' in query else {})}), ''))
    # Existing deployment-owned public raster storage only. No user-supplied
    # host allowlist, signed URL, tracking endpoint or redirects.
    base = os.getenv('CRM_EMAIL_ASSET_PUBLIC_BASE_URL','').rstrip('/')
    if base and public_https(base) and value.startswith(base + '/') and not url.query:
        return value
    return None


def preview_document(doc):
    """One read-only lowering path for miniatures and full Flow previews.

    Discount substitution must precede checkout lowering: personalisation.render
    calls substitute again, whose authored-offer validation expects tokens.
    Already lowered offer text is not an authored discount section.
    """
    from crm_recovery_discount import substitute
    if not doc.get('recovery_discount'):
        # Incomplete drafts remain inspectable without inventing a promotion.
        # Authored URL tokens still fail through the normal safety validator.
        from copy import deepcopy
        import re
        def neutral(value):
            if isinstance(value,str):
                if re.search(r'(?:href|src)\s*=\s*["\'][^"\']*{{\s*discount_',value,re.I):return value
                return re.sub(r'{{\s*discount_(code|value)\s*}}',lambda m:'Discount code unavailable in sample preview' if m[1]=='code' else 'Offer unavailable in sample preview',value)
            if isinstance(value,list):return [neutral(v) for v in value]
            if isinstance(value,dict):return {k:(v if 'url' in k or 'link' in k else neutral(v)) for k,v in value.items()}
            return value
        doc=neutral(deepcopy(doc))
    doc = substitute(doc)
    from crm_checkout_preview import needs_checkout, document, sample
    if needs_checkout(doc):doc, _ = document(doc, sample(doc))
    from crm_personalisation import present, render as personalise
    if present(doc):doc = personalise(doc, {'first_name':'Alex','product_name':'Your selected edition','short_product_name':'Your selected edition','sport_category':'Sport'}, trigger='post_purchase')
    return doc


def render(doc, cfg):
    doc = preview_document(doc)
    from crm_campaign_content import render_campaign
    # production=False never creates open/click tracking URLs.
    html = render_campaign(doc, cfg, production=False)['html']
    from playwright.sync_api import sync_playwright
    from PIL import Image
    with sync_playwright() as pw:
        options = {'headless': True}
        if os.getenv('CRM_THUMBNAIL_BROWSER_CHANNEL'):options['channel'] = os.environ['CRM_THUMBNAIL_BROWSER_CHANNEL']
        if not options.get('channel') and not Path(pw.chromium.executable_path).exists():
            installed = subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'],
                capture_output=True, timeout=55, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if installed.returncode:raise RuntimeError('Chromium installation failed')
        browser = pw.chromium.launch(**options)
        try:
            context = browser.new_context(viewport={'width': 600, 'height': 790}, java_script_enabled=False, service_workers='block')
            def route(request):
                url = image_url(request.request.url) if request.request.resource_type == 'image' else None
                if not url:return request.abort()
                # Rewritten request strips all original query parameters. Redirects
                # cannot reach private hosts or tracking endpoints.
                try:
                    response = request.fetch(url=url, max_redirects=0, timeout=5000)
                    if response.status != 200 or not response.headers.get('content-type','').startswith('image/'):
                        return request.abort()
                    body = response.body()
                    if len(body)>2*1024*1024:return request.abort()
                    request.fulfill(response=response, body=body)
                except Exception:request.abort()
            context.route('**/*', route)
            page = context.new_page()
            page.set_default_timeout(12000)
            page.set_content(html, wait_until='load', timeout=15000)
            # Capture the same top-of-email area as the compact 76x100 card.
            png = page.screenshot(type='png', animations='disabled', timeout=12000)
            image = Image.open(BytesIO(png)).convert('RGB').resize((240,316), Image.Resampling.LANCZOS)
            result = BytesIO();image.save(result, format='WEBP', quality=75, method=4)
            return result.getvalue()
        finally:browser.close()


if __name__ == '__main__':
    source = json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
    try:
        Path(sys.argv[2]).write_bytes(render(source['document'], source['settings']))
    except Exception as exc:
        message=str(exc).lower()
        reason=('browser_install_failed' if 'installation failed' in message else
                'browser_runtime_unavailable' if any(x in message for x in ('executable','browser','shared libraries','playwright','dependencies')) else 'email_render_failed')
        sys.stderr.write(reason)
        sys.exit(1)
