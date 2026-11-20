"""Server-rendered public pages: usable catalogue links, metadata and JSON-LD."""
from html import escape
import json
from urllib.parse import urlencode

from marketplace import (BASE_PATH, PUBLIC_ORIGIN, SHOP_URL, CATEGORIES, CONDITIONS,
                         SPORTS, listing_url, money, public_listing)


def h(value):
    return escape(str(value), quote=True)


def jsonld(value):
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def shell(content, *, title, description, path=BASE_PATH, schema=None, nonce='', noindex=False):
    canonical = PUBLIC_ORIGIN + path
    schema = schema or {'@context': 'https://schema.org', '@type': 'WebPage', 'name': title, 'url': canonical}
    return f'''<!doctype html><html lang="en-AU"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{h(title)}</title><meta name="description" content="{h(description)}">
<meta name="theme-color" content="#101113"><meta name="robots" content="{'noindex,follow' if noindex else 'index,follow'}">
<link rel="canonical" href="{h(canonical)}"><meta property="og:type" content="website">
<meta property="og:site_name" content="Sports Cave Marketplace"><meta property="og:title" content="{h(title)}">
<meta property="og:description" content="{h(description)}"><meta property="og:url" content="{h(canonical)}">
<meta property="og:image" content="{PUBLIC_ORIGIN}{BASE_PATH}/assets/logo.webp"><meta name="twitter:card" content="summary">
<link rel="icon" href="/favicon.png"><link rel="preconnect" href="https://www.sportscaveshop.com" crossorigin>
<link rel="stylesheet" href="{BASE_PATH}/assets/marketplace.css?v=1">
<script type="application/ld+json" nonce="{h(nonce)}">{jsonld(schema)}</script>
<script src="{BASE_PATH}/assets/marketplace.js?v=1" defer></script></head>
<body><a class="skip" href="#main">Skip to content</a>
<header class="header"><div class="header-inner"><a class="brand" href="{BASE_PATH}" aria-label="Sports Cave Marketplace home">
<img src="{BASE_PATH}/assets/logo.webp" alt="Sports Cave" width="158" height="49"><span>MARKETPLACE</span></a>
<nav aria-label="Main navigation"><a class="shop-link" href="{SHOP_URL}">Sports Cave shop</a>
<a class="button small gold" href="{BASE_PATH}/sell">Sell an item</a></nav></div></header>
{content}
<footer class="footer"><div><strong>SPORTS CAVE</strong><span>For the love of the game.</span></div>
<nav aria-label="Footer"><a href="{SHOP_URL}">Visit the shop</a><a href="{BASE_PATH}/terms">How it works &amp; privacy</a></nav>
<p>Australia · AUD · Founding seller launch</p></footer></body></html>'''


COLLECTION_ART = '''<svg viewBox="0 0 480 290" role="img" aria-labelledby="collection-art-title">
<title id="collection-art-title">A framed sporting edition, collector jersey and trading card</title>
<defs><linearGradient id="frame" x2="1" y2="1"><stop stop-color="#d8b76e"/><stop offset=".5" stop-color="#9b7230"/><stop offset="1" stop-color="#efd69b"/></linearGradient>
<linearGradient id="paper" x2="0" y2="1"><stop stop-color="#f9f8f4"/><stop offset="1" stop-color="#dcd8cd"/></linearGradient></defs>
<ellipse cx="254" cy="267" rx="204" ry="14" fill="#000" opacity=".25"/>
<g transform="translate(45 12) rotate(-7 100 120)"><rect width="191" height="238" rx="2" fill="#08090b" stroke="url(#frame)" stroke-width="5"/>
<rect x="13" y="13" width="165" height="211" fill="url(#paper)"/><rect x="27" y="27" width="137" height="152" fill="#14232b"/>
<path d="M27 151L164 85V178H27Z" fill="#263e46"/><path d="M27 161L164 96" stroke="#cfaf67" stroke-width="2"/>
<circle cx="95" cy="61" r="13" fill="#cfaf67"/><path d="M91 78L113 82L129 126L114 131L104 107L96 134L64 152L56 139L80 119Z" fill="#e7e1d3"/>
<path d="M86 85L56 101L50 90L79 73M110 84L135 68L141 80L120 99" fill="#e7e1d3"/>
<rect x="63" y="195" width="90" height="3" fill="#b6a683"/><rect x="78" y="206" width="60" height="2" fill="#aaa396"/></g>
<g transform="translate(242 42) rotate(9 90 100)"><path d="M48 4L76 15L104 4L150 35L131 77L111 65V198H31V65L11 77L-7 35Z" fill="#202b30" stroke="#738083" stroke-width="2"/>
<path d="M49 5Q76 44 103 5" fill="none" stroke="#cbaa66" stroke-width="7"/><path d="M31 78H111M31 91H111" stroke="#cbaa66" stroke-width="5"/>
<text x="71" y="156" text-anchor="middle" font-family="Arial,sans-serif" font-weight="bold" font-size="62" fill="#e8e4d9">7</text></g>
<g transform="translate(324 133) rotate(11 54 74)"><rect width="106" height="145" rx="9" fill="#d0d6d2" stroke="#f3f3e9" stroke-width="2"/>
<rect x="9" y="9" width="88" height="23" rx="2" fill="#f2eee4"/><path d="M18 16H64M18 23H49M76 15V26M80 15V26M85 15V26" stroke="#7e7561" stroke-width="2"/>
<rect x="10" y="39" width="86" height="95" fill="#223e44"/><path d="M10 103L96 49V134H10Z" fill="#42635f"/><circle cx="53" cy="63" r="8" fill="#d9b96e"/>
<path d="M48 75H62L70 100L64 123H53L57 99L48 91L35 107L29 101Z" fill="#e5dccc"/><rect x="18" y="124" width="28" height="2" fill="#cdaa61"/></g></svg>'''


def home(config, rows, query, nonce='', unavailable=False):
    category = query.get('category', '')
    sport = query.get('sport', '')
    search = str(query.get('q', ''))[:100].strip()
    filtered = [row for row in rows if (not category or row['category'] == category)
                and (not sport or row['sport'] == sport)
                and (not search or search.casefold() in ' '.join(str(row.get(f, '')) for f in ('title', 'team', 'sport', 'description')).casefold())]
    try:
        page = max(1, min(500, int(query.get('page', '1'))))
    except (ValueError, TypeError):
        page = 1
    visible = filtered[(page - 1) * 12:page * 12]
    filters = ''.join(f'<a class="chip {"active" if category == key else ""}" href="{BASE_PATH}?{h(urlencode({"category": key}))}#finds">{h(label)}</a>' for key, label in CATEGORIES.items())
    sport_options = '<option value="">All sports</option>' + ''.join(f'<option {"selected" if sport == s else ""}>{h(s)}</option>' for s in SPORTS)
    cards = ''.join(card(row) for row in visible)
    if not cards:
        if unavailable:
            heading, detail = 'Back in a moment.', 'Listings are temporarily unavailable. Please try again shortly.'
        elif rows:
            heading, detail = 'Still looking for your next find?', 'Try another sport, category or search.'
        else:
            heading, detail = 'Your collection could start something.', 'Founding sellers are welcome. Submit a piece for the opening collection.'
        cards = f'<div class="empty"><div><h3>{h(heading)}</h3><p>{h(detail)}</p></div><a class="button dark" href="{BASE_PATH}/sell">List your first item</a></div>'
    pager = ''
    if page > 1:
        pager += f'<a class="chip" href="?{h(urlencode({**dict(query), "page": page - 1}))}#finds">Previous</a>'
    if len(filtered) > page * 12:
        pager += f'<a class="chip" href="?{h(urlencode({**dict(query), "page": page + 1}))}#finds">Next</a>'
    content = f'''<main id="main" class="home"><section class="hero"><div class="hero-copy"><p class="eyebrow">THE COLLECTOR-TO-COLLECTOR MARKETPLACE</p>
<h1>{h(config['headline'])}</h1><p class="hero-description">{h(config['description'])}</p>
<div class="hero-actions"><a class="button gold" href="{BASE_PATH}/sell">Sell a piece</a><a class="text-link" href="#finds">Find your next</a></div>
<p class="hero-note">Free founding listings <span>·</span> Australian collectors</p></div><div class="collection-art">{COLLECTION_ART}<span>PASS IT ON. KEEP THE STORY.</span></div></section>
<section id="finds" class="catalogue" aria-labelledby="finds-heading"><div class="catalogue-heading"><h2 id="finds-heading">Find your next.</h2><span>{len(filtered)} {'find' if len(filtered) == 1 else 'finds'}</span></div>
<form class="search" action="{BASE_PATH}#finds" method="get" role="search"><label class="sr-only" for="search">Search the marketplace</label><input id="search" name="q" type="search" value="{h(search)}" placeholder="Search a team, player or piece…" maxlength="100">
<label class="sr-only" for="sport">Sport</label><select id="sport" name="sport">{sport_options}</select><input type="hidden" name="category" value="{h(category)}"><button class="button dark" type="submit">Search</button></form>
<nav class="filters" aria-label="Item category"><a class="chip {"active" if not category else ""}" href="{BASE_PATH}#finds">All finds</a>{filters}</nav>
<div class="listing-grid">{cards}</div><nav class="pager" aria-label="Catalogue pages">{pager}</nav></section></main>'''
    schema = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'Organization', '@id': PUBLIC_ORIGIN + BASE_PATH + '#organisation', 'name': 'Sports Cave', 'url': SHOP_URL,
         'logo': PUBLIC_ORIGIN + BASE_PATH + '/assets/logo.webp'},
        {'@type': 'WebSite', 'name': 'Sports Cave Marketplace', 'url': PUBLIC_ORIGIN + BASE_PATH},
        {'@type': 'CollectionPage', 'name': 'Sports Cave Marketplace', 'url': PUBLIC_ORIGIN + BASE_PATH,
         'mainEntity': {'@type': 'ItemList', 'itemListElement': [
             {'@type': 'ListItem', 'position': i + 1, 'url': PUBLIC_ORIGIN + listing_url(row), 'name': row['title']}
             for i, row in enumerate(visible)]}}]}
    return shell(content, title='Sports Cave Marketplace | Memorabilia, Jerseys & Trading Cards',
                 description=config['description'], schema=schema, nonce=nonce,
                 noindex=bool(search or category or sport or page != 1))


def card(row):
    url = listing_url(row)
    return f'''<article class="listing-card"><a href="{url}"><div class="card-image"><img src="{BASE_PATH}/images/{h(row['id'])}/0.webp" alt="{h(row['title'])}" width="600" height="600" loading="lazy" decoding="async"></div>
<div class="card-copy"><span class="card-category">{h(CATEGORIES[row['category']])} · {h(row['sport'])}</span><h3>{h(row['title'])}</h3>
<div class="card-bottom"><strong>{money(row['price_cents'])}</strong><span>{h(row['condition'])}</span></div></div></a></article>'''


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
<h2>Free founding listings</h2><p>There is no submission or listing charge for this launch. The planned seller fee is 5% of the item price on a completed on-platform sale. Any payout illustration is indicative. Payment collection, seller onboarding, shipping arrangements and final sale terms will be available before checkout opens. This release accepts enquiries; it does not collect payments, reserve items or pay sellers.</p>
<h2>Your information</h2><p>Sports Cave stores your submission and enquiries to review listings, contact you and operate the marketplace. Seller email addresses stay private. Buyer enquiry details are available to Sports Cave and may be shared with the relevant seller to answer that enquiry. We do not add you to a marketing list through these forms. Avoid personal details in public descriptions and photos; uploaded photo metadata is removed.</p>
<h2>Need a hand?</h2><p>To correct or remove a listing, request access to or deletion of your information, or report an item, contact <a href="mailto:hello@sportscaveshop.com">hello@sportscaveshop.com</a>. Include your listing reference. These launch terms do not exclude rights available under applicable law.</p></main>'''
    return shell(content, title='How It Works & Privacy | Sports Cave Marketplace', description='Founding seller submissions, review, fees and privacy at Sports Cave Marketplace.', path=BASE_PATH + '/terms', nonce=nonce)
