"""Deterministic queue targeting using smart candidates and verified membership."""
import re
from urllib.parse import urlsplit

from ads_target_relevance import rank_relevant_meta_options, tokens, extract_relevance_terms


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
    from meta_ads_client import MetaAdsApiError
    from posting_import_csv import canonical_posting_country

    explicit = saved or result.get('posting_settings') or {}
    product_sets = sorted(refs.get('product_sets') or [], key=lambda row: str(row.get('id','')))
    selected_set = str(explicit.get('product_set_id') or '')
    ranked = rank_relevant_meta_options(product_sets, product_title=result['product_name'],
        sport=result['category'], show_all=True)['all_options']
    sport_terms, title_terms = extract_relevance_terms(result['product_name'], result['category'])
    identity_terms = set(title_terms)-sport_terms
    ranked.sort(key=lambda row: -len(identity_terms & set(tokens(row.get('name')))))
    if selected_set:
        ranked = [row for row in ranked if str(row['id']) == selected_set]
        if not ranked:
            raise ValueError('The selected product set is no longer in the configured catalog.')
    chosen = None
    for row in ranked:
        try:
            products = client.product_set_members(str(row['id']))
        except MetaAdsApiError as error:
            if str(error.error_code) in ('3', '10', '190', '200') and not error.is_transient:
                raise ValueError(
                    'Meta denied product-set membership verification '
                    f'(code {error.error_code}). All imported files are saved. '
                    'Check the Meta app and catalogue access, then Resume import.'
                ) from error
            raise
        if contains_product(products, result):
            chosen = row
            break
    if not chosen:
        raise ValueError('No eligible product set contains this product. Files are saved; correct the catalog membership and Resume import.')
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
