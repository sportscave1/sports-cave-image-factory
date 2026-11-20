"""Sports Cave's photograph-led marketplace discovery pages."""
from html import escape
import json
from urllib.parse import urlencode

from marketplace import (BASE_PATH, PUBLIC_ORIGIN, SHOP_URL, CATEGORIES, CONDITIONS,
                         SPORTS, listing_url, money, public_listing)


def h(value):
    return escape(str(value), quote=True)


def jsonld(value):
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


_ICONS = {
    'search': '<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.5 4.5"/>',
    'menu': '<path d="M4 6h16M4 12h16M4 18h16"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'tag': '<path d="M3 3h8l10 10-8 8L3 11Z"/><circle cx="7.5" cy="7.5" r="1"/>',
    'chat': '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H5l-3 2 1.5-6A8.5 8.5 0 1 1 21 11.5Z"/>',
    'review': '<path d="m12 3 9 4v6c0 5-9 9-9 9S3 18 3 13V7Z"/><path d="m8 12 3 3 5-6"/>',
    'frame': '<rect x="3" y="2" width="18" height="20" rx="1"/><path d="M6 5h12v12H6Z"/><path d="m7 15 4-5 3 3 3-4M9 20h6"/>',
    'jersey': '<path d="m8 3 4 2 4-2 6 5-3 4-3-2v11H8V10l-3 2-3-4Z"/><path d="M10 3q2 5 4 0M11 11h3l-3 6"/>',
    'cards': '<rect x="6" y="2" width="14" height="20" rx="2"/><path d="M3 5v14M9 7h8M9 10h8M9 13h8M9 18h4"/>',
}


def icon(name):
    return f'<svg class="icon" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{_ICONS[name]}</svg>'


def browse_url(values=None, **changes):
    values = {**dict(values or {}), **changes}
    query = urlencode({k: v for k, v in values.items() if v != '' and v is not None})
    return BASE_PATH + '/browse' + ('?' + query if query else '')


def search_form(value='', *, hero=False, filters=None):
    field = 'hero-search' if hero else 'header-search'
    hidden = ''.join(f'<input type="hidden" name="{h(k)}" value="{h(v)}">' for k, v in (filters or {}).items() if k in ('sport', 'category', 'sort') and v)
    return f'<form class="discovery-search {"hero-search" if hero else "header-search"}" action="{BASE_PATH}/browse" method="get" role="search"><label class="sr-only" for="{field}">Search the marketplace</label><input id="{field}" name="q" type="search" value="{h(value)}" placeholder="Team, player or piece" maxlength="100" autocomplete="off">{hidden}<button type="submit" aria-label="Search">{icon("search")}</button></form>'


def shell(content, *, title, description, path=BASE_PATH, schema=None, nonce='', noindex=False,
          is_home=False, header_search=False, search_value='', search_filters=None):
    canonical = PUBLIC_ORIGIN + path
    schema = schema or {'@context': 'https://schema.org', '@type': 'WebPage', 'name': title, 'url': canonical}
    category_links = ''.join(f'<a href="{h(browse_url(category=k))}">{h(v)}</a>' for k, v in CATEGORIES.items())
    sport_links = ''.join(f'<a href="{h(browse_url(sport=s))}">{h(s)}</a>' for s in SPORTS)
    preload = f'<link rel="preload" as="image" href="{BASE_PATH}/assets/collector-room-1600.webp" imagesrcset="{BASE_PATH}/assets/collector-room-800.webp 800w, {BASE_PATH}/assets/collector-room-1600.webp 1600w" imagesizes="100vw">' if is_home else ''
    return f'''<!doctype html><html lang="en-AU"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{h(title)}</title><meta name="description" content="{h(description)}">
<meta name="theme-color" content="#101113"><meta name="robots" content="{'noindex,follow' if noindex else 'index,follow'}">
<link rel="canonical" href="{h(canonical)}"><meta property="og:type" content="website">
<meta property="og:site_name" content="Sports Cave Marketplace"><meta property="og:title" content="{h(title)}">
<meta property="og:description" content="{h(description)}"><meta property="og:url" content="{h(canonical)}">
<meta property="og:image" content="{PUBLIC_ORIGIN}{BASE_PATH}/assets/collector-room-1600.webp"><meta property="og:image:width" content="1600"><meta property="og:image:height" content="800"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.png"><link rel="preconnect" href="https://www.sportscaveshop.com" crossorigin>{preload}
<link rel="stylesheet" href="{BASE_PATH}/assets/marketplace.css?v=2"><link rel="stylesheet" href="{BASE_PATH}/assets/marketplace-home.css?v=3">
<script type="application/ld+json" nonce="{h(nonce)}">{jsonld(schema)}</script>
<script src="{BASE_PATH}/assets/marketplace.js?v=2" defer></script></head>
<body class="{'is-home' if is_home else 'inner-page'}"><a class="skip" href="#main">Skip to content</a>
<header class="header"><div class="header-inner {'has-search' if header_search else ''}"><div class="brand-links"><a class="brand" href="{BASE_PATH}" aria-label="Sports Cave Marketplace home"><img src="{BASE_PATH}/assets/logo.webp" alt="Sports Cave" width="158" height="49"><span>MARKETPLACE</span></a>
<details class="browse-menu"><summary>{icon('menu')}<span>Browse</span></summary><nav aria-label="Browse marketplace"><div><strong>Find your next</strong><a href="{BASE_PATH}/browse">All finds</a>{category_links}</div><div><strong>By sport</strong>{sport_links}</div></nav></details></div>
{search_form(search_value, filters=search_filters) if header_search else ''}<nav class="header-actions" aria-label="Main navigation"><a class="shop-link" href="{SHOP_URL}">Sports Cave shop</a><a class="sell-link" href="{BASE_PATH}/sell">{icon('plus')}<span>Sell an item</span></a></nav></div></header>
{content}<footer class="footer"><div class="footer-top"><div class="footer-brand"><a class="brand" href="{BASE_PATH}" aria-label="Sports Cave Marketplace home"><img src="{BASE_PATH}/assets/logo.webp" alt="Sports Cave" width="158" height="49"></a><p>For the love of the game.</p></div>
<nav aria-label="Footer marketplace"><strong>Marketplace</strong><a href="{BASE_PATH}/browse">Browse all finds</a><a href="{BASE_PATH}/terms">How it works</a><a href="{SHOP_URL}">Sports Cave shop</a></nav>
<nav aria-label="Footer collect"><strong>Collect</strong>{category_links}</nav><nav aria-label="Footer selling"><strong>Sell</strong><a href="{BASE_PATH}/sell">List an item</a><a href="{BASE_PATH}/terms#fees">Founding seller offer</a><a href="mailto:hello@sportscaveshop.com">Get in touch</a></nav></div>
<div class="footer-bottom"><span>Australia · AUD</span><p>Sports Cave Marketplace</p><a href="{BASE_PATH}/terms">Terms &amp; privacy</a></div></footer></body></html>'''


def home(config, rows, query, nonce='', unavailable=False, browse=False):
    category = query.get('category', '') if query.get('category', '') in CATEGORIES else ''
    sport = query.get('sport', '') if query.get('sport', '') in SPORTS else ''
    search = str(query.get('q', ''))[:100].strip()
    sort = query.get('sort', 'newest')
    if sort not in ('newest', 'price_low', 'price_high'):
        sort = 'newest'
    catalogue_mode = browse or bool(category or sport or search or query.get('page') or query.get('sort'))
    filtered = [row for row in rows if (not category or row['category'] == category) and (not sport or row['sport'] == sport)
                and (not search or search.casefold() in ' '.join(str(row.get(f, '')) for f in ('title', 'team', 'sport', 'description')).casefold())]
    filtered.sort(key=(lambda row: row['price_cents']) if sort != 'newest' else (lambda row: row.get('published_at', '')), reverse=sort != 'price_low')
    try:
        page = max(1, min(500, int(query.get('page', '1'))))
    except (ValueError, TypeError):
        page = 1
    visible = filtered[(page - 1) * 12:page * 12]
    count = f'{len(filtered)} {"find" if len(filtered) == 1 else "finds"}'
    filters = {'q': search, 'sport': sport, 'category': category, 'sort': sort}
    category_tabs = ''.join(f'<a class="collection-tab {"active" if category == key else ""}" href="{h(browse_url(filters, category=key, page=None))}" {"aria-current=page" if category == key else ""}>{h(label)}</a>' for key, label in CATEGORIES.items())
    tabs = f'<nav class="collection-tabs" aria-label="Item category"><a class="collection-tab {"active" if not category else ""}" href="{h(browse_url(filters, category="", page=None))}" {"aria-current=page" if not category else ""}>{"All finds" if catalogue_mode else "New finds"}</a>{category_tabs}</nav>'
    cards = ''.join(card(row) for row in visible)
    if not cards:
        if unavailable:
            heading, detail = 'Back in a moment.', 'Listings are temporarily unavailable. Please try again shortly.'
        elif rows:
            heading, detail = 'Your next find is out there.', 'Try another team, sport or category.'
        else:
            heading, detail = 'The opening collection starts with you.', 'Have a piece worth passing on?'
        categories = ''.join(f'<a class="empty-category" href="{h(browse_url(category=key))}">{icon({"memorabilia":"frame","jerseys":"jersey","cards":"cards"}[key])}<span>{h(label)}</span></a>' for key, label in CATEGORIES.items())
        action = f'<a class="button gold" href="{BASE_PATH}/sell">List an item for free</a>' if not rows else f'<a class="button dark" href="{BASE_PATH}/browse">Browse all finds</a>'
        cards = f'<div class="opening-collection"><div class="opening-categories">{categories}</div><div class="opening-copy"><h3>{h(heading)}</h3><p>{h(detail)}</p>{action}</div></div>'
    pager = ''
    if page > 1:
        pager += f'<a class="chip" href="{h(browse_url(filters, page=page - 1))}#finds">Previous</a>'
    if len(filtered) > page * 12:
        pager += f'<a class="chip" href="{h(browse_url(filters, page=page + 1))}#finds">Next</a>'
    controls = ''
    if catalogue_mode:
        sport_options = '<option value="">All sports</option>' + ''.join(f'<option {"selected" if sport == s else ""}>{h(s)}</option>' for s in SPORTS)
        sort_options = ''.join(f'<option value="{value}" {"selected" if sort == value else ""}>{label}</option>' for value, label in (('newest','Newest first'),('price_low','Price: low to high'),('price_high','Price: high to low')))
        controls = f'<form class="browse-controls" action="{BASE_PATH}/browse" method="get"><input type="hidden" name="q" value="{h(search)}"><input type="hidden" name="category" value="{h(category)}"><label><span class="sr-only">Sport</span><select name="sport">{sport_options}</select></label><label><span class="sr-only">Sort finds</span><select name="sort">{sort_options}</select></label><button type="submit" class="button apply-filters">Apply filters</button></form>'
    collection = f'<section id="finds" class="catalogue section-width" aria-labelledby="finds-heading"><div class="catalogue-heading"><h2 id="finds-heading">{"Find your next." if catalogue_mode else "From one collection to the next."}</h2><span>{count}</span></div>{controls}{tabs}<div class="listing-grid">{cards}</div><nav class="pager" aria-label="Catalogue pages">{pager}</nav></section>'
    if catalogue_mode:
        content = f'<main id="main" class="browse-page">{collection}</main>'
    else:
        sport_links = ''.join(f'<a href="{h(browse_url(sport=s))}">{h(s)}</a>' for s in SPORTS)
        shortcuts = ''.join(f'<a href="{h(browse_url(category=key))}">{h(label)}</a>' for key, label in CATEGORIES.items())
        content = f'''<main id="main" class="home"><section class="hero" aria-labelledby="hero-heading"><img class="hero-photo" src="{BASE_PATH}/assets/collector-room-1600.webp" srcset="{BASE_PATH}/assets/collector-room-800.webp 800w, {BASE_PATH}/assets/collector-room-1600.webp 1600w" sizes="100vw" alt="" width="1600" height="800" fetchpriority="high" decoding="async"><div class="hero-shade"></div>
<div class="hero-copy"><p class="eyebrow">SPORTS CAVE MARKETPLACE</p><h1 id="hero-heading">{h(config['headline'])}</h1><p class="hero-description">{h(config['description'])}</p>{search_form(hero=True)}<nav class="hero-shortcuts" aria-label="Popular collections">{shortcuts}</nav></div><p class="hero-signoff">For the love of the game.</p></section>
<section class="marketplace-facts" aria-label="Founding marketplace"><div><strong>$0</strong><span>Founding listing fees</span></div><div><strong>3</strong><span>Collector categories</span></div><div><strong>AU</strong><span>Australian collectors</span></div></section>
<nav class="sports-strip section-width" aria-label="Browse by sport"><span>Follow your game</span><div>{sport_links}</div></nav>{collection}
<section class="buying section-width" aria-labelledby="buying-heading"><h2 id="buying-heading">Collecting. Made personal.</h2><div class="buying-columns"><div>{icon('tag')}<h3>Collector to collector</h3><p>Find a piece from someone who shares your passion.</p></div><div>{icon('chat')}<h3>Ask before you buy</h3><p>Send an enquiry while your contact details stay private.</p></div><div>{icon('review')}<h3>A considered collection</h3><p>Every listing is reviewed before it goes live.</p></div></div><a class="text-link" href="{BASE_PATH}/terms">How it works</a></section>
<section class="seller-strip section-width"><div><p class="eyebrow">MAKE ROOM FOR WHAT’S NEXT</p><h2>Your collection. A new chapter.</h2></div><a class="button gold" href="{BASE_PATH}/sell">Sell an item</a></section></main>'''
    schema = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'Organization', '@id': PUBLIC_ORIGIN + BASE_PATH + '#organisation', 'name': 'Sports Cave', 'url': SHOP_URL, 'logo': PUBLIC_ORIGIN + BASE_PATH + '/assets/logo.webp'},
        {'@type': 'WebSite', 'name': 'Sports Cave Marketplace', 'url': PUBLIC_ORIGIN + BASE_PATH, 'potentialAction': {'@type': 'SearchAction', 'target': {'@type': 'EntryPoint', 'urlTemplate': PUBLIC_ORIGIN + BASE_PATH + '/browse?q={search_term_string}'}, 'query-input': 'required name=search_term_string'}},
        {'@type': 'CollectionPage', 'name': 'Browse Sports Cave Marketplace' if catalogue_mode else 'Sports Cave Marketplace', 'url': PUBLIC_ORIGIN + BASE_PATH + ('/browse' if catalogue_mode else ''), 'mainEntity': {'@type': 'ItemList', 'numberOfItems': len(visible), 'itemListElement': [{'@type': 'ListItem', 'position': (page - 1) * 12 + i + 1, 'url': PUBLIC_ORIGIN + listing_url(row), 'name': row['title']} for i, row in enumerate(visible)]}}]}
    return shell(content, title='Browse Sports Memorabilia, Jerseys & Cards | Sports Cave Marketplace' if catalogue_mode else 'Sports Cave Marketplace | Memorabilia, Jerseys & Trading Cards', description=config['description'], path=BASE_PATH + ('/browse' if catalogue_mode else ''), schema=schema, nonce=nonce, noindex=bool(search or category or sport or sort != 'newest' or page != 1), is_home=not catalogue_mode, header_search=catalogue_mode, search_value=search, search_filters=filters)


def card(row):
    return f'''<article class="listing-card"><a href="{listing_url(row)}"><div class="card-image"><img src="{BASE_PATH}/images/{h(row['id'])}/0.webp" alt="{h(row['title'])}" width="600" height="600" loading="lazy" decoding="async"></div><div class="card-copy"><h3>{h(row['title'])}</h3><span class="card-category">{h(row['sport'])} · {h(row['condition'])}</span><div class="card-bottom"><strong>{money(row['price_cents'])}</strong><span>{h(CATEGORIES[row['category']])}</span></div></div></a></article>'''


def select(name, label, choices):
    items = choices.items() if isinstance(choices, dict) else ((v, v) for v in choices)
    return f'<label>{h(label)}<select name="{h(name)}" required><option value="">Select</option>' + ''.join(f'<option value="{h(k)}">{h(v)}</option>' for k, v in items) + '</select></label>'


def sell(config, nonce=''):
    if not config['intake_open']:
        return shell(f'<main id="main" class="narrow"><p class="eyebrow">SELL WITH SPORTS CAVE</p><h1>Back for more soon.</h1><p>New seller submissions are currently paused.</p><a class="button dark" href="{BASE_PATH}">Browse the marketplace</a></main>',
                     title='Sell with Sports Cave Marketplace', description='Sell your sporting collection with Sports Cave.', path=BASE_PATH + '/sell', nonce=nonce)
    form = f'''<main id="main" class="narrow"><a class="back" href="{BASE_PATH}">Marketplace</a><p class="eyebrow">SELL WITH SPORTS CAVE</p><h1>A new home for your collection.</h1>
<p class="intro">Free to submit. Reviewed before it goes live.</p><form id="seller-form" class="seller-form" data-endpoint="{BASE_PATH}/api/submissions">
<div class="form-grid"><label class="full">Item title<input name="title" maxlength="110" placeholder="Team, player and the piece" required></label>
{select('category', 'Item type', CATEGORIES)}{select('sport', 'Sport', SPORTS)}
<label>Team / player <span class="muted">(optional)</span><input name="team" maxlength="80"></label>{select('condition', 'Condition', CONDITIONS)}
<label>Asking price (AUD)<input id="price" name="price" type="number" min="10" max="50000" step=".01" inputmode="decimal" required></label>
<label>Tracked postage (AUD)<input name="shipping" type="number" min="0" max="1000" step=".01" value="0" inputmode="decimal" required></label>
<div class="quote full"><strong id="fee-quote">Founding offer: free listings. Planned seller fee: 5% on a completed sale.</strong><span>Checkout and payouts are coming next. No payment is collected with this submission.</span></div>
<label class="full">About the item<textarea name="description" rows="3" maxlength="1800" placeholder="Size, year, edition / card number, condition and any flaws." required></textarea></label>
<label class="full">Provenance <span class="muted">(optional)</span><textarea name="provenance" rows="2" maxlength="800" placeholder="Certificate, grader / certification number or where it came from. Do not include personal details."></textarea></label>
<label class="full">Actual item photos (2–4)<input id="photos" name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple required><span class="hint">JPG, PNG or WebP · up to 2 MB each. Include the back, tags and any flaws.</span></label>
<label>Public seller name<input name="seller_name" maxlength="70" autocomplete="name" required></label>{select('seller_type', 'Seller type', ('Private collector', 'Business seller'))}
<label>Your email <span class="muted">(private)</span><input name="seller_email" type="email" maxlength="254" autocomplete="email" required></label>
<label>Suburb / state<input name="location" maxlength="80" placeholder="Brisbane, QLD" required></label></div>
<label class="trap" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label>
<label class="consent"><input name="consent" type="checkbox" required><span>I own this item, my photos and description are accurate, and I agree to the <a href="{BASE_PATH}/terms" target="_blank" rel="noopener">submission terms and privacy notice</a>.</span></label>
<div class="form-submit"><button class="button gold" type="submit">Submit for review</button><p class="form-status" role="status" aria-live="polite"></p></div></form><noscript><p>Enable JavaScript to submit your item photographs.</p></noscript></main>'''
    return shell(form, title='Sell Your Memorabilia, Jerseys & Cards | Sports Cave Marketplace',
                 description='Submit your sporting collection to Sports Cave Marketplace. Free founding listings, reviewed before publication.', path=BASE_PATH + '/sell', nonce=nonce)


def item(row, nonce=''):
    row = public_listing(row)
    photos = ''.join(f'<img src="{BASE_PATH}/images/{h(row["id"])}/{i}.webp" alt="{h(row["title"])} — photo {i + 1}" width="900" height="900" {"loading=lazy" if i else "fetchpriority=high"}>' for i in range(row['photo_count']))
    content = f'''<main id="main" class="item"><a class="back" href="{BASE_PATH}">Marketplace</a><div class="item-layout"><div class="item-photos">{photos}</div>
<section class="item-details"><p class="eyebrow">{h(CATEGORIES[row['category']])} · {h(row['sport'])}</p><h1>{h(row['title'])}</h1><p class="price">{money(row['price_cents'])}</p>
<p class="muted">{money(row['shipping_cents'])} tracked postage · Asking price in AUD</p><dl><div><dt>Condition</dt><dd>{h(row['condition'])}</dd></div><div><dt>Seller</dt><dd>{h(row['seller_name'])} · {h(row['seller_type'])}</dd></div><div><dt>Location</dt><dd>{h(row['location'])}</dd></div></dl>
<p class="item-description">{h(row['description'])}</p>{'<h2>Provenance supplied by seller</h2><p class="item-description">' + h(row['provenance']) + '</p>' if row.get('provenance') else ''}
<details class="enquiry" open><summary>Ask about this item</summary><p>Sports Cave will review your enquiry with the seller. Checkout is coming next.</p>
<form id="enquiry-form" data-endpoint="{BASE_PATH}/api/enquiries"><input type="hidden" name="listing_id" value="{h(row['id'])}">
<label>Your name<input name="name" maxlength="70" autocomplete="name" required></label><label>Your email<input name="email" type="email" maxlength="254" autocomplete="email" required></label>
<label>Message<textarea name="message" rows="3" maxlength="1000" required></textarea></label><label class="trap" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label>
<label class="consent"><input name="consent" type="checkbox" required><span>I agree to the <a href="{BASE_PATH}/terms">privacy notice</a> and to sharing this enquiry with the seller.</span></label>
<button class="button gold" type="submit">Send enquiry</button><p class="form-status" role="status" aria-live="polite"></p></form></details>
<p class="item-note">Seller-supplied details. Listing review is not independent authentication.</p></section></div></main>'''
    condition = {'New / unused': 'NewCondition', 'Excellent': 'UsedCondition', 'Good': 'UsedCondition', 'Fair': 'UsedCondition'}[row['condition']]
    schema = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'Product', 'name': row['title'], 'description': row['description'], 'sku': row['id'],
         'image': [PUBLIC_ORIGIN + BASE_PATH + f'/images/{row["id"]}/{i}.webp' for i in range(row['photo_count'])],
         'itemCondition': 'https://schema.org/' + condition, 'category': CATEGORIES[row['category']],
         'offers': {'@type': 'Offer', 'price': f'{row["price_cents"] / 100:.2f}', 'priceCurrency': 'AUD',
                    'availability': 'https://schema.org/InStock', 'url': PUBLIC_ORIGIN + listing_url(row),
                    'seller': {'@type': 'Organization' if row['seller_type'] == 'Business seller' else 'Person', 'name': row['seller_name']}}},
        {'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Marketplace', 'item': PUBLIC_ORIGIN + BASE_PATH},
            {'@type': 'ListItem', 'position': 2, 'name': row['title'], 'item': PUBLIC_ORIGIN + listing_url(row)}]}]}
    return shell(content, title=row['title'] + ' | Sports Cave Marketplace', description=row['description'][:160], path=listing_url(row), schema=schema, nonce=nonce)


def terms(nonce=''):
    content = f'''<main id="main" class="narrow legal"><a class="back" href="{BASE_PATH}">Marketplace</a><p class="eyebrow">FOUNDING SELLER LAUNCH</p><h1>Good pieces. Clear expectations.</h1>
<h2>List your own collection</h2><p>Submit sporting memorabilia, jerseys or trading cards you own and are entitled to sell. Use current photographs of the actual item, describe flaws and provide evidence for signatures, grading or match-worn claims. Counterfeits and misleading listings are not accepted. Sports Cave may decline or remove a listing.</p>
<h2>Review, then publish</h2><p>Submissions are private until Sports Cave approves them. Your seller name, seller type, suburb / state, asking price, postage, item description, provenance and photographs appear publicly. Listing review does not authenticate an item or guarantee seller claims. Sellers remain responsible for accurate details. Private collectors and business sellers are identified separately.</p>
<h2 id="fees">Free founding listings</h2><p>There is no submission or listing charge for this launch. The planned seller fee is 5% of the item price on a completed on-platform sale. Any payout illustration is indicative. Payment collection, seller onboarding, shipping arrangements and final sale terms will be available before checkout opens. This release accepts enquiries; it does not collect payments, reserve items or pay sellers.</p>
<h2>Your information</h2><p>Sports Cave stores your submission and enquiries to review listings, contact you and operate the marketplace. Seller email addresses stay private. Buyer enquiry details are available to Sports Cave and may be shared with the relevant seller to answer that enquiry. We do not add you to a marketing list through these forms. Avoid personal details in public descriptions and photos; uploaded photo metadata is removed.</p>
<h2>Need a hand?</h2><p>To correct or remove a listing, request access to or deletion of your information, or report an item, contact <a href="mailto:hello@sportscaveshop.com">hello@sportscaveshop.com</a>. Include your listing reference. These launch terms do not exclude rights available under applicable law.</p></main>'''
    return shell(content, title='How It Works & Privacy | Sports Cave Marketplace', description='Founding seller submissions, review, fees and privacy at Sports Cave Marketplace.', path=BASE_PATH + '/terms', nonce=nonce)
