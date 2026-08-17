import unittest

import seo_technical_audit as technical


class TechnicalHTMLAuditTests(unittest.TestCase):
    def test_healthy_page_does_not_invent_findings(self):
        findings = technical.audit_html(
            "https://www.sportscaveshop.com/products/example",
            status_code=200,
            final_url="https://www.sportscaveshop.com/products/example",
            html_text=(
                '<html><head><title>Example</title><meta name="description" content="Useful page">'
                '<link rel="canonical" href="https://www.sportscaveshop.com/products/example">'
                '</head><body><h1>Example</h1><img src="product.webp" alt="Framed sports artwork">'
                '</body></html>'
            ),
        )
        self.assertEqual(findings, [])

    def test_html_audit_reports_va_safe_indexing_and_accessibility_issues(self):
        findings = technical.audit_html(
            "https://example.test/page",
            status_code=200,
            final_url="https://example.test/page",
            html_text='<meta name="robots" content="noindex"><h1>A</h1><h1>B</h1><img src="x.webp">',
        )
        codes = {row["issue_code"] for row in findings}
        self.assertTrue({"noindex", "missing_title", "missing_meta_description", "h1_count", "missing_canonical", "missing_image_alt"} <= codes)
        self.assertTrue(all(row.get("correction_steps") and row.get("likely_impact") for row in findings))

    def test_url_inspection_is_saved_evidence_not_a_live_test(self):
        findings = technical.inspection_findings(
            "https://example.test/page",
            {
                "inspectionResult": {
                    "indexStatusResult": {
                        "verdict": "FAIL",
                        "coverageState": "Crawled - currently not indexed",
                        "googleCanonical": "https://example.test/other",
                    }
                }
            },
        )
        self.assertEqual(findings[0]["source"], "GSC URL Inspection")
        self.assertEqual(findings[0]["coverage_state"], "Crawled - currently not indexed")
        self.assertNotIn("live test", findings[0]["issue_summary"].casefold())

    def test_product_schema_and_broken_internal_links_are_checked_in_background(self):
        findings = technical.audit_html(
            "https://example.test/products/example",
            status_code=200,
            final_url="https://example.test/products/example",
            page_type="product",
            html_text=(
                '<title>Example</title><meta name="description" content="Description">'
                '<link rel="canonical" href="https://example.test/products/example">'
                '<h1>Example</h1><a href="/missing">Missing</a>'
            ),
        )
        self.assertIn("missing_structured_data", {row["issue_code"] for row in findings})

        class Response:
            status_code = 404

        broken, checked = technical.broken_internal_link_findings(
            "https://example.test/products/example",
            '<a href="/missing">Missing</a><a href="https://outside.test/no">Outside</a>',
            request_get=lambda *_args, **_kwargs: Response(),
            cache={},
            remaining=5,
        )
        self.assertEqual(checked, 1)
        self.assertEqual(broken[0]["affected_urls"], ["https://example.test/missing"])


if __name__ == "__main__":
    unittest.main()
