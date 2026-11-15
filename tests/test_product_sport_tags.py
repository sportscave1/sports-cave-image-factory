import copy
import unittest
from product_sport_tags import TAGS, classify_product, apply_prompt_rules, START
from product_sport_tag_sync import sync_product_sport_tags, SportTagSyncError


def product(title, collections=(), tags=()):
    return {'id': 'gid://shopify/Product/123', 'title': title, 'tags': list(tags),
            'productType': 'Framed Art',
            'collections': [{'title': c, 'handle': c.lower().replace(' ', '-')} for c in collections]}


class ClassificationTests(unittest.TestCase):
    def test_new_disciplines_override_career_without_cross_classification(self):
        for title,sport in [('Valentino Rossi Isle of Man TT','Motorcycle Road Racing'),
                            ('Valentino Rossi Motocross','Motocross'),('Fernando Alonso IndyCar','IndyCar'),
                            ('Toby Price Dakar Rally','Rally Raid')]:
            result=classify_product(product(title))
            self.assertTrue(result.ready,result.review)
            self.assertEqual(set(result.required_tags),{TAGS['Motorsport'],TAGS[sport]})

    def test_required_acceptance_artworks(self):
        cases = {
            'Jett Lawrence Motocross': ['Motorsport', 'Motocross'],
            'Colin McRae 1995 RAC Rally': ['Motorsport', 'Rally'],
            'Michael Dunlop Isle of Man TT': ['Motorsport', 'Motorcycle Road Racing'],
            'Toby Price Dakar': ['Motorsport', 'Rally Raid'],
            'Will Power Indianapolis 500': ['Motorsport', 'IndyCar'],
            'Peter Brock Tribute': ['Motorsport', 'V8 Supercars'],
            'Ayrton Senna Tribute': ['Motorsport', 'Formula One'],
            'Dale Earnhardt Tribute': ['Motorsport', 'NASCAR'],
            'Valentino Rossi Tribute': ['Motorsport', 'MotoGP'],
            'Michael Jordan Tribute': ['Basketball'], 'Shane Warne Tribute': ['Cricket'],
            'Tom Brady Tribute': ['NFL'], 'Andrew Johns Tribute': ['Rugby League'],
            'Cristiano Ronaldo Tribute': ['Football'], 'Winx Tribute': ['Horse Racing'],
            'WWE Undertaker Tribute': ['WWE', 'Combat'],
            'Formula One vs NASCAR artwork': ['Motorsport', 'Formula One', 'NASCAR'],
        }
        for title, sports in cases.items():
            with self.subTest(title=title):
                result = classify_product(product(title))
                self.assertTrue(result.ready, result.review)
                self.assertEqual(set(result.required_tags), {TAGS[s] for s in sports})

    def test_every_exact_collection_mapping(self):
        for sport, tag in TAGS.items():
            result = classify_product(product('Tribute', [sport + ' Wall Art']))
            self.assertTrue(result.ready, sport)
            self.assertIn(tag, result.required_tags)

    def test_real_collection_handles_and_athletes(self):
        for handle, sport in [('motor-racing-wall-art', 'Motorsport'), ('nba', 'Basketball'),
                              ('rugby-league-collection', 'Rugby League'), ('soccer', 'Football'),
                              ('combat-art', 'Combat'), ('peter-brock-wall-art', 'V8 Supercars')]:
            result = classify_product(product('Tribute', [handle]))
            self.assertTrue(result.ready, result.review)
            self.assertIn(TAGS[sport], result.required_tags)

    def test_multi_sport_and_multiple_collections(self):
        p = product('Michael Jordan vs Cristiano Ronaldo', ['NBA Wall Art', 'Football Wall Art', 'Collector Series'])
        self.assertEqual(set(classify_product(p).required_tags), {TAGS['Basketball'], TAGS['Football']})
        self.assertTrue(classify_product(p).ready)

    def test_context_overrides_career_and_historical_names_preserved(self):
        for title in ['Valentino Rossi GT World Challenge',
                      'Valentino Rossi Enduro', 'Valentino Rossi Suzuka 8 Hours', 'Marc Márquez Supermoto']:
            result = classify_product(product(title))
            self.assertTrue(result.ready, result.review)
            self.assertEqual(result.required_tags, (TAGS['Motorsport'],))
        p = product('1972 Australian Touring Car Championship — Peter Brock')
        before = copy.deepcopy(p)
        self.assertIn(TAGS['V8 Supercars'], classify_product(p).required_tags)
        self.assertEqual(p, before)

    def test_broad_motorsport_supplemented_and_precise_conflict_reviewed(self):
        self.assertIn(TAGS['Formula One'], classify_product(product('Ayrton Senna', ['Motor Racing Wall Art'])).required_tags)
        for p in [product('Ayrton Senna', ['NBA Wall Art']),
                  product('Ayrton Senna', ['NASCAR Wall Art']),
                  product('Valentino Rossi GT World Challenge', ['MotoGP Wall Art']),
                  product('Shane Warne NBA Tribute')]:
            self.assertFalse(classify_product(p).ready)

    def test_no_generic_promotional_or_ambiguous_guesses(self):
        for title in ['GOAT Champion Racing Legend Final', 'Rugby Tribute', 'Hockey Hero']:
            result = classify_product(product(title, ['All Sports Wall Art', 'Best Selling Sports Wall Art',
                                                     'Popular', 'Featured Designs', 'Collector Series',
                                                     'New Products', 'The Gift Edit', 'Rivalries']))
            self.assertFalse(result.ready)
            self.assertEqual(result.required_tags, ())

    def test_olympics_swimming_and_football_boundaries(self):
        self.assertEqual(classify_product(product('Olympic Swimming Tribute')).required_tags, (TAGS['Olympics'],))
        self.assertEqual(classify_product(product('American Football')).required_tags, (TAGS['NFL'],))
        self.assertEqual(classify_product(product('Australian Rules Football')).required_tags, (TAGS['AFL'],))
        self.assertNotIn(TAGS['Olympics'], classify_product(product('Michael Jordan')).required_tags)

    def test_old_tags_preserved_and_wrong_classification_flagged(self):
        p = product('Peter Brock Tribute', tags=['collector', 'collector', TAGS['Formula One']])
        result = classify_product(p)
        self.assertFalse(result.ready)
        self.assertIn(TAGS['Formula One'], result.merged_tags)
        self.assertEqual(result.merged_tags.count('collector'), 1)
        p['tags'] = ['collector', TAGS['Motorsport']]
        self.assertEqual(classify_product(p).missing_tags, (TAGS['V8 Supercars'],))

    def test_description_variation_cannot_change_tags(self):
        p = product('Peter Brock Tribute')
        expected = classify_product(p).required_tags
        p['descriptionHtml'] = 'Champion GOAT perfect gift for basketball or football fans'
        self.assertEqual(classify_product(p).required_tags, expected)

    def test_contrary_motor_prose_and_negation_require_review(self):
        p = product('Valentino Rossi Tribute')
        p['descriptionHtml'] = '<p>His GT World Challenge race.</p>'
        self.assertFalse(classify_product(p).ready)
        self.assertFalse(classify_product(product('Not NASCAR Tribute')).ready)

    def test_shared_prompt_repeatable(self):
        text = apply_prompt_rules('Existing prompt', {'product_name': 'Peter Brock Tribute'})
        self.assertEqual(text, apply_prompt_rules(text, {'product_name': 'Peter Brock Tribute'}))
        self.assertEqual(text.count(START), 1)
        for tag in TAGS.values(): self.assertIn(tag, text)


class FakeShopify:
    def __init__(self, value=None):
        self.product = value or product('Peter Brock Tribute', tags=['Unrelated'])
        self.product.update(variants=[{'price': '339', 'inventory': 20}], images=['black.webp'], descriptionHtml='<p>Approved</p>')
        self.calls = []; self.adds = 0; self.timeout_after_write = False; self.readback_fail = False
        self.reject = False

    def __call__(self, query, variables):
        self.calls.append((query, copy.deepcopy(variables)))
        if 'mutation' in query:
            self.adds += 1
            if self.reject: return {'tagsAdd': {'node': None, 'userErrors': [{'message': 'Access denied'}]}}
            self.product['tags'] = list(dict.fromkeys(self.product['tags'] + variables['tags']))
            if self.timeout_after_write:
                self.timeout_after_write = False
                raise TimeoutError('response lost')
            return {'tagsAdd': {'node': {'id': self.product['id']}, 'userErrors': []}}
        if self.readback_fail and self.adds: raise TimeoutError('read unavailable')
        p = copy.deepcopy(self.product)
        p['collections'] = {'nodes': p['collections'], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}
        return {'product': p}


class SyncTests(unittest.TestCase):
    def test_new_and_existing_preserve_all_other_fields_and_duplicate_retry(self):
        for initial in [[], ['Unrelated', TAGS['Motorsport']]]:
            api = FakeShopify(product('Peter Brock Tribute', tags=initial))
            before = copy.deepcopy(api.product)
            result = sync_product_sport_tags(123, request=api)
            self.assertEqual(result['status'], 'verified')
            self.assertEqual(api.product | {'tags': before['tags']}, before)
            self.assertTrue(set(initial) <= set(api.product['tags']))
            sync_product_sport_tags(123, request=api)
            self.assertEqual(api.adds, 1)
            self.assertEqual(len(api.product['tags']), len(set(api.product['tags'])))
            for query, variables in api.calls:
                if 'mutation' in query: self.assertEqual(set(variables), {'id', 'tags'})

    def test_timeout_after_success_reconciles_same_product(self):
        api = FakeShopify(); api.timeout_after_write = True
        self.assertEqual(sync_product_sport_tags(123, request=api)['status'], 'verified')
        self.assertEqual(api.adds, 1)

    def test_unknown_conflict_and_existing_wrong_tag_never_write(self):
        for p in [product('Unknown'), product('Ayrton Senna', ['NBA Wall Art']),
                  product('Peter Brock', tags=[TAGS['Formula One']])]:
            api = FakeShopify(p)
            self.assertEqual(sync_product_sport_tags(123, request=api)['status'], 'review_required')
            self.assertEqual(api.adds, 0)

    def test_timeout_readback_and_usererrors_report_failure(self):
        def timeout(*args): raise TimeoutError()
        with self.assertRaises(SportTagSyncError): sync_product_sport_tags(123, request=timeout)
        for field in ('readback_fail', 'reject'):
            api = FakeShopify(); setattr(api, field, True)
            with self.assertRaises(SportTagSyncError): sync_product_sport_tags(123, request=api)
            self.assertLessEqual(api.adds, 2)

    def test_wrong_identity_and_incomplete_pagination_never_write(self):
        api = FakeShopify(); api.product['id'] = 'gid://shopify/Product/999'
        with self.assertRaises(SportTagSyncError): sync_product_sport_tags(123, request=api)
        self.assertEqual(api.adds, 0)
        with self.assertRaises(SportTagSyncError): sync_product_sport_tags('gid://shopify/Customer/123', request=api)

    def test_readback_missing_tags_and_broken_pagination_fail(self):
        api = FakeShopify()
        def lost_tags(query, variables):
            data = api(query, variables)
            if 'mutation' in query: api.product['tags'] = ['Unrelated']
            return data
        with self.assertRaises(SportTagSyncError): sync_product_sport_tags(123, request=lost_tags)
        self.assertEqual(api.adds, 2)
        api = FakeShopify()
        def broken_pages(query, variables):
            data = api(query, variables)
            data['product']['collections']['pageInfo'] = {'hasNextPage': True, 'endCursor': 'repeated'}
            return data
        with self.assertRaises(SportTagSyncError): sync_product_sport_tags(123, request=broken_pages)
        self.assertEqual(api.adds, 0)

    def test_collection_pagination(self):
        api = FakeShopify(product('Tribute'))
        def pages(query, variables):
            data = api(query, variables)
            if 'mutation' not in query:
                data['product']['collections'] = ({'nodes': [{'title': 'Collector Series'}],
                    'pageInfo': {'hasNextPage': True, 'endCursor': 'next'}} if not variables.get('after') else
                    {'nodes': [{'title': 'Formula One Wall Art'}], 'pageInfo': {'hasNextPage': False}})
            return data
        self.assertEqual(sync_product_sport_tags(123, request=pages)['status'], 'verified')
        self.assertIn(TAGS['Formula One'], api.product['tags'])


if __name__ == '__main__': unittest.main()
