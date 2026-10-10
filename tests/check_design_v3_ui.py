"""Browser checks against the local offline fixture; all external requests blocked."""
import json
import os
import re
from pathlib import Path
import time
from playwright.sync_api import sync_playwright

base = os.environ.get('DESIGN_V3_FIXTURE_URL', 'http://127.0.0.1:8904')
out = Path('tmp/design-v3-browser')
out.mkdir(parents=True, exist_ok=True)
results = {}
with sync_playwright() as pw:
    for channel in ('chrome', 'msedge'):
        browser = pw.chromium.launch(channel=channel, headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        context.route('**/*', lambda r: r.continue_() if r.request.url.startswith(('http://127.0.0.1', 'ws://127.0.0.1', 'data:')) else r.abort())
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        start = time.perf_counter()
        page.goto(base)
        page.get_by_text('Fixture source reads: 0', exact=True).wait_for()
        page.get_by_role('button', name='Prepare Research', exact=True).click()
        page.get_by_text('Fixture source reads: 1', exact=True).wait_for()
        research = page.get_by_role('textbox', name='Research Prompt preview', exact=True)
        # Labels use the same production prompt-card helper.
        if research.count() == 0:
            research = page.locator('textarea').filter(has_text='SPORTS CAVE SALES & DESIGN INTELLIGENCE').first
        assert 'Moment Lock' in research.input_value()
        assert 'The Catch' in research.input_value()
        page.get_by_text('Sales & Design Intelligence', exact=True).first.click()
        page.get_by_role('button', name='Refresh intelligence', exact=True).click()
        page.get_by_text('Fixture source reads: 2', exact=True).wait_for()
        assert 'The Catch' in research.input_value()
        # Current manual allocation is unchanged by brief preparation.
        page.get_by_role('combobox', name=re.compile('Sport or collection$')).click()
        page.get_by_role('option', name='Baseball', exact=True).click()
        numbers = page.get_by_role('spinbutton')
        before = [x.input_value() for x in numbers.all()]
        page.get_by_role('button', name='Prepare Design Brief', exact=True).click()
        prompt = page.get_by_role('textbox', name='Design brief prompt', exact=True)
        prompt.wait_for()
        assert 'STYLE ALLOCATION - EXACT' in prompt.input_value()
        assert 'The Baseball Memory' in prompt.input_value()
        assert before == [x.input_value() for x in numbers.all()]
        page.get_by_role('combobox', name=re.compile('Sport or collection$')).click()
        page.get_by_role('combobox', name=re.compile('Sport or collection$')).fill('NFL')
        page.get_by_role('option', name='NFL', exact=True).click()
        prompt.wait_for(state='detached')
        page.get_by_text('Simulate analytics outage', exact=True).click()
        page.get_by_role('button', name='Prepare Research', exact=True).click()
        page.wait_for_function("Array.from(document.querySelectorAll('textarea')).some(x => x.value.includes('Stored analytics unavailable'))")
        assert 'The Catch' in research.input_value()
        assert 'diagnostic must not leak' not in research.input_value()
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 1000})
            page.screenshot(path=str(out / f'{channel}-{width}.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'), 'Horizontal overflow'
        assert not errors, errors
        results[channel] = {'elapsed_seconds': round(time.perf_counter() - start, 2), 'checks': 'passed', 'console_errors': errors}
        browser.close()
(out / 'results.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
