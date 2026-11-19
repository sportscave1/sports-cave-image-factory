"""Shared read-only calendar/catalogue eligibility for morning recommendations."""
from datetime import timedelta
from urllib.parse import urlsplit

from home_brief_calendar import HISTORY_PREFIX, load_schedule, shop_product_handle
from product_sport_tags import collection_sports
from sports_categories import normalize_sport_category
from supabase_backend import connect


SPORTS_EDITORIAL_POLICY = (
    "Default to men's sport in the Sports Morning Brief summary, full brief, news, "
    "legends, rivalries, design picks and editorial calendar notes. Exclude routine "
    "women's leagues including WBBL / Women's Big Bash, AFLW, NRLW and WNBA. "
    "Men's BBL, NRL and NBA remain eligible. Allow the Matildas (Australia women's "
    "national football team). Allow significant athletics / Olympic stories and "
    "other world-famous women athletes only for major current achievements or events "
    "with source-backed broad mainstream interest and strong collector appeal; "
    "explain why the exception qualifies. An ordinary league result or local star "
    "is insufficient, and star exceptions must not reintroduce routine excluded leagues. "
    "Filter before ranking and use fewer picks rather than excluded filler. "
    "This editorial scope does not change the separate live Home calendar or "
    "the all-live-sports Meta ad recommendation workflow."
)


def live_events(today):
    return [event for event in load_schedule() if event.status(today) == "Live"]


def opportunity_context(today):
    from home_sports_morning_brief import design_sections
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT value FROM app_settings WHERE (starts_with(key,%s) OR key='home_sports_morning_brief')
                       AND value->>'date'>=%s AND value->>'date'<%s ORDER BY key DESC""",
                    (HISTORY_PREFIX, str(today - timedelta(days=7)), str(today)))
        history = [row['value'] for row in cur.fetchall()]
    return dict(
        live_calendar=[dict(sport=e.sport, markets=list(e.markets), title=e.title,
                            start_date=str(e.start), end_date=str(e.end), source=e.source)
                       for e in live_events(today)],
        recent_designs=[dict(date=old['date'], subject=item.get('subject', ''), title=item['title'])
                        for old in history for section in design_sections(old)
                        for item in old.get(section, [])],
        sports_editorial_policy=SPORTS_EDITORIAL_POLICY,
        design_policy="Top four fresh designs overall; AUS and USA priority; exclude preceding seven days. No country quotas. Apply sports_editorial_policy before ranking.")


def validate_ad_products(items, today, *, require_all=False):
    """Reject invented/off-season products and mismatched storefront collections."""
    events = live_events(today)
    if require_all and {item['sport'] for item in items} != {event.sport for event in events}:
        raise ValueError('Cover every Live Home calendar sport, including explicit catalogue or evidence gaps.')
    products = []
    for item in items:
        if not any(e.sport == item['sport'] and (item['market'] in e.markets or 'ALL' in e.markets)
                   and e.title == item['event_title'] for e in events):
            raise ValueError('Ad recommendations must match a Live Home calendar event and market.')
        if 'unavailable_reason' not in item:
            products.append(item)
            if item.get('secondary_product'):
                products.append(item['secondary_product'])
    with connect() as conn, conn.cursor() as cur:
        for item in products:
            if not any(e.sport == item['sport'] and (item['market'] in e.markets or 'ALL' in e.markets)
                       and e.title == item['event_title'] for e in events):
                raise ValueError("Ad recommendations must match a Live Home calendar event and market.")
            handle = shop_product_handle(item['product_url'])
            cur.execute("""SELECT title, status, online_store_url, raw_json FROM shopify_products
                           WHERE handle=%s""", (handle,))
            row = cur.fetchone()
            if not row or (row.get('status') or '').upper() != 'ACTIVE' or not shop_product_handle(row.get('online_store_url') or ''):
                raise ValueError("Ad product must be verified active and published in the Sports Cave catalogue.")
            if shop_product_handle(row['online_store_url']) != handle or row['title'] != item['product_title']:
                raise ValueError("Ad product title and URL must match the live catalogue.")
            collections = (row.get('raw_json') or {}).get('collections', [])
            product = row.get('raw_json') or {}
            variants = product.get('variants', [])
            if isinstance(variants, dict):
                variants = variants.get('nodes', [])
            if product.get('availableForSale') is False or (variants and all(
                    variant.get('availableForSale') is False for variant in variants)):
                raise ValueError("Ad product must have a purchasable variant.")
            if isinstance(collections, dict):
                collections = collections.get('nodes', [])
            target = urlsplit(item['collection_url']).path.rstrip('/').split('/')[-1]
            eligible = False
            for collection in collections:
                if not isinstance(collection, dict) or collection.get('handle') != target:
                    continue
                sports, _ = collection_sports(collection)
                sports |= {normalize_sport_category(collection.get('title')),
                           normalize_sport_category(collection.get('handle'))}
                eligible |= item['sport'] in sports
            if not eligible:
                raise ValueError("Ad product must belong to the specified sport collection.")
