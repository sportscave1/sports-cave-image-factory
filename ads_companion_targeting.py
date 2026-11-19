"""Deterministic queue targeting by sport, independent of featured-item membership."""
import re
from urllib.parse import urlsplit

from ads_target_relevance import rank_relevant_meta_options, tokens, extract_relevance_terms


class CatalogPending(ValueError):
    """Catalogue data is not available yet; retain the generated package for retry."""


FORMULA_ONE_PRODUCT_SET = 'FORMULA 1 WALL ART POPULAR'
NBA_PRODUCT_SET = 'NBA WALL ART POPULAR BLACK FRAMES'


def contains_product(products, result):
    pid = str(result.get('product_id') or '').rsplit('/', 1)[-1]
    expected = urlsplit(result['product_url'])
    hosts = {'sportscave.com.au', 'sportscaveshop.com'}
    for product in products:
        retailer = str(product.get('retailer_id') or '')
        exact = pid.isdigit() and (retailer == pid or re.fullmatch(r'shopify_[A-Z]{2}_'+re.escape(pid)+r'_\d+', retailer))
        url = urlsplit(str(product.get('url') or ''))
        link = (url.hostname or '').removeprefix('www.') in hosts and url.path.rstrip('/') == expected.path.rstrip('/')
        if exact or link:
            return True
    return False


def select(refs, result, *, client, saved=None):
    import ads_posting_page as posting
    from posting_import_csv import canonical_posting_country

    explicit = saved or result.get('posting_settings') or {}
    product_sets = sorted(refs.get('product_sets') or [], key=lambda row: str(row.get('id','')))
    from sports_categories import normalize_sport_category
    sport = normalize_sport_category(result['category'])
    # Collection labels, not athlete/team relevance, determine the catalogue.
    # Prefer the canonical wall-art title, accepting exact taxonomy aliases.
    ranked = [row for row in product_sets
              if sport and normalize_sport_category(row.get('name')) == sport]
    canonical_name = ' '.join(tokens(sport + ' Wall Art'))
    ranked.sort(key=lambda row: (
        ' '.join(tokens(row.get('name'))) != canonical_name,
        not ' '.join(tokens(row.get('name'))).endswith('wall art'),
    ))
    required_name = f'{sport or result["category"]} Wall Art'
    preferred_name = {'Formula One': FORMULA_ONE_PRODUCT_SET, 'NBA': NBA_PRODUCT_SET}.get(sport)
    if preferred_name:
        required_name = preferred_name
        ranked = [row for row in product_sets
                  if ' '.join(str(row.get('name') or '').split()).casefold()
                  == preferred_name.casefold()]
    if not ranked:
        raise CatalogPending(f'Meta has not yet confirmed the {required_name} collection.')
    # The cover and CTA promote the featured product; the Collection tiles use
    # the selected sport/curated set. A new product need not be in that set.
    # Posting still validates set/catalogue access and verifies every paused ad.
    chosen = ranked[0]
    country = posting.COUNTRY_META_CODES[canonical_posting_country(result['country'])]
    audiences = posting._audience_options(refs)
    saved_geo = {str(row['id']): (row.get('targeting') or {}).get('geo_locations') or {}
                 for row in refs.get('saved_audiences') or []}
    lookalike_geo = {str(row['id']): (row.get('lookalike_spec') or {}).get('country')
                    for row in refs.get('custom_audiences') or []}
    def eligible(row):
        countries = saved_geo.get(str(row.get('id')), {}).get('countries') or []
        lookalike_country = lookalike_geo.get(str(row.get('id')))
        return (not countries or country in countries) and (not lookalike_country or country == lookalike_country)
    explicit_audience = explicit.get('audience') or {}
    if explicit_audience and (explicit.get('audience_explicit') or saved):
        audience = next((row for row in audiences if row['key'] == explicit_audience.get('key') and eligible(row)), None)
        if not audience:
            raise ValueError('The selected audience is unavailable or does not match the campaign market.')
    else:
        metadata = result.get('product_metadata') or {}
        context = result['product_name'] + ' ' + ' '.join(str(metadata.get(field) or '') for field in ('athletes','teams','league'))
        candidates = sorted((row for row in audiences if row['type'] != 'broad' and eligible(row)), key=lambda row: row['key'])
        options = rank_relevant_meta_options(candidates,
            product_title=context, sport=result['category'], id_key='key')['options']
        sport_terms, title_terms = extract_relevance_terms(context, result['category'])
        identity_terms = set(title_terms)-sport_terms
        options.sort(key=lambda row: -len(identity_terms & set(tokens(row.get('name')))))
        audience = options[0] if options else next(row for row in audiences if row['type']=='broad')
    return dict(product_set_id=str(chosen['id']), product_set_name=chosen['name'], audience=audience,
                audience_name=audience.get('name') or 'Broad — Sports Cave Default', audience_explicit=True)
