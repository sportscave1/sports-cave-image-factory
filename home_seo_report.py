"""One validated SEO edition shared by Home, SEO and the hosted brief worker."""
from datetime import date, datetime, timezone
from html import escape
import json
from urllib.parse import urlsplit

KEY = 'home_seo_daily_report'
HISTORY = 'seo_daily_report:'
MAX_PAYLOAD = 40000
STRATEGY = '''Grow qualified non-branded Google traffic and organic landing-page orders in AU, US and UK; CA and NZ are secondary. Rankings are a diagnostic, not the business goal.

Daily at 04:00 Australia/Sydney: check source freshness and technical blockers first. Compare the latest complete 28 days with the prior 28 by market, and use seven days only as an emerging-demand signal. Inspect GSC query/page evidence, GA4 organic landing-page conversions, Shopify availability, converting Google Ads search terms and Meta creative demand where verified. Missing sources remain gaps, never zeros.

Shortlist up to three buying opportunities and choose one priority. Match each intent to an existing durable collection or relevant available edition. Check live titles, descriptions, canonicals, indexing and internal links before preparing an exact change. Avoid repeated rewrites and keyword stuffing. Preserve collector titles and product facts.

Companion work stays in Companion: use approved task instructions with URL, market, evidence, exact before/after, verification and rollback. Report publication does not authorize storefront edits, redirects, theme rules or external posting. Record actual completion separately from approval. Review outcomes at 14 and 28 days with stock, promotions and sporting-event context.

Weekly: research relevant club publications, collector newsletters and sports gift guides; prepare individual editorial pitches for review. Never mass-post links or fabricate endorsements. Merchant Center diagnostics and a public-storefront crawl are the next coverage checks; connected status alone does not prove usable data.'''


def _text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('SEO report text is missing or too long.')
    return value.strip()


def parse(raw, today):
    if not isinstance(raw, str) or len(raw) > MAX_PAYLOAD:
        raise ValueError('SEO report exceeds the size limit.')
    edition = json.loads(raw)
    required = {'date', 'summary', 'period_start', 'period_end', 'source_gaps', 'opportunities', 'next_action'}
    if not isinstance(edition, dict) or set(edition) != required or edition['date'] != str(today):
        raise ValueError("Supply today's Sydney SEO edition with the required fields.")
    start, end = date.fromisoformat(edition['period_start']), date.fromisoformat(edition['period_end'])
    if start > end or end >= today or (end - start).days != 27:
        raise ValueError('Use a completed 28-day evidence window.')
    edition['summary'] = _text(edition['summary'], 600)
    edition['next_action'] = _text(edition['next_action'], 1200)
    if not isinstance(edition['source_gaps'], list) or len(edition['source_gaps']) > 12:
        raise ValueError('Supply a bounded source gap list.')
    edition['source_gaps'] = [_text(gap, 300) for gap in edition['source_gaps']]
    rows = edition['opportunities']
    if not isinstance(rows, list) or len(rows) > 3:
        raise ValueError('Supply up to three evidenced opportunities.')
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'query', 'market', 'url', 'evidence', 'action', 'availability'}:
            raise ValueError('Each opportunity needs query, market, url, evidence, action and availability.')
        for field, limit in (('query', 200), ('evidence', 1200), ('action', 1200), ('availability', 300)):
            row[field] = _text(row[field], limit)
        target = urlsplit(_text(row['url'], 1200))
        if (target.scheme != 'https' or target.hostname not in {'sportscaveshop.com', 'www.sportscaveshop.com'}
                or target.username or target.password or target.port not in (None, 443)):
            raise ValueError('Opportunity targets must be public Sports Cave storefront URLs.')
        if row['market'] not in ('AU', 'US', 'UK', 'CA', 'NZ'):
            raise ValueError('Choose a supported market.')
    return edition


def publish(raw, user):
    import os_accounts
    from sports_sales_calendar import sydney_date
    from supabase_backend import connect
    if not os_accounts.is_reporting_owner(user) or not os_accounts.can_access_page(user, 'seo'):
        raise PermissionError('SEO report publication requires the reporting owner and SEO access.')
    edition = parse(raw, sydney_date())
    saved = {**edition, 'published_at': datetime.now(timezone.utc).isoformat()}
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (KEY,))
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (KEY,))
        previous = cur.fetchone()
        if previous and previous['value'].get('date', '') > edition['date']:
            raise ValueError('A newer SEO report is already published.')
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (HISTORY + edition['date'],))
        archived = cur.fetchone()
        if archived:
            if {k: archived['value'].get(k) for k in edition} != edition:
                raise ValueError('This date already has a different SEO edition.')
            saved = archived['value']
        for key in (KEY, HISTORY + edition['date']):
            cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now())
                ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()''', (key, json.dumps(saved)))
    return edition


def latest():
    from supabase_backend import get_app_setting
    return get_app_setting(KEY, ensure_schema_first=False) or {}


def compact_html(saved, today):
    heading = '<strong>SEO daily review</strong>'
    if not saved:
        body = '<p>Awaiting the first report · daily at 4:00 am Sydney.</p>'
    else:
        stamp = escape(str(saved.get('date', '')))
        state = ' · awaiting today’s report' if saved.get('date') != str(today) else ''
        body = f'<small>{stamp}{state} · {escape(saved.get("period_start", ""))} – {escape(saved.get("period_end", ""))}</small><p>{escape(saved.get("summary", ""))}</p>'
        rows = saved.get('opportunities', [])[:3]
        body += '<ul>' + ''.join(f'<li>{escape(r["market"])} · {escape(r["query"])}</li>' for r in rows) + '</ul>'
        if saved.get('source_gaps'):
            body += ('<details><summary>' + str(len(saved['source_gaps'])) + ' source gaps</summary><small>'
                     + escape('; '.join(saved['source_gaps'])) + '</small></details>')
    return ('<section class="sc-meta-insight sc-seo-daily" aria-label="SEO daily review" style="padding:.6rem .75rem">'
            + heading + body + '<a href="/?page=seo">Open SEO review, plan and reports →</a></section>')
