from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock,patch

from crm_abandoned_checkout import context,block_html,variant_details,edition_label,hydrate
from crm_checkout_styles import default_html,upgrade_html,rules
from crm_checkout_template import load
from crm_campaign_content import render_campaign
from tests.test_crm_abandoned_checkout import checkout,native_document
from tests.test_crm_send_flow import CFG
from tests.test_crm_checkout_template_styles import attrs


class CheckoutDetailsTests(TestCase):
    def test_known_frame_and_dimensions(self):
        for frame in ('Black','Oak','White','Unframed'):
            expected=frame if frame=='Unframed' else frame+' Frame'
            self.assertEqual(variant_details(frame+' / XL - 62 × 87 cm (24.4 × 34.3 in)'),
                             (expected+' · XL','62 × 87 cm (24.4 × 34.3 in)'))
        self.assertEqual(variant_details('Custom finish / Signed'),('Custom finish / Signed',''))
        self.assertEqual(variant_details('Black / Limited - special'),('Black Frame · Limited - special',''))

    def test_compact_row_and_shared_market_formatter(self):
        for currency,expected in [('AUD','A$423.30'),('USD','US$423.30'),('GBP','£423.30'),('NZD','NZD 423.30')]:
            source=checkout(currency=currency);line=source['lineItems']['nodes'][0]
            line['variantTitle']='Black / XL - 62 × 87 cm (24.4 × 34.3 in)'
            line['discountedTotalPriceWithCodeDiscount']['presentmentMoney']['amount']='423.30'
            original=deepcopy(source);data=context(source)
            html=render_campaign(hydrate(native_document(),data),CFG)['html']
            self.assertIn(expected,html);self.assertIn('Qty 2',html)
            for old in ('Line total:','Quantity:','YOUR SELECTED EDITION'):self.assertNotIn(old,html)
            for cls in ('sc-cart-dimensions','sc-cart-qty','sc-cart-divider','sc-cart-rule'):
                self.assertTrue(attrs(html,cls));self.assertIn('style',attrs(html,cls)[0])
            self.assertEqual(source,original)

    def test_exact_ledger_link_batch_and_no_render_reads(self):
        source=checkout(items=2)
        for line in source['lineItems']['nodes']:line['variant']={'product':{'id':'gid://shopify/Product/123'}}
        reader=Mock(return_value=[{'shopify_product_id':'123','edition_total':100,'run_next_edition_number':52,
                                  'sold_count':49,'remaining_count':51,'active':True}])
        data=context(source,edition_reader=reader)
        reader.assert_called_once_with(product_ids=['gid://shopify/Product/123'],handles=[],limit=100)
        for _ in range(3):
            html=block_html(data)
            self.assertIn('NEXT AVAILABLE EDITION · #052/100',html)
            self.assertNotIn('RESERVED',html)
        self.assertEqual(reader.call_count,1)

    def test_padding_and_limit_fallback_never_fabricates_reservation(self):
        for number in (8,52,99,100):
            label=edition_label({'limit':100,'next':number,'remaining':1,'reserved':True})
            self.assertIn('#'+str(number).zfill(3)+'/100',label);self.assertNotIn('RESERVED',label)
        for number in (None,0,101):
            self.assertEqual(edition_label({'limit':100,'next':number}), 'LIMITED TO 100 WORLDWIDE')
        self.assertEqual(edition_label(None),'')
        self.assertEqual(edition_label({'limit':True}),'')

    def test_unavailable_or_ambiguous_ledger_does_not_invent_number(self):
        source=checkout();source['lineItems']['nodes'][0]['variant']={'product':{'id':'gid://shopify/Product/123'}}
        row={'shopify_product_id':'123','edition_total':100}
        data=context(source,edition_reader=Mock(return_value=[row]))
        self.assertIn('LIMITED TO 100 WORLDWIDE',block_html(data))
        for reader in (Mock(return_value=[row,row]),Mock(side_effect=RuntimeError('Unavailable'))):
            self.assertNotIn('WORLDWIDE',block_html(context(source,edition_reader=reader)))

    def test_ledger_reads_are_bounded_and_unknown_product_never_matches(self):
        source=checkout(items=52)
        for index,line in enumerate(source['lineItems']['nodes']):
            if index<51:line['variant']={'product':{'id':'gid://shopify/Product/'+str(index+1)}}
        reader=Mock(return_value=[{'shopify_product_id':'1','edition_total':100}])
        data=context(source,edition_reader=reader)
        self.assertEqual([len(call.kwargs['product_ids']) for call in reader.call_args_list],[50,1])
        self.assertIsNone(data['items'][-1]['edition'])

    def test_legacy_master_read_upgrade_is_non_persistent_and_custom_rules_survive(self):
        import re
        legacy=re.sub(r'\.sc-cart-(?:dimensions|qty|divider|rule)\s*\{[^{}]*\}\n','',default_html())
        legacy=legacy.replace('.sc-cart-variant { color:#b79335;', '.sc-cart-variant { color:#aabbcc;')
        store=Mock();store.state.return_value={'revision':5,'html':legacy}
        result=load(store)
        self.assertIn('color:#aabbcc',result['html']);self.assertNotIn('.sc-cart-dimensions',result['html'])
        self.assertEqual(store.state.return_value['html'],legacy)
        self.assertEqual(result['html'],legacy)  # Opening a master never restores deleted source.
        self.assertIn('.sc-cart-dimensions',upgrade_html(result['html']))  # Legacy render-copy compatibility remains.
        self.assertTrue(rules(result['html']))

    def test_new_classes_are_restricted_to_semantic_tags(self):
        from crm_campaign_html import import_html
        html,_,_=import_html('<img class="sc-cart-rule" src="https://cdn.shopify.com/fixture.png"><p class="sc-cart-unknown">Text</p><hr class="sc-cart-rule">')
        self.assertEqual(html.count('class="sc-cart-rule"'),1)
        self.assertNotIn('sc-cart-unknown',html)
