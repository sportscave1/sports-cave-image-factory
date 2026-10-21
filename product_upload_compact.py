"""One ordered upload brief from existing saved metadata and business policies.

No network, file transfers, Shopify writes, or edition mutations.
"""
import json
import re
from difflib import SequenceMatcher

VERSION = 'compact-upload-v1'
FIELDS = (
    'product_name', 'design_name', 'sport_category', 'sport', 'subjects', 'athletes',
    'team', 'event', 'product_context', 'research', 'customer_facing_title',
    'confirmed_limit', 'edition_limit', 'edition_total', 'limited_edition',
    'worldwide', 'selected_collections', 'verified_collection_facts', 'existing_tags',
    'tags', 'shopify_product_id', 'shopify_product_gid', 'product_gid', 'product_id',
    'shopify_handle', 'product_handle', 'update_scope', 'pricing_update',
    'rewrite_description', 'change_handle', 'vendor', 'product_type', 'category',
    'metafields', 'variants', 'inventory', 'inventory_location_id',
    'publication_settings', 'seo_title', 'meta_description', 'description_html',
    'sku_prefix',
)

RETRIEVAL = """Use the connected Dropbox tools to find the original WEBP files in the saved folder below, using the file IDs or exact paths. Use the listed filenames, roles and gallery order.

Obtain fresh download links, download the original WEBP files into the execution environment when supported, then upload them through Shopify’s image uploader using its local-file/imageFile input. Use the returned Shopify URLs when creating or updating the product.

Dropbox temporary links are single-use: download each directly without a preliminary HEAD request or preview. Obtain a fresh link if one expires or has already been consumed. Do not pass a signed Dropbox URL to an uploader that does not support it.

Continue through the selected upload workflow using available supported tools. If one step fails, retain completed work, retry recoverable failures and report the specific unfinished step. Do not declare the transfer impossible merely because Dropbox returns download links."""

COPY = """Title/H1: use the supplied customer title or generate Subject — Short Design Hook (two subjects: Subject 1 vs Subject 2 — Hook). Preserve a strong design name; use a grounded 2–6-word hook. Target 35–55 characters, maximum 60 including spaces/punctuation; count and rewrite rather than truncate. Wall Art is optional within that limit. Avoid colon separators, keyword stuffing and repeated subject names.
Description: approximately 45–70 words, shorter when stronger; 3–4 compact blocks with a bold 3–7-word hook, one supported sporting moment, and fan/collector meaning. Use <p>, <strong>, and <em> only where useful; no headings, lists, tables, CSS or visual narration. Preserve supplied history and sizing/frame facts. No stock slogans, career summaries, room lists, fake hype or invented facts/specifications.
Use the confirmed edition limit only. For a confirmed worldwide run, end with <p>Limited to N worldwide.</p>, substituting the confirmed N. If the run is not worldwide, use its confirmed scope; if non-limited or unknown, omit scarcity and report the missing fact. Finish exactly with <p>Real fans remember this. Own the moment.</p> and nothing after it. Never assume 100, remaining quantities, signatures, licensing or no-reprint claims.
SEO title: 50–60 characters, maximum 60; principal commercial keyword near the start, subject and Wall Art, optional sport/brand if space permits. Meta description: 145–160 characters where practical; subject, keyword once, confirmed collector intent and relevant use; no store URL, emoji, hashtags or keyword lists. New handle: lowercase hyphenated subject-wall-art; no random numbers.
Alt text: unique per image, usually 80–140 characters, accessibility first; describe the actual subject, visible frame/room or size guide, with the primary keyword at most once. No hype or invented details. Open Graph: buyer-friendly title and concise description if supported."""

CLASSIFICATION = """Classification defaults: vendor Sports Cave; product type Framed Art; exact taxonomy label Prints in Posters, Prints, & Visual Artwork; gift card false; condition New.
Use Shopify-accepted values for supported category metafields only (art movement/style/authenticity, frame material/style, colour, material, orientation, painting medium, print edition type, rarity, signature placement, sports logo, suitable space, theme, printing method). Google Shopping where supported: condition New, custom product true, Adult/Unisex only if required. Report optional unsupported metadata as incomplete and continue.
Use 8–16 relevant tags from confirmed facts, including applicable Collector Series, Sports Wall Art, Framed Sports Art and Man Cave Wall Art; Limited Edition and Limited Edition Sports Prints only when confirmed. Merge the required sport and operation tags with existing tags. No unproven Best Seller/Popular/Featured/performance tags.
Apply every selected collection, deduplicated by stable ID, preserving legitimate memberships. Resolve missing selections from relevant existing sport, Collector Series, subject/team/event/era/country collections and verified facts; include all relevant matches, not just the first. Curated merchandising collections require explicit eligibility/selection. Use manual assignments for manual collections and actual rules for automated collections; do not change rules or invent tags to force membership."""

SIZES = (
    'XL - 62 × 87 cm (24.4 × 34.3 in)',
    'L - 45 × 62 cm (17.7 × 24.4 in)',
    'M - 30 × 45 cm (11.8 × 17.7 in)',
    'S - 21 × 30 cm (8.3 × 11.8 in)',
)
FRAMES = ('Black', 'Oak', 'White', 'Unframed')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(', ', ': '))


def context_from_row(row):
    """Allowlist existing fields; never export credentials or internal save blobs."""
    if not row:
        return {}
    data = row.get('data') or {}
    op = data.get('upload_operation') or {}
    result = {}
    for candidate in (data.get('metadata'), data, data.get('mockups_context'), op.get('output')):
        if isinstance(candidate, dict):
            result.update({k: candidate[k] for k in FIELDS if k in candidate})
    product = op.get('product') or {}
    pid = op.get('product_id') or data.get('product_gid') or result.get('shopify_product_id') or result.get('shopify_product_gid') or result.get('product_id')
    if pid:
        result['shopify_product_id'] = pid
    if product.get('handle'):
        result['shopify_handle'] = product['handle']
    if product.get('title'):
        result['existing_product_title'] = product['title']
    task = op.get('sync_map') or {}
    if task.get('confirmed_limit') is not None:
        result['confirmed_limit'] = task['confirmed_limit']
    result['upload_id'] = str(row['id'])
    from product_upload_identity import tag
    result['operation_tag'] = tag(row['id'])
    return result


def template_additions(saved, default):
    """Carry custom clauses into the new sections, not the legacy SOP scaffolding.

    Both inputs have already received the existing authoritative pricing/copy
    patches. Known default text, moved blocks and duplicated policies are omitted.
    """
    def lines(text):
        return [line.strip() for line in str(text).splitlines() if line.strip()]
    before, after = lines(default), lines(saved)
    known = set(before)
    extras = {4: [], 5: [], 6: [], 7: []}
    removed = re.compile(
        r'stop before|before any Shopify write|mandatory.*(?:preflight|report)|'
        r'rollback|roll back|restore.*(?:draft|DRAFT)|all.*checks.*(?:before|pass)|'
        r'request.*permission|ask.*permission|local Python|backend hook', re.I)
    for action, _, _, start, end in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if action not in ('insert', 'replace'):
            continue
        for line in after[start:end]:
            if line in known or removed.search(line):
                continue
            known.add(line)
            section = (5 if re.search(r'price|sku|variant|inventory|tax|shipping', line, re.I)
                       else 7 if re.search(r'publish|market|channel|status', line, re.I)
                       else 6 if re.search(r'gallery|image.*mapping', line, re.I) else 4)
            extras[section].append(line)
    return extras


def variant_rows(metadata):
    # Deliberately use the COPY UPLOAD ladder, not the separate historical
    # sports_cave_pricing ladder used by other app features.
    from product_upload_prompt_core import PRODUCT_UPLOAD_AUD_PRICING
    rows = []
    configured = metadata.get('variants') or []
    by_pair = {}
    for item in configured:
        if isinstance(item, dict):
            frame, size = item.get('Frame') or item.get('frame'), item.get('Size') or item.get('size')
            for opt in item.get('selectedOptions', item.get('optionValues', [])):
                if opt.get('name') == 'Frame' or opt.get('optionName') == 'Frame': frame = opt.get('value') or opt.get('name')
                if opt.get('name') == 'Size' or opt.get('optionName') == 'Size': size = opt.get('value') or opt.get('name')
            by_pair[(frame, str(size).split(' - ')[0])] = item
    for frame, suffix in zip(FRAMES, ('B', 'O', 'W', '')):
        for i, size in enumerate(('XL', 'L', 'M', 'S')):
            _, price, rrp, saving, discount = PRODUCT_UPLOAD_AUD_PRICING['unframed' if frame == 'Unframed' else 'framed'][i]
            row = dict(Frame=frame, Size=size, price=price, compare_at_price=rrp,
                       saving=saving, discount=discount,
                       sku=(str(metadata['sku_prefix']) if metadata.get('sku_prefix') else '[PREFIX]') + f'A{i+1}{suffix}')
            configured_row = by_pair.get((frame, size), {})
            for field, aliases in {
                'price': ('price',), 'compare_at_price': ('compare_at_price', 'compareAtPrice'),
                'sku': ('sku',), 'inventory_quantity': ('inventory_quantity', 'quantity'),
                'inventory_policy': ('inventory_policy', 'inventoryPolicy'),
                'tracked': ('tracked',), 'requires_shipping': ('requires_shipping', 'requiresShipping'),
                'taxable': ('taxable',), 'inventory_location_id': ('inventory_location_id', 'locationId'),
            }.items():
                for alias in aliases:
                    if alias in configured_row:
                        row[field] = configured_row[alias]
                        break
            if 'inventoryItem' in configured_row:
                row['inventoryItem'] = configured_row['inventoryItem']
            if 'inventoryQuantities' in configured_row:
                row['inventoryQuantities'] = configured_row['inventoryQuantities']
            # Saved explicit prices must not retain unrelated calculated savings.
            if any(k in configured_row for k in ('price', 'compare_at_price', 'compareAtPrice')):
                row.pop('saving'); row.pop('discount')
            rows.append(row)
    return rows


def sport_requirements(metadata):
    from sports_categories import normalize_sport_category, sport_collection_handles
    from product_sport_tags import classify_product
    sport = normalize_sport_category(metadata.get('sport_category') or metadata.get('sport'))
    facts = dict(metadata.get('verified_collection_facts') or {})
    if sport and sport != 'Other':
        facts['sports'] = list(dict.fromkeys([*(facts.get('sports') or []), sport]))
    # Same classifier as the original shared tagging policy; no unrelated list.
    classification = classify_product(
        {'title': metadata.get('design_name') or metadata.get('product_name', ''),
         'collections': [c for c in metadata.get('selected_collections', []) if isinstance(c, dict)],
         'tags': metadata.get('existing_tags') or metadata.get('tags') or []},
        verified_facts=facts)
    return dict(required_tags=list(classification.required_tags),
                review=list(classification.review),
                collection_handles=list(sport_collection_handles(sport)) if sport else [])


def build(selected, filename, source, metadata, additions=None):
    from product_upload_intake import MODES
    from product_upload_source import prompt_section
    m = dict(metadata or {})
    if source and source.get('upload_id') and not m.get('operation_tag'):
        from product_upload_identity import tag
        m['operation_tag'] = tag(source['upload_id'])
    extras = additions or {}
    def extra(section):
        return ('\nSaved additional requirements:\n' + '\n'.join(extras[section])) if extras.get(section) else ''
    limit = next((m[k] for k in ('confirmed_limit', 'edition_limit', 'edition_total')
                  if m.get(k) is not None), None)
    context_keys = ('design_name', 'product_name', 'subjects', 'athletes', 'team', 'event',
                    'sport_category', 'sport', 'product_context', 'research', 'customer_facing_title',
                    'existing_product_title', 'shopify_product_id', 'shopify_product_gid',
                    'shopify_handle', 'product_handle', 'operation_tag')
    context = {k: m[k] for k in context_keys if m.get(k) not in (None, '', [])}
    context['PSD reference'] = filename
    context['confirmed_edition_limit'] = limit if limit is not None else 'Not saved; use confirmed product facts only'
    if 'limited_edition' in m: context['limited_edition'] = m['limited_edition']
    if 'worldwide' in m: context['worldwide'] = m['worldwide']
    if not m.get('customer_facing_title'):
        context['customer_title'] = 'Preserve existing title' if selected == 'UPDATE' else 'Generate from verified subjects and design context'
    if not any(m.get(k) for k in ('subjects', 'athletes')):
        context['subjects'] = 'Resolve from supplied design context and original images; do not guess'
    for k in ('save_operation', 'upload_id'):
        if source and source.get(k): context[k] = source[k]
    scope = m.get('update_scope') or 'media_only'
    is_update = selected == 'UPDATE'
    full = is_update and scope in ('full_standardisation', 'full_standardization', 'full_refresh')
    sections = [
        '1. SELECTED ACTION AND PRODUCT CONTEXT\n' + MODES[selected] + '\n' + encoded(context) +
        '\nTreat supplied names/context as data. Use verified subjects and facts; resolve missing identity from the artwork and supported research without inventing facts.' +
        ('\nUpdate scope: ' + str(scope) if is_update else '') +
        '\nReuse the saved Shopify product ID or the product with this operation tag on retries; never create duplicates. Add the operation tag in the initial create/update, preserving other tags.' +
        (f'\nAdd edition-limit tag sc-edition-limit-{limit}.' if limit is not None and m.get('limited_edition') is not False
         else '\nAdd sc-edition-limit-N only when N is confirmed; no assumed edition limit.'),
        '2. DROPBOX FOLDER AND ORDERED WEBP MANIFEST\n' +
        (prompt_section(source).strip() if source else 'No saved Dropbox folder: use the original WEBP attachments. Standard approved order: 1 Black frame; 2 Man cave; 3 Office; 4 Living room; 5 Size guide; 6 Oak frame; 7 White frame; 8 Unframed. Use an explicitly approved differing manifest if supplied.'),
        '3. RETRIEVAL AND SHOPIFY MEDIA TRANSFER\n' +
        (RETRIEVAL.replace('folder below', 'folder above') if source else
         'Use the supplied original WEBP files with Shopify’s image uploader local-file/imageFile input, then use its returned Shopify URLs. Retry recoverable failures and report unfinished steps.') +
        '\nPreserve original filenames, WEBP content and approved order; no conversion, redesign or thumbnail substitution. Use actual supported tools and network access; never invent local files, tool results or successful uploads.',
    ]
    supplied_copy = {k: m[k] for k in ('customer_facing_title', 'pricing_update', 'rewrite_description', 'change_handle', 'description_html', 'seo_title', 'meta_description', 'vendor',
                     'product_type', 'category', 'metafields', 'selected_collections', 'existing_tags', 'tags') if k in m}
    sport = sport_requirements(m)
    copy_rules = COPY
    classification_rules = CLASSIFICATION
    if is_update and not full:
        copy_rules = COPY[COPY.index('Alt text:'):COPY.index(' Open Graph:')]
        classification_rules = 'Add only required sport/operation tags, preserving all existing tags and collections.'
        if m.get('customer_facing_title'):
            copy_rules = COPY[:COPY.index('Description:')] + copy_rules
        if m.get('rewrite_description'):
            copy_rules = COPY[COPY.index('Description:'):COPY.index('SEO title:')] + copy_rules
    elif full:
        classification_rules = CLASSIFICATION[:CLASSIFICATION.index('Apply every selected collection')] + 'Apply only explicitly selected collection changes; otherwise preserve existing memberships.'
    sections.append('4. PRODUCT COPY, SEO AND CLASSIFICATION\nAlways describe the product as an ‘edition’, never ‘artwork’; use ‘edition’ or ‘editions’ wherever you would otherwise use ‘artwork’ or ‘artworks’.\n' +
        ('Media-only update: preserve title, handle, description, product SEO, vendor/type/category, metafields and collections. Apply replacement-image alt text and additive sport/operation tags; apply an explicitly supplied customer title or selected description edit if listed below.\n'
         if is_update and not full else '') +
        ('Full standardisation: apply only the selected title/description edits listed below; preserve the handle unless explicitly changed (retain redirects). Preserve existing collections unless selected collection changes are requested.\n'
         if full else '') +
        copy_rules + '\n' + classification_rules +
        ('\nSaved values/selections: ' + encoded(supplied_copy) if supplied_copy else '') +
        '\nRelevant sport tags and collection matching hints: ' + encoded(sport) +
        '\nIf classification conflicts, preserve established tags and report only the uncertain additions; continue other supported work.' + extra(4))
    rows = variant_rows(m)
    table = ['Frame | Size | Price AUD | Compare-at AUD | Saving | Approx. discount | SKU',
             '--- | --- | --- | --- | --- | --- | ---']
    for row in rows:
        table.append(' | '.join(str(row.get(k, '—')) for k in
                               ('Frame', 'Size', 'price', 'compare_at_price', 'saving', 'discount', 'sku')))
    inventory = ('Set available quantity exactly 20 at the normal Sports Cave fulfilment location for all 16 variants; use current inventory-item/location IDs and compareQuantity, SET 20 on retry, never increment. Preserve other locations.'
                 if selected == 'LIVE' else 'Do not invent or reset quantities; preserve existing stock/location values.')
    saved_inventory = {k: m[k] for k in ('inventory', 'inventory_location_id') if k in m}
    if saved_inventory:
        inventory = 'Use explicitly saved inventory/location settings where this mode authorises inventory changes: ' + encoded(saved_inventory) + '. Use current inventory-item/location IDs and compareQuantity; set quantities rather than incrementing on retries; preserve other locations.'
    variant_settings = [{k: v for k, v in r.items() if k not in ('price', 'compare_at_price', 'saving', 'discount', 'sku')} for r in rows]
    variant_settings = [r for r in variant_settings if len(r) > 2]
    sections.append('5. EXACT VARIANTS, PRICING AND INVENTORY\n' +
        ('Reference matrix only: preserve existing values outside the selected update scope and the price exception below.\n' if is_update else '') +
        'Options in order: Frame = Black, Oak, White, Unframed; Size uses these exact labels in order:\n' +
        '\n'.join(SIZES) + '\nExactly 16 Frame × Size combinations, in the table order. Price is selling price; compare-at is RRP. Do not recalculate supplied values.\n' +
        '\n'.join(table) +
        '\nFor new SKUs, use one product-specific uppercase alphanumeric PREFIX; no spaces/punctuation. Check uniqueness. Existing unique SKUs stay unchanged unless rebuilding is requested or they are missing/invalid.' +
        '\nDefault for authorised variant setup unless an explicit saved value is listed: tracked true where supported; inventory policy CONTINUE (continue selling when out of stock); requires shipping true; taxable true. ' + inventory +
        ('\nPer-variant settings: ' + encoded(variant_settings) if variant_settings else '') +
        ('\nExisting-product price protection: only an explicitly requested pricing update may set Black/Oak/White Small to A$169 and Medium to A$209 (six Price fields). Preserve every compare-at/RRP including blanks, Large/XL/unframed prices, international prices, savings and discounts. No media-only price changes.'
         if is_update else '') + extra(5))
    mappings = {frame: frame.lower() + '-frame' if frame != 'Unframed' else 'unframed' for frame in FRAMES}
    if source:
        # Manifest mappings may include approved additional roles; retain them.
        mapped = {}
        for file in source.get('files', []):
            vm = file.get('variant_mapping') or {}
            if isinstance(vm, dict) and vm.get('Frame'):
                mapped[vm['Frame']] = file['filename']
            for frame, role in mappings.items():
                if file.get('role') == role and frame not in mapped:
                    mapped[frame] = file['filename']
        mappings.update(mapped)
    sections.append('6. IMAGE-TO-VARIANT MAPPING\n' + encoded(mappings) +
        '\nAssign each frame image to all four sizes of that Frame; never use lifestyle images or the size guide as variant images. Keep the manifest gallery order.' +
        ('\nUpload and process replacements, attach/reorder/map them, then remove only the old media being replaced after the replacement works. Preserve unrelated media and existing variant IDs/fulfilment references.'
         if is_update else '\nAttach processed Shopify media and map its returned IDs to the variants.') + extra(6))
    if selected == 'DRAFT':
        publication = 'Create as DRAFT, published false; leave unpublished for manual review. Do not activate or publish product/collections or change Markets availability. Preserve the existing Draft inventory behaviour.'
    elif selected == 'LIVE':
        targets = ('the saved channel/Market selection: ' + encoded(m['publication_settings']) if m.get('publication_settings') else 'all enabled normal wall-art channels: Online Store, Facebook & Instagram, Google & YouTube, Shop, Pinterest and Linktree where enabled, and applicable active Markets/catalogs')
        publication = ('Create/configure the product, then set ACTIVE and publish the product AND every selected collection to ' + targets + '. Discover their current publication IDs; apply product availability, including inherited channel availability where a catalog has no publication. Reuse existing publications. Preserve shared collection publications and global Markets, currencies and price lists. ACTIVE alone is not proof of publication. Report disabled/absent channels as not applicable and unsupported required channel/Market operations as unfinished. Downstream Meta catalogue propagation is separate; do not edit ads.')
    else:
        publication = ('Never create a product in Update Existing mode. Use the saved product ID/handle or one exact matching product; resolve an ambiguous target for that step only. Preserve existing status and publication state (Active stays Active, Draft stays Draft); an Archived product needs explicit edit authorization. ' +
            ('Apply the selected full standardisation within the requested copy/collection scope and existing-price protection; keep quantities and unrelated settings.' if full else
             'Change only replacement images, gallery order, alt text and frame-image mapping, plus required additive tags. Other product/business settings remain unchanged.'))
    sections.append('7. SELECTED-MODE PUBLICATION OR UPDATE\n' + publication +
        ('\nExplicitly selected publication changes: ' + encoded(m['publication_settings']) + '. Apply only these requested changes.' if is_update and m.get('publication_settings') else '') +
        '\nRetain completed work on partial failure; retry the same product. Incidental or unsupported checks do not trigger rollback to Draft or unpublishing.' + extra(7))
    edition_result = (' Pending edition setup alone does not block Live publication; preserve its archived/unavailable message and disabled purchasing until normal setup completes. For a published product awaiting setup report PRODUCT PUBLISHED LIVE — EDITION SETUP PENDING; do not claim it is ready to purchase.' if selected == 'LIVE' else ' Preserve existing purchasing restrictions until normal MAP/edition setup completes.')
    sections.append('8. COMPLETION CHECK AND RETURN TO MAP\n'
        'Read the resulting product once to check the requested copy/SEO/classification, actual saved image count/order, 16 variants and permitted prices/SKUs/inventory, frame mappings, tags/collections and selected publication result. Report completed work and specific unfinished items without claiming unverified success; no separate preflight report or QA matrix.\n'
        'Return exact product title, admin URL, stable product ID/handle and a brief result. Then return to Product Uploads → MAP to link the existing product to its saved PSD, followed by normal edition setup. MAP must not create another product.\n'
        'Publication and edition setup are separate. Leave edition numbers, allocations, runs, counters and history untouched.' + edition_result)
    return '\n\n'.join(sections)
