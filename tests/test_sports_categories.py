import ast
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import sports_categories as sports

ROOT = Path(__file__).resolve().parents[1]


class SportRegistryTests(unittest.TestCase):
    def test_order_duplicates_and_controls(self):
        values = sports.sport_category_options('Select category')
        self.assertEqual(values[0], 'Select category')
        self.assertEqual(values[-1], 'Other')
        self.assertEqual(values[1:-1], tuple(sorted(values[1:-1], key=str.casefold)))
        self.assertEqual(len(values), len(set(values)))
        self.assertEqual(sports.sport_category_options('', current='Soccer').count('Football'), 1)

    def test_legacy_aliases(self):
        for alias, expected in {
            'Soccer': 'Football', 'Football/Soccer': 'Football', 'Basketball': 'NBA',
            'Hockey': 'Ice Hockey', 'NHL': 'Ice Hockey', 'Boxing': 'Combat',
            'MMA': 'Combat', 'Combat Sports': 'Combat', 'UFC/MMA': 'Combat',
            'Motor Racing': 'Motorsport', 'NRL': 'Rugby League', 'F1': 'Formula One',
            'Supercars': 'V8 Supercars', 'MLB': 'Baseball',
        }.items():
            with self.subTest(alias=alias):
                self.assertEqual(sports.normalize_sport_category(alias), expected)
                self.assertTrue(sports.is_valid_sport_category(alias))

    def test_unknown_workflow_defaults(self):
        self.assertEqual(sports.normalize_sport_category('unknown'), '')
        self.assertEqual(sports.normalize_sport_category('unknown', 'Other'), 'Other')
        self.assertFalse(sports.is_valid_sport_category('unknown'))

    def test_live_audit_coverage_and_marketing_exclusion(self):
        audit = json.loads((ROOT / 'tests/fixtures/sport_taxonomy_shopify_2026_10_07.json').read_text(encoding='utf-8'))
        self.assertTrue(audit['collections_complete'])
        self.assertTrue(audit['active_products_complete'])
        by_handle = {c['handle']: c for c in audit['collections']}
        for sport, handles in sports.SPORT_COLLECTION_HANDLES.items():
            for handle in handles:
                self.assertIn(handle, by_handle)
                self.assertEqual(sports.normalize_sport_category(by_handle[handle]['title']), sport)
        for collection in audit['collections']:
            if collection['handle'] not in {h for hs in sports.SPORT_COLLECTION_HANDLES.values() for h in hs}:
                self.assertEqual(sports.normalize_sport_category(collection['title']), '', collection['title'])

    def test_hierarchy_does_not_guess_unrelated_sports(self):
        self.assertEqual(sports.infer_sport_category(['Formula One Wall Art', 'Motor Racing Wall Art']), 'Formula One')
        self.assertEqual(sports.infer_sport_category(['NFL', 'NBA']), '')
        self.assertEqual(sports.detect_sport_in_text('American Football Wall Art'), 'NFL')
        self.assertEqual(sports.detect_sport_in_text('Horse Racing Wall Art'), 'Horse Racing')

    def test_all_providers_share_registry(self):
        import ads_page, db, meta_posting_service, social_media_creator
        import social_media_reels_studio_page as reels
        import sports_cave_dashboard, seo_blog_workflow, app, crm_logic
        expected = set(sports.CANONICAL_SPORT_CATEGORIES)
        for values in (ads_page.CATEGORY_OPTIONS, db.SPORT_CATEGORIES,
                       meta_posting_service.SPORT_OPTIONS, social_media_creator.SPORT_OPTIONS,
                       reels.SPORT_CATEGORY_OPTIONS, sports_cave_dashboard.DESIGN_IDEA_SPORTS,
                       seo_blog_workflow.SPORT_OPTIONS, app.SPORT_OPTIONS, crm_logic.SPORTS):
            self.assertTrue(expected <= set(values))
        import ads_creative_refresh
        self.assertIs(ads_creative_refresh.ads_page.CATEGORY_OPTIONS, ads_page.CATEGORY_OPTIONS)

    def test_state_normalization_is_idempotent(self):
        state = {'ads_category': 'Soccer', 'refresh': 'NRL', 'posting': 'Hockey', 'social': 'Basketball'}
        for key in state:
            sports.normalize_sport_state(state, key, 'Other')
        self.assertEqual(list(state.values()), ['Football', 'Rugby League', 'Ice Hockey', 'NBA'])
        expected = dict(state)
        for key in state:
            sports.normalize_sport_state(state, key, 'Other')
        self.assertEqual(state, expected)

    def test_database_payload_aliases(self):
        import db
        for value in (*sports.CANONICAL_SPORT_CATEGORIES, 'Soccer', 'Hockey', 'Boxing'):
            self.assertEqual(db.clean_product_payload({'sport_category': value})['sport_category'],
                             sports.normalize_sport_category(value))

    def test_meta_review_product_hydration(self):
        import meta_review_products, meta_review_handoff
        for sport in sports.CANONICAL_SPORT_CATEGORIES:
            product = meta_review_products.canonical({'title': 'Test', 'handle': 'test', 'sport_category': sport})
            self.assertEqual(product['category'], sport)
            state = {}
            meta_review_handoff.hydrate_product(state, product)
            self.assertEqual(state['ads_category'], sport)

    def test_shared_primary_product_category_uses_specific_collection(self):
        import meta_review_products
        result = meta_review_products.canonical({'title': 'Test', 'handle': 'test',
            'collections': [{'title': 'Motor Racing Wall Art'}, {'title': 'Formula One Wall Art'}]})
        self.assertEqual(result['category'], 'Formula One')

    def test_all_sports_generate_ads_without_network(self):
        import ads_page
        with patch('requests.sessions.Session.request', side_effect=AssertionError('No network permitted')):
            for sport in sports.CANONICAL_SPORT_CATEGORIES:
                for campaign_type in ('Carousel', 'Instant Experience', 'Single Image / Video'):
                    with self.subTest(sport=sport, campaign_type=campaign_type):
                        result = ads_page.build_ads_prompt('Test Collector Edition', sport, 'Australia',
                            campaign_type, 'https://www.sportscaveshop.com/products/test', variation_token='taxonomy-test')
                        self.assertTrue(result)

    def test_posting_inference_and_saved_alias_validation(self):
        import ads_posting_page
        for sport in sports.CANONICAL_SPORT_CATEGORIES:
            self.assertEqual(ads_posting_page._infer_sport({'row': {'sport_category': sport}}), sport)

    def test_posting_csv_accepts_every_sport_and_old_aliases(self):
        from tests.test_posting_import_csv import posting_rows
        from posting_import_csv import serialize_posting_import_csv, parse_posting_import_csv
        for value in (*sports.CANONICAL_SPORT_CATEGORIES, 'Soccer', 'Hockey', 'NRL'):
            rows = posting_rows(sport_category=value)
            parsed = parse_posting_import_csv(serialize_posting_import_csv(rows),
                allowed_sports=sports.sport_category_options())
            self.assertEqual(parsed['sport_category'], sports.normalize_sport_category(value))

    def test_saved_posting_handoff_keeps_alias_package_intact(self):
        from copy import deepcopy
        from tests.test_ads_posting_handoff import completed_ad, save_locally, product_records
        import ads_posting_handoff as handoff
        import ads_posting_page as posting
        result, workflow = completed_ad()
        result['category'] = 'Soccer'
        save_locally(result, workflow)
        package = workflow[handoff.SAVED_PACKAGE_KEY]
        original = deepcopy(package)
        state = {}
        handoff.queue_saved_package(package, state=state)
        self.assertTrue(posting.consume_saved_posting_package(product_records(), state=state))
        sports.normalize_sport_state(state, posting.SPORT_KEY, 'Other')
        self.assertEqual(state[posting.SPORT_KEY], 'Football')
        self.assertEqual(package, original)

    def test_sport_specific_adapters_accept_new_disciplines(self):
        import design_studio_styles, image_factory
        for sport in sports.MOTORSPORT_DISCIPLINES:
            self.assertEqual(design_studio_styles.select_sport_adapter(sport), 'motorsport')
            self.assertIn('graphite', image_factory.build_room_style_guidance('Test', sport))
        self.assertEqual(design_studio_styles.select_sport_adapter('Combat'), 'combat')
        self.assertEqual(design_studio_styles.select_sport_adapter('Swimming'), 'generic')

    def test_product_filter_includes_historical_aliases_without_writes(self):
        import db
        from unittest.mock import MagicMock
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        with patch.object(db, 'get_connection') as context:
            context.return_value.__enter__.return_value = connection
            self.assertEqual(db.list_products(sport_category='Football'), [])
        sql, params = connection.execute.call_args.args
        self.assertTrue(sql.lstrip().startswith('SELECT'))
        self.assertIn('soccer', params)
        self.assertIn('football', params)

    def test_legacy_crm_interest_rules_accept_canonical_labels(self):
        import crm_logic
        from unittest.mock import Mock
        facts = Mock()
        facts.value.return_value = {'Baseball', 'Rugby League'}
        self.assertTrue(crm_logic.matches(crm_logic.rule('interest', 'MLB', 'contains'), facts))
        self.assertTrue(crm_logic.matches(crm_logic.rule('interest', 'NRL', 'contains'), facts))

    def test_reels_new_disciplines_and_legacy_detection(self):
        import social_media_reels_studio_page as reels
        self.assertEqual(reels.detect_sport_category('peter-brock-v8-supercars'), 'V8 Supercars')
        self.assertEqual(reels.detect_sport_category('brady-super-bowl-football'), 'NFL')
        self.assertEqual(reels.detect_sport_category('jordan-basketball'), 'NBA')
        self.assertEqual(reels.detect_sport_category('motogp-racing'), 'MotoGP')

    def test_seo_editorial_custom_values_preserved(self):
        import seo_blog_workflow as blog
        self.assertEqual(blog.normalize_brief({'sport': 'Basketball / NBA'})['sport'], 'NBA')
        result = blog.normalize_brief({'sport': 'Cycling'})
        self.assertEqual((result['sport'], result['sport_custom']), ('Other', 'Cycling'))
        self.assertEqual(blog.normalize_brief({'sport': 'All Sports / General Sports'})['sport'], 'All Sports / General Sports')

    def test_design_ideas_all_sports_have_safe_style_fallback(self):
        import sports_cave_dashboard as dashboard
        for sport in sports.CANONICAL_SPORT_CATEGORIES:
            self.assertEqual(sum(dashboard.suggest_design_idea_style_mix(sport, 10).values()), 10)

    def test_no_network_dependency_in_registry(self):
        tree = ast.parse((ROOT / 'sports_categories.py').read_text(encoding='utf-8'))
        modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        modules.update(a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names)
        self.assertEqual(modules, {'re', 'ui_option_ordering'})


class SportWidgetTests(unittest.TestCase):
    def test_actual_provider_widgets_preserve_aliases_across_reruns(self):
        from streamlit.testing.v1 import AppTest
        script = '''
import streamlit as st
import ads_page, ads_creative_refresh, meta_posting_service, social_media_creator
from sports_categories import normalize_sport_state
providers = {'New Ads': ads_page.CATEGORY_OPTIONS,
             'Creative Refresh': ads_creative_refresh.ads_page.CATEGORY_OPTIONS,
             'Posting': meta_posting_service.SPORT_OPTIONS,
             'Social': social_media_creator.SPORT_OPTIONS}
for label, options in providers.items():
    normalize_sport_state(st.session_state, label, 'Other')
    st.selectbox(label, options, key=label)
'''
        app = AppTest.from_string(script)
        for key in ('New Ads', 'Creative Refresh', 'Posting', 'Social'):
            app.session_state[key] = 'NRL'
        app.run(timeout=30)
        self.assertFalse(app.exception)
        for widget in app.selectbox:
            self.assertEqual(widget.value, 'Rugby League')
            self.assertTrue(set(sports.CANONICAL_SPORT_CATEGORIES) <= set(widget.options))
        app.selectbox[0].select('MotoGP').run()
        app.run()
        self.assertEqual(app.selectbox[0].value, 'MotoGP')
        self.assertEqual(app.selectbox[1].value, 'Rugby League')


if __name__ == '__main__':
    unittest.main()
