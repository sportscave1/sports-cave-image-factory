"""Bounded, read-only daily SEO evidence with explicit coverage and source dates."""
from datetime import timedelta
from decimal import Decimal
import json
from crm_growth_reporting import _available, _ga4
from google_direct_reporting import GoogleReports
import seo_phase1 as model


def context(day):
    report = GoogleReports()
    report = report.for_request(report.connection())
    start, end = model.period(28, today=day)
    result = {'period_start': str(start), 'period_end': str(end),
              'comparison': 'Previous non-overlapping 28 days; GSC final data only',
              'source_gaps': ['Google Ads search-term conversions are not supplied by this endpoint.',
                              'Meta creative performance is a demand hypothesis, not measured Google search demand.',
                              'Verify Shopify availability and the live storefront before recommending edits.',
                              'Merchant Center diagnostics and current crawl findings are not supplied.'],
              'markets': {}}
    for market, code in (('Australia', 'AU'), ('United States', 'US'), ('United Kingdom', 'UK')):
        periods = {}
        for name, offset in (('current', 0), ('prior', 28)):
            first, last = start - timedelta(days=offset), end - timedelta(days=offset)
            filters = {'market': market, 'search_type': 'web'}
            def gsc():
                rows = report.gsc(first, last, ('query', 'page'), filters)
                return {'rows': rows[:100], 'rows_returned': len(rows), 'shown': min(100, len(rows)),
                        'note': 'Bounded query/page evidence; hidden or truncated queries are not zero.'}
            contract = model.ga4_contract('Google organic', ('landingPagePlusQueryString',))
            def ga4():
                from dataclasses import replace
                filtered = replace(contract, filters=contract.filters + model.filters_for_ga4(market, 'All devices'))
                data = _ga4(report, report.connection(), filtered, first, last)
                if 'rows' in data:
                    data['rows'] = data['rows'][:100]
                    data['shown'] = len(data['rows'])
                return data
            periods[name] = {'start': str(first), 'end': str(last),
                             'gsc': _available('seo_gsc_' + code, gsc),
                             'ga4_organic_landing_pages': _available('seo_ga4_' + code, ga4)}
        result['markets'][code] = periods
    result['attribution'] = 'GA4 purchases and revenue belong to landing pages, not individual organic queries. Shopify sales are a separate truth source.'
    return json.loads(json.dumps(result, default=lambda value: float(value) if isinstance(value, Decimal) else str(value)))
