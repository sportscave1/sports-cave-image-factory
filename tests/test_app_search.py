import asyncio
import json
import sys
import unittest
from unittest.mock import patch

import app_search
import os_accounts
import top_bar
import top_bar_api


class AppSearchTests(unittest.TestCase):
    def test_all_routes_and_features_are_permission_scoped(self):
        rows = app_search.build_app_index([p['route'] for p in os_accounts.PAGE_REGISTRY])
        self.assertEqual(len({r['id'] for r in rows}), len(rows))
        self.assertTrue(all(r['route_key'] in os_accounts.PAGE_BY_KEY for r in rows))
        self.assertTrue(all(not r['query'] for r in rows))
        limited = app_search.build_app_index(['Email'])
        self.assertEqual({r['title'] for r in limited}, {'Email','Email Settings','Customer Support','Signatures'})
        self.assertTrue(all(r['route_key']=='email' for r in limited))
        limited[0]['aliases'].append('mutation')
        self.assertNotIn('mutation', app_search.build_app_index(['Email'])[0]['aliases'])

    def test_compatibility_endpoint_does_not_load_entities_or_connectors(self):
        with patch.object(top_bar_api, '_claims', return_value={'allowed_routes':['Email']}), \
             patch.object(top_bar_api, 'load_search_sources', side_effect=AssertionError('I/O forbidden')):
            response = asyncio.run(top_bar_api.top_bar_search_index(None))
        self.assertEqual(len(json.loads(response.body)['results']), 4)

    def test_shell_embeds_index_without_initializing_pages(self):
        before=set(sys.modules)
        with patch.object(top_bar.top_bar_security, 'create_top_bar_token', return_value='fixture'), \
             patch.object(top_bar_api, 'load_search_sources', side_effect=AssertionError('I/O forbidden')):
            config=top_bar.top_bar_config({'id':'fixture','role':'admin','is_active':True},logo_src='',current_route='Dashboard')
        self.assertTrue(config['searchIndex'])
        loaded=set(sys.modules)-before
        self.assertFalse(any(name.startswith(('support_email','meta_graph','shopify')) for name in loaded))


if __name__ == '__main__': unittest.main()
