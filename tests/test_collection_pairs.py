from unittest.mock import MagicMock, patch
import pytest
import collector_collection_offers as offers
from collector_collection_ranking import affinity, rank_candidates
from tests.test_collector_vault import CUSTOMER_A


def test_storefront_affinity_weights_and_family_deduplication():
    tags = ['SC_SUBJECT_A', 'SC_SUBJECT_B', 'SC_TEAM_C', 'SC_SPORT_BASEBALL']
    assert affinity(tags, tags) == 110 + 86 + 27
    assert affinity(['SC_THEME_GOLD'], ['SC_THEME_GOLD']) == 0
    assert affinity(['SC_SPORT_MOTORSPORT'], ['SC_SPORT_MOTORSPORT']) == 0
    assert rank_candidates('anchor', ['sport', 'team', 'subject'], {
        'anchor': tags, 'sport': ['SC_SPORT_BASEBALL'], 'team': ['SC_TEAM_C'], 'subject': ['SC_SUBJECT_A']
    }) == ['subject', 'team', 'sport']


def test_seed_must_be_owned_before_any_catalogue_request():
    with patch('crm_smart_catalogue.histories', return_value={CUSTOMER_A: [{'products': [{'product_id': 55}]}]}), \
         patch('collector_vault.list_owned_certificates', return_value=[]), \
         patch('crm_collector_transport.bounded') as bounded:
        from collector_vault import CollectorVaultError
        with pytest.raises(CollectorVaultError):
            offers.recommendations(CUSTOMER_A, 'AU', '999')
        bounded.assert_not_called()


def test_selected_edition_seeds_matching_and_all_purchases_stay_excluded():
    seed, other, sport, subject = [f'gid://shopify/Product/{i}' for i in (55, 56, 57, 58)]
    shop = MagicMock()
    shop.query.return_value = {'nodes': [
        {'id': seed, 'tags': ['SC_SUBJECT_A','SC_SPORT_BASEBALL']},
        {'id': sport, 'tags': ['SC_SPORT_BASEBALL']},
        {'id': subject, 'tags': ['SC_SUBJECT_A']},
    ]}
    catalogue = MagicMock()
    catalogue.resolve.return_value = [{'id': sport, 'edition': {'sold': 90}}, {'id': subject, 'edition': {'sold': 1}}]
    with patch('crm_smart_catalogue.histories', return_value={CUSTOMER_A: [{'products': [{'product_id': 55}, {'product_id': 56}]}]}), \
         patch('collector_vault.list_owned_certificates', return_value=[]), \
         patch('crm_collector_transport.bounded', return_value=shop), \
         patch('crm_catalogue.Catalogue', return_value=catalogue), \
         patch('crm_smart_candidates.memberships', return_value=[{'id': 'baseball'}]) as memberships, \
         patch('crm_smart_candidates.collection_products', return_value=[seed, other, sport, subject]) as collection_products, \
         patch('crm_catalogue.edition_available', return_value=True), \
         patch('crm_catalogue.product_issues', return_value=[]), \
         patch('website_recommendation_analytics._ranking_snapshot', return_value={}):
        result = offers.recommendations(CUSTOMER_A, 'AU', seed)
    assert memberships.call_args.args[1] == [seed]
    assert collection_products.call_args.args[1] == 'baseball'
    assert catalogue.resolve.call_args.args[0] == [subject, sport]
    assert [product['id'] for product in result] == [subject, sport]
