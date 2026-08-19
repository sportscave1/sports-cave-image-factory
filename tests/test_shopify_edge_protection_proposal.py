import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "config" / "shopify_storefront_edge_protection.proposed.json"


class ShopifyEdgeProtectionProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))

    def test_proposal_is_inert(self):
        self.assertEqual(self.proposal["status"], "PROPOSAL_ONLY_DO_NOT_APPLY")
        self.assertFalse(self.proposal["current_edge"]["merchant_controlled"])

    def test_only_correct_production_hosts_are_targeted(self):
        self.assertEqual(
            self.proposal["production_domains"],
            ["www.sportscaveshop.com", "sportscaveshop.com"],
        )
        expression = self.proposal["country_block"]["expression"]
        self.assertNotIn("sportscave.com.au", expression)

    def test_country_rule_blocks_singapore_on_both_hosts(self):
        rule = self.proposal["country_block"]
        self.assertEqual(rule["action"], "block")
        self.assertEqual(rule["response_status"], 403)
        self.assertIn('ip.src.country eq "SG"', rule["expression"])
        self.assertIn('"www.sportscaveshop.com"', rule["expression"])
        self.assertIn('"sportscaveshop.com"', rule["expression"])

    def test_search_exception_requires_provider_verification(self):
        expression = self.proposal["country_block"]["expression"]
        self.assertIn("cf.bot_management.verified_bot", expression)
        self.assertIn("cf.verified_bot_category", expression)
        self.assertIn("Search Engine Crawler", expression)
        self.assertNotIn("user_agent", expression.casefold())
        self.assertNotIn("googlebot", expression.casefold())

    def test_rate_limit_is_not_armed_before_baselining(self):
        rule = self.proposal["rate_limit_pilot"]
        self.assertEqual(rule["status"], "DISABLED_PENDING_EDGE_LOG_BASELINE")
        self.assertEqual(rule["action"], "managed_challenge")
        self.assertIn('/products/', rule["expression"])
        self.assertIn('/collections/', rule["expression"])


if __name__ == "__main__":
    unittest.main()
