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
          is_home=False, header_search=False, search_value='', search_filters=None, account_page=False):
    canonical = PUBLIC_ORIGIN + path
    schema = schema or {'@context': 'https://schema.org', '@type': 'WebPage', 'name': title, 'url': canonical}
    home_styles = f'<link rel="stylesheet" href="{BASE_PATH}/assets/marketplace-restore.css?v=1">' if is_home else ''
    preload = f'<link rel="preload" as="image" href="{BASE_PATH}/assets/collector-room-1600.webp" imagesrcset="{BASE_PATH}/assets/collector-room-800.webp 800w, {BASE_PATH}/assets/collector-room-1600.webp 1600w" imagesizes="100vw">' if is_home else ''
    account_assets = f'<link rel="stylesheet" href="{BASE_PATH}/assets/marketplace-accounts.css?v=1"><script src="{BASE_PATH}/assets/marketplace-accounts.js?v=1" defer></script>' if account_page else ''
    return f'''<!doctype html><html lang="en-AU"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{h(title)}</title><meta name="description" content="{h(description)}">
<meta name="theme-color" content="#101113"><meta name="robots" content="{'noindex,follow' if noindex else 'index,follow'}">
<link rel="canonical" href="{h(canonical)}"><meta property="og:type" content="website">
<meta property="og:site_name" content="Sports Cave Marketplace"><meta property="og:title" content="{h(title)}">
<meta property="og:description" content="{h(description)}"><meta property="og:url" content="{h(canonical)}">
<meta property="og:image" content="{PUBLIC_ORIGIN}{BASE_PATH}/assets/collector-room-1600.webp"><meta property="og:image:width" content="1600"><meta property="og:image:height" content="800"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.png"><link rel="preconnect" href="https://www.sportscaveshop.com" crossorigin>{preload}
<link rel="stylesheet" href="{BASE_PATH}/assets/marketplace.css?v=2"><link rel="stylesheet" href="{BASE_PATH}/assets/marketplace-home.css?v=3"><link rel="stylesheet" href="{BASE_PATH}/assets/marketplace-collect.css?v=1">{home_styles}
<script type="application/ld+json" nonce="{h(nonce)}">{jsonld(schema)}</script>
<script src="{BASE_PATH}/assets/marketplace.js?v=3" defer></script>{account_assets}</head>
<body class="{'is-home' if is_home else 'inner-page'}"><a class="skip" href="#main">Skip to content</a>
<header class="header"><div class="header-inner {'has-search' if header_search else ''}"><div class="brand-links"><a class="brand" href="{BASE_PATH}" aria-label="Sports Cave Marketplace home"><img src="{BASE_PATH}/assets/logo.webp" alt="Sports Cave" width="158" height="49"><span>MARKETPLACE</span></a>
</div><nav class="header-actions" aria-label="Main navigation"><a class="shop-link" href="{BASE_PATH}/terms">How it works</a><a class="account-link" href="{BASE_PATH}/account">Account</a><a class="sell-link" href="{BASE_PATH}/sell">{icon('plus')}<span>Sell an item</span></a></nav></div></header>
{content}<footer class="footer"><div class="footer-top"><div class="footer-brand"><a class="brand" href="{BASE_PATH}" aria-label="Sports Cave Marketplace home"><img src="{BASE_PATH}/assets/logo.webp" alt="Sports Cave" width="158" height="49"></a><p>For the love of the game.</p></div>
<nav aria-label="Footer marketplace"><strong>Marketplace</strong><a href="{BASE_PATH}">The collection</a><a href="{BASE_PATH}/inbox">Your messages</a><a href="{BASE_PATH}/terms">How it works</a><a href="{SHOP_URL}">Sports Cave shop</a></nav>
<nav aria-label="Footer buying"><strong>Buying</strong><a href="{BASE_PATH}/paypal">PayPal</a><a href="{BASE_PATH}/buyer-protection">Buyer Protection</a><a href="{BASE_PATH}/terms">Terms &amp; privacy</a></nav><nav aria-label="Footer selling"><strong>Sell</strong><a href="{BASE_PATH}/sell">List an item</a><a href="{BASE_PATH}/terms#fees">Founding seller offer</a><a href="mailto:hello@sportscaveshop.com">Get in touch</a></nav></div>
<div class="footer-bottom"><span>Australia · AUD</span><p>Sports Cave Marketplace</p><a href="{BASE_PATH}/terms">Terms &amp; privacy</a></div></footer></body></html>'''


def home(config, rows, query, nonce='', unavailable=False, browse=False):
    # Keep existing search links working, without category navigation on a small catalogue.
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
    filters = {'q': search, 'sport': sport, 'category': category, 'sort': sort}
    cards = ''.join(card(row) for row in visible)
    if not cards:
        if unavailable:
            heading, detail = 'Back in a moment.', 'The collection is temporarily unavailable. Please try again shortly.'
        elif rows:
            heading, detail = 'A fresh look?', 'No pieces match this selection.'
        else:
            heading, detail = 'Be part of the opening collection.', 'A favourite jersey. A signed piece. A card worth passing on.'
        action = f'<a class="button gold" href="{BASE_PATH}/sell">List your first item</a>' if not rows and not unavailable else f'<a class="text-link" href="{BASE_PATH}#finds">Back to the collection</a>'
        cards = f'<div class="opening-collection opening-simple"><div class="opening-mark" aria-hidden="true">{icon("plus")}</div><div class="opening-copy"><h3>{h(heading)}</h3><p>{h(detail)}</p>{action}</div></div>'
    pager = ''
    if page > 1:
        pager += f'<a class="chip" href="{h(browse_url(filters, page=page - 1))}#finds">Previous</a>'
    if len(filtered) > page * 12:
        pager += f'<a class="chip" href="{h(browse_url(filters, page=page + 1))}#finds">Next</a>'
    controls = ''
    if catalogue_mode:
        options = ''.join(f'<option value="{value}" {"selected" if sort == value else ""}>{label}</option>' for value, label in (('newest','Newest first'),('price_low','Price: low to high'),('price_high','Price: high to low')))
        controls = f'<form class="browse-controls quiet-search" action="{BASE_PATH}/browse" method="get"><label><span class="sr-only">Search the collection</span><input type="search" name="q" value="{h(search)}" placeholder="Search the collection" maxlength="100"></label><input type="hidden" name="category" value="{h(category)}"><input type="hidden" name="sport" value="{h(sport)}"><label><span class="sr-only">Sort pieces</span><select name="sort">{options}</select></label><button class="button dark" type="submit">Update</button></form>'
    count = f'<span>{len(filtered)} {"piece" if len(filtered) == 1 else "pieces"}</span>' if filtered else ''
    collection = f'<section id="finds" class="catalogue section-width" aria-labelledby="finds-heading"><div class="catalogue-heading"><h2 id="finds-heading">The collection.</h2>{count}</div>{controls}<div class="listing-grid">{cards}</div><nav class="pager" aria-label="Collection pages">{pager}</nav></section>'
    if catalogue_mode:
        content = f'<main id="main" class="browse-page">{collection}</main>'
    else:
        sport_links = ''.join(f'<a href="{h(browse_url(sport=s))}">{h(s)}</a>' for s in SPORTS)
        shortcuts = ''.join(f'<a href="{h(browse_url(category=key))}">{h(label)}</a>' for key, label in CATEGORIES.items())
        tabs = f'<nav class="collection-tabs" aria-label="Item category"><a class="collection-tab active" href="{BASE_PATH}/browse" aria-current="page">New finds</a>' + ''.join(f'<a class="collection-tab" href="{h(browse_url(category=key))}">{h(label)}</a>' for key, label in CATEGORIES.items()) + '</nav>'
        home_cards = cards
        if not visible:
            tiles = ''.join(f'<a class="empty-category" href="{h(browse_url(category=key))}">{icon({"memorabilia":"frame","jerseys":"jersey","cards":"cards"}[key])}<span>{h(label)}</span></a>' for key, label in CATEGORIES.items())
            home_cards = f'<div class="opening-collection"><div class="opening-categories">{tiles}</div><div class="opening-copy"><h3>{h(heading)}</h3><p>{h(detail)}</p>{action}</div></div>'
        home_collection = f'<section id="finds" class="catalogue section-width" aria-labelledby="finds-heading"><div class="catalogue-heading"><h2 id="finds-heading">From one collection to the next.</h2>{count}</div>{tabs}<div class="listing-grid">{home_cards}</div><nav class="pager" aria-label="Collection pages">{pager}</nav></section>'
        # The marketplace has not enabled checkout or recorded completed sales.
        # Approvals and enquiries are not sales. Shop totals do not belong here.
        sales_total = 0
        available_total = '—' if unavailable else str(len(rows))
        content = f'''<main id="main" class="home"><section class="hero" aria-labelledby="hero-heading"><img class="hero-photo" src="{BASE_PATH}/assets/collector-room-1600.webp" srcset="{BASE_PATH}/assets/collector-room-800.webp 800w, {BASE_PATH}/assets/collector-room-1600.webp 1600w" sizes="100vw" alt="" width="1600" height="800" fetchpriority="high" decoding="async"><div class="hero-shade"></div>
<div class="hero-copy"><p class="eyebrow">SPORTS CAVE MARKETPLACE</p><h1 id="hero-heading">{h(config['headline'])}</h1><p class="hero-description">{h(config['description'])}</p>{search_form(hero=True)}<nav class="hero-shortcuts" aria-label="Popular collections">{shortcuts}</nav></div><p class="hero-signoff">For the love of the game.</p></section>
<section class="marketplace-facts" aria-label="Marketplace-only totals"><div><strong>{sales_total}</strong><span>Total sales</span></div><div><strong>{h(available_total)}</strong><span>Items for sale</span></div><div><strong>$0</strong><span>Founding listing fees</span></div></section>
<nav class="sports-strip section-width" aria-label="Browse by sport"><span>Follow your game</span><div>{sport_links}</div></nav>{home_collection}
<section class="buying section-width" aria-labelledby="buying-heading"><h2 id="buying-heading">Collecting. Made personal.</h2><div class="buying-columns"><div>{icon('tag')}<h3>Collector to collector</h3><p>Find a piece from someone who shares your passion.</p></div><div>{icon('chat')}<h3>Ask before you buy</h3><p>Send an enquiry while your contact details stay private.</p></div><div>{icon('review')}<h3>A considered collection</h3><p>Every listing is reviewed before it goes live.</p></div></div><a class="text-link" href="{BASE_PATH}/terms">How it works</a></section>
<section class="payment-strip section-width"><div class="payment-word">PayPal</div><div><h2>A little more confidence.</h2><p>Learn about Goods &amp; Services and eligible Buyer Protection. Marketplace checkout is coming next.</p></div><a class="text-link" href="{BASE_PATH}/buyer-protection">Buyer Protection <span aria-hidden="true">↗</span></a></section>
<section class="seller-strip section-width"><div><p class="eyebrow">MAKE ROOM FOR WHAT’S NEXT</p><h2>Your collection. A new chapter.</h2></div><a class="button gold" href="{BASE_PATH}/sell">Sell an item</a></section></main>'''
    schema = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'Organization', '@id': PUBLIC_ORIGIN + BASE_PATH + '#organisation', 'name': 'Sports Cave', 'url': SHOP_URL, 'logo': PUBLIC_ORIGIN + BASE_PATH + '/assets/logo.webp'},
        {'@type': 'WebSite', 'name': 'Sports Cave Marketplace', 'url': PUBLIC_ORIGIN + BASE_PATH},
        {'@type': 'CollectionPage', 'name': 'Sports Cave Marketplace', 'url': PUBLIC_ORIGIN + BASE_PATH + ('/browse' if catalogue_mode else ''), 'mainEntity': {'@type': 'ItemList', 'numberOfItems': len(visible), 'itemListElement': [{'@type': 'ListItem', 'position': (page - 1) * 12 + i + 1, 'url': PUBLIC_ORIGIN + listing_url(row), 'name': row['title']} for i, row in enumerate(visible)]}}]}
    if not catalogue_mode:
        schema['@graph'][1]['potentialAction'] = {'@type': 'SearchAction', 'target': {'@type': 'EntryPoint', 'urlTemplate': PUBLIC_ORIGIN + BASE_PATH + '/browse?q={search_term_string}'}, 'query-input': 'required name=search_term_string'}
    return shell(content, title='The Collection | Sports Cave Marketplace' if catalogue_mode else 'Sports Cave Marketplace | Memorabilia, Jerseys & Trading Cards', description=config['description'], path=BASE_PATH + ('/browse' if catalogue_mode else ''), schema=schema, nonce=nonce, noindex=bool(search or category or sport or sort != 'newest' or page != 1), is_home=not catalogue_mode)


def card(row):
    video = '<span class="card-video"><span aria-hidden="true">▶</span> Video</span>' if row.get('has_video') else ''
    return f'''<article class="listing-card"><a href="{listing_url(row)}"><div class="card-image"><img src="{BASE_PATH}/images/{h(row['id'])}/0.webp" alt="{h(row['title'])}" width="600" height="600" loading="lazy" decoding="async">{video}</div><div class="card-copy"><h3>{h(row['title'])}</h3><span class="card-category">{h(row['condition'])}</span><div class="card-bottom"><strong>{money(row['price_cents'])}</strong><span>{h(row['seller_name'])}</span></div></div></a></article>'''


def select(name, label, choices):
    items = choices.items() if isinstance(choices, dict) else ((v, v) for v in choices)
    return f'<label>{h(label)}<select name="{h(name)}" required><option value="">Select</option>' + ''.join(f'<option value="{h(k)}">{h(v)}</option>' for k, v in items) + '</select></label>'


def sell(config, nonce='', *, video_available=False):
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
<label class="full media-upload">Show it in motion <span class="muted">(optional)</span><input id="video" name="video" type="file" accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm" {'' if video_available else 'disabled'}><span class="hint">{'One recorded clip · MP4, MOV or WebM · up to 15 MB / 60 seconds. Show the item from every angle; describe important details in writing too.' if video_available else 'Video uploads are temporarily unavailable. You can still submit your photos.'}</span><span id="video-selection" class="hint" role="status"></span></label>
<label>Public seller name<input name="seller_name" maxlength="70" autocomplete="name" required></label>{select('seller_type', 'Seller type', ('Private collector', 'Business seller'))}
<label>Your email <span class="muted">(private)</span><input name="seller_email" type="email" maxlength="254" autocomplete="email" required></label>
<label>Suburb / state<input name="location" maxlength="80" placeholder="Brisbane, QLD" required></label></div>
<label class="trap" aria-hidden="true">Website<input name="website" tabindex="-1" autocomplete="off"></label>
<label class="consent"><input name="consent" type="checkbox" required><span>I own this item and have permission to share its photos and video. My listing is accurate and I agree to the <a href="{BASE_PATH}/terms" target="_blank" rel="noopener">submission terms and privacy notice</a>.</span></label>
<div class="form-submit"><button class="button gold" type="submit">Submit for review</button><p class="form-status" role="status" aria-live="polite"></p></div></form><noscript><p>Enable JavaScript to submit your item photographs.</p></noscript></main>'''
    return shell(form, title='Sell Your Memorabilia, Jerseys & Cards | Sports Cave Marketplace',
                 description='Submit your sporting collection to Sports Cave Marketplace. Free founding listings, reviewed before publication.', path=BASE_PATH + '/sell', nonce=nonce)


def item(row, nonce='', *, demo=False):
    row = public_listing(row)
    item_id = h(row['id'])
    item_path = BASE_PATH + '/demo' if demo else listing_url(row)
    def image_url(index):
        return f'{BASE_PATH}/assets/demo-{"jersey" if index == 0 else "detail"}.svg' if demo else f'{BASE_PATH}/images/{item_id}/{index}.webp'
    photo_url = image_url(0)
    panels, thumbnails = [], []
    for index in range(row['photo_count']):
        url = image_url(index)
        panels.append(f'<figure class="media-panel" id="media-photo-{index}" data-media-panel><img src="{url}" alt="{h(row["title"])} — photo {index + 1}" width="960" height="1200" {"loading=lazy" if index else "fetchpriority=high"} decoding="async"></figure>')
        thumbnails.append(f'<a class="media-thumb" href="#media-photo-{index}" data-media-target="media-photo-{index}" aria-label="View photo {index + 1}" {"aria-current=true" if not index else ""}><img src="{url}" alt="" width="72" height="90" loading="lazy"></a>')
    if row.get('has_video'):
        panels.append(f'<figure class="media-panel video-panel" id="media-video" data-media-panel><video controls playsinline preload="none" poster="{photo_url}" aria-label="Recorded item video supplied by {h(row["seller_name"])}"><source src="{BASE_PATH}/videos/{item_id}/item.mp4" type="video/mp4"><p>Your browser cannot play this video. Please use the item photos and description.</p></video><figcaption>Recorded by the seller · See the written description for item details.</figcaption></figure>')
        thumbnails.append(f'<a class="media-thumb video-thumb" href="#media-video" data-media-target="media-video" aria-label="Watch recorded item video"><span aria-hidden="true">▶</span><small>Video</small></a>')
    provenance = '<h2>Provenance</h2><p class="item-description">' + h(row['provenance']) + '</p>' if row.get('provenance') else ''
    content = f'''<main id="main" class="item collector-item"><a class="back" href="{BASE_PATH}#finds">Back to the collection</a><div class="item-layout">
<section class="item-media" aria-label="Item photos and video"><div class="gallery" data-gallery><div class="media-stage">{''.join(panels)}</div><nav class="media-thumbs" aria-label="Choose an item photo or video">{''.join(thumbnails)}</nav><p class="gallery-caption"><span data-media-caption aria-live="polite">Photo 1 of {row['photo_count']}</span><span>Seller-supplied media</span></p></div></section>
<section class="item-details"><p class="eyebrow">{'DEMO LISTING · NOT FOR SALE' if demo else 'FROM ONE COLLECTION TO THE NEXT'}</p><h1>{h(row['title'])}</h1><div class="item-tags"><span>{h(row['condition'])}</span><span>{h(row['location'])}</span></div><p class="price">{money(row['price_cents'])}<span>AUD</span></p><p class="postage-line">{money(row['shipping_cents'])} tracked postage · {'Example price' if demo else 'Asking price'}</p>
<div class="seller-profile"><span class="seller-avatar" aria-hidden="true">{h(row['seller_name'][:1].upper())}</span><div><strong>{h(row['seller_name'])}</strong><span>{h(row['seller_type'])}</span></div></div>
<div class="product-actions"><a class="button dark" href="{BASE_PATH}/contact/{item_id}?intent=message">{icon('chat')} Message seller</a><a class="button outline" href="{BASE_PATH}/contact/{item_id}?intent=offer">Make offer</a></div><p class="item-note">Create an account or sign in to message and make an offer. {'This example cannot receive messages or payments.' if demo else 'Your email stays private.'}</p>
<a class="item-protection" href="{BASE_PATH}/buyer-protection">{icon('review')}<span><strong>Know your Buyer Protection</strong><small>PayPal eligibility, payment tips and what to check.</small></span><span aria-hidden="true">↗</span></a>
<div class="item-story"><h2>About this piece</h2><p class="item-description">{h(row['description'])}</p>{provenance}<dl><div><dt>Item type</dt><dd>{h(CATEGORIES[row['category']])}</dd></div><div><dt>Sport</dt><dd>{h(row['sport'])}</dd></div></dl></div>
<p class="item-note">Seller-supplied details. Listing review is not independent authentication. <a href="mailto:hello@sportscaveshop.com?subject=Marketplace%20item%20{item_id}">Report this item</a></p></section></div></main>'''
    condition = {'New / unused': 'NewCondition', 'Excellent': 'UsedCondition', 'Good': 'UsedCondition', 'Fair': 'UsedCondition'}[row['condition']]
    product = {'@type': 'Product', 'name': row['title'], 'description': row['description'], 'sku': row['id'],
         'image': [PUBLIC_ORIGIN + image_url(i) for i in range(row['photo_count'])],
         'itemCondition': 'https://schema.org/' + condition, 'category': CATEGORIES[row['category']],
         'offers': {'@type': 'Offer', 'price': f'{row["price_cents"] / 100:.2f}', 'priceCurrency': 'AUD',
                    'availability': 'https://schema.org/InStock', 'url': PUBLIC_ORIGIN + item_path,
                    'seller': {'@type': 'Organization' if row['seller_type'] == 'Business seller' else 'Person', 'name': row['seller_name']}}}
    if demo:
        product.pop('offers', None)
    if row.get('has_video') and row.get('published_at'):
        product['subjectOf'] = {'@type': 'VideoObject', 'name': row['title'] + ' — item video',
            'description': 'Seller-recorded item showcase. ' + row['description'][:160],
            'thumbnailUrl': PUBLIC_ORIGIN + photo_url, 'uploadDate': row['published_at'],
            'contentUrl': PUBLIC_ORIGIN + BASE_PATH + f'/videos/{row["id"]}/item.mp4',
            'duration': f'PT{row.get("video_seconds", 0)}S'}
    schema = {'@context': 'https://schema.org', '@graph': [product,
        {'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Marketplace', 'item': PUBLIC_ORIGIN + BASE_PATH},
            {'@type': 'ListItem', 'position': 2, 'name': row['title'], 'item': PUBLIC_ORIGIN + item_path}]}]}
    return shell(content, title=row['title'] + ' | Sports Cave Marketplace', description=row['description'][:160], path=item_path, schema=schema, nonce=nonce, noindex=demo)


def payment_page(protection=False, nonce=''):
    policy = 'https://www.paypal.com/au/legalhub/paypal/buyer-protection'
    overview = 'https://www.paypal.com/au/digital-wallet/buyer-purchase-protection'
    if protection:
        path, title, headline = '/buyer-protection', 'Buyer Protection', 'Confidence starts with the details.'
        lead = 'Know the piece. Know the seller. Know how you pay.'
        body = f'''<section class="protection-grid" aria-label="Buying with confidence"><article><span class="step-number">01</span><h2>Look a little closer.</h2><p>Check photos, video, condition and provenance. Ask for anything missing before agreeing to buy.</p></article><article><span class="step-number">02</span><h2>Choose Goods &amp; Services.</h2><p>Eligible payments from your PayPal account may qualify for Buyer Protection. Friends &amp; Family payments are excluded.</p><a href="{BASE_PATH}/paypal">About PayPal ↗</a></article><article><span class="step-number">03</span><h2>Keep a record.</h2><p>Save the listing, messages, receipt and tracked delivery details. Listing approval does not authenticate an item.</p></article></section>
<section class="protection-detail"><div><p class="eyebrow">IF SOMETHING GOES WRONG</p><h2>A clear next step.</h2><p>Contact the seller first. If unresolved, open a dispute in <a href="https://www.paypal.com/disputes/">PayPal’s Resolution Centre</a>. Sports Cave can help with marketplace records; PayPal decides eligibility and claims.</p><a class="text-link" href="mailto:hello@sportscaveshop.com">Contact Sports Cave</a></div><div class="protection-faq"><details><summary>What may be covered?</summary><p>Eligible purchases that do not arrive or are significantly different from their description may qualify for the price paid and original postage. Coverage is conditional. <a href="{overview}">PayPal’s overview ↗</a></p></details><details><summary>What should I check first?</summary><p>Australian eligibility includes payments below A$20,000. Resale purchases are excluded; collection in person and custom-made items have limits. Check <a href="{policy}">PayPal’s full terms</a> before paying.</p></details><details><summary>How long do I have?</summary><p>For non-delivery, open a dispute within 180 days of payment. For a significant mismatch, the earlier of 30 days after delivery or 180 days after payment applies. Escalate an unresolved dispute within 20 days of opening it. <a href="{policy}">Check current deadlines ↗</a></p></details><details><summary>Should I return the item?</summary><p>Follow PayPal’s instructions and keep proof of return. Return postage is generally your cost. <a href="{policy}">Read claim requirements ↗</a></p></details></div></section>'''
    else:
        path, title, headline = '/paypal', 'PayPal', 'A familiar way to pay.'
        lead = 'Goods & Services. Clear records. A more considered purchase.'
        body = f'''<section class="paypal-intro"><div><p class="eyebrow">PAY THE SELLER ON PAYPAL</p><h2>Agree it here. Pay on PayPal.</h2><p>Message the seller and agree the total. The seller can share an invoice from their own PayPal Business account in your private conversation. Open it to check the recipient, item and amount, then pay on PayPal.</p><a class="button dark" href="{BASE_PATH}/inbox">Your messages</a></div><aside><span class="payment-word">PayPal</span><h2>Goods &amp; Services</h2><p>Pay from your PayPal account for eligible purchases. Buyer Protection may apply if an item does not arrive or is significantly different from its description.</p><a class="text-link" href="{BASE_PATH}/buyer-protection">Explore Buyer Protection ↗</a></aside></section>
<section class="payment-checklist"><h2>Before you pay.</h2><div><p><strong>Agree the details.</strong> Confirm the actual item, condition, total price and tracked postage with the seller.</p><p><strong>Check the payment.</strong> Use Goods &amp; Services from your PayPal account. Friends &amp; Family is excluded from Buyer Protection.</p><p><strong>Keep everything.</strong> Save the listing, messages and payment receipt. Read <a href="{policy}">PayPal’s Australian terms</a> for eligibility, exclusions and deadlines.</p></div></section><p class="payment-footnote">PayPal is a separate payment provider. Sports Cave does not guarantee a refund or decide PayPal claims. <a href="{overview}">Read PayPal’s protection overview ↗</a></p>'''
    content = f'''<main id="main" class="payment-page"><section class="protection-hero"><div class="section-width"><a class="back" href="{BASE_PATH}">Marketplace</a><p class="eyebrow">SPORTS CAVE · {h(title.upper())}</p><h1>{headline}</h1><p>{lead}</p><nav aria-label="Payment information"><a href="{BASE_PATH}/paypal" {'aria-current="page"' if not protection else ''}>PayPal</a><a href="{BASE_PATH}/buyer-protection" {'aria-current="page"' if protection else ''}>Buyer Protection</a></nav></div></section><div class="section-width payment-content"><p class="payment-status">Seller-provided invoice links open on PayPal. This website does not collect payments or verify payment status.</p>{body}</div></main>'''
    return shell(content, title=title + ' | Sports Cave Marketplace', description='PayPal Goods & Services, eligible Buyer Protection and safer buying on Sports Cave Marketplace.', path=BASE_PATH + path, nonce=nonce)


def terms(nonce=''):
    content = f'''<main id="main" class="narrow legal"><a class="back" href="{BASE_PATH}">Marketplace</a><p class="eyebrow">FOUNDING SELLER LAUNCH</p><h1>Good pieces. Clear expectations.</h1>
<h2>List your own collection</h2><p>Submit sporting memorabilia, jerseys or trading cards you own and are entitled to sell. Use current photographs of the actual item, describe flaws and provide evidence for signatures, grading or match-worn claims. Counterfeits and misleading listings are not accepted. Sports Cave may decline or remove a listing.</p>
<h2>Review, then publish</h2><p>Submissions are private until Sports Cave approves them. Your seller name, seller type, suburb / state, asking price, postage, item description, provenance and uploaded photos and video appear publicly. Listing review does not authenticate an item or guarantee seller claims. Sellers remain responsible for accurate details. Private collectors and business sellers are identified separately.</p>
<h2 id="fees">Free founding listings</h2><p>There is no submission or listing charge for this launch. The planned seller fee is 5% of the item price on a completed on-platform sale. Any payout illustration is indicative. Commission collection is not active. Sellers may share invoices from their own PayPal Business accounts; buyers pay the seller on PayPal. Check the actual recipient, item and total there. This website does not collect payments, verify payment status, reserve items or pay sellers. Accepting an offer does not process a payment.</p>
<h2>Your account &amp; conversations</h2><p>Create an account and confirm your email before messaging a seller or making an offer. Use the same verified email as your seller submission to receive its conversations. Your display name is shared with the other participant; your email and password are not. Keep messages relevant and do not share passwords, financial credentials or unnecessary personal details. You can block or report a conversation. Sports Cave may suspend marketplace access for misuse.</p>
<h2>Your information</h2><p>Sports Cave stores your account, submissions, messages, offers and invoice links to operate the marketplace and review reports. Only the buyer, seller and authorised Sports Cave administrators can access their conversation. Support can review messages; messaging is not end-to-end encrypted. Account authentication is provided by Supabase. We do not add you to a marketing list through these forms. Avoid personal details in public descriptions, photos and video; uploaded media metadata is removed. Recorded videos stay private until the listing is approved.</p>
<h2>Need a hand?</h2><p>To correct or remove a listing, request access to or deletion of your information, or report an item, contact <a href="mailto:hello@sportscaveshop.com">hello@sportscaveshop.com</a>. Include your listing reference. These launch terms do not exclude rights available under applicable law.</p></main>'''
    return shell(content, title='How It Works & Privacy | Sports Cave Marketplace', description='Founding seller submissions, review, fees and privacy at Sports Cave Marketplace.', path=BASE_PATH + '/terms', nonce=nonce)
