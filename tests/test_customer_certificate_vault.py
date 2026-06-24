import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CustomerCertificateVaultTests(unittest.TestCase):
    def test_shopify_app_requests_customer_account_scopes_without_dropping_admin_scopes(self):
        source = (ROOT / "shopify_customer_account" / "shopify.app.toml").read_text(encoding="utf-8")
        match = re.search(r'^\s*scopes\s*=\s*"([^"]*)"', source, flags=re.MULTILINE)
        self.assertIsNotNone(match)
        scopes = {scope.strip() for scope in match.group(1).split(",") if scope.strip()}

        for scope in (
            "read_customers",
            "read_orders",
            "write_orders",
            "read_products",
            "write_products",
            "read_files",
            "write_files",
            "read_images",
            "write_images",
            "read_inventory",
            "read_locations",
            "read_markets",
            "read_metaobjects",
            "read_metaobject_definitions",
            "customer_read_customers",
            "customer_read_orders",
        ):
            self.assertIn(scope, scopes)

    def test_customer_account_extension_uses_api_access_without_external_network_access(self):
        source = (
            ROOT
            / "shopify_customer_account"
            / "extensions"
            / "customer-certificate-vault"
            / "shopify.extension.toml"
        ).read_text(encoding="utf-8")

        self.assertIn("target = \"customer-account.page.render\"", source)
        self.assertRegex(source, r"(?m)^\s*api_access\s*=\s*true\s*$")
        self.assertNotRegex(source, r"(?m)^\s*network_access\s*=\s*true\s*$")

    def test_customer_extension_reads_order_certificate_metafields_and_hides_raw_scope_errors(self):
        source = (
            ROOT
            / "shopify_customer_account"
            / "extensions"
            / "customer-certificate-vault"
            / "src"
            / "MySportsCaveCollection.jsx"
        ).read_text(encoding="utf-8")

        self.assertIn("shopify://customer-account/api/${API_VERSION}/graphql.json", source)
        self.assertIn('metafield(namespace: "sports_cave", key: "certificates_json")', source)
        self.assertIn("jsonValue", source)
        self.assertIn("customerSafeErrorMessage", source)
        self.assertIn(
            "Certificate vault permissions are still being updated. Please try again shortly.",
            source,
        )
        self.assertIn('heading="My Collection"', source)
        self.assertIn("Your Sports Cave Collector Vault", source)
        self.assertIn(
            "Every numbered release in your collection is recorded here with its official certificate of authenticity.",
            source,
        )
        self.assertIn("Your collection is waiting.", source)
        self.assertIn("certificate_preview_image_url", source)
        self.assertIn("certificate_print_jpg_url", source)
        self.assertIn("View Certificate", source)
        self.assertIn("Download Print Certificate", source)
        self.assertIn("Download PDF", source)
        self.assertIn("<s-button", source)
        self.assertIn('target="_blank"', source)
        self.assertIn("matchesContext(record.shopify_customer_id, customer?.id)", source)
        self.assertIn("matchesContext(record.shopify_order_id, order?.id)", source)
        self.assertIn("Array.isArray(parsed)", source)
        self.assertIn("record.certificate_pdf_url || record.certificate_file_url", source)

    def test_customer_vault_release_notes_are_documented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        extension_readme = (ROOT / "shopify_customer_account" / "README.md").read_text(encoding="utf-8")

        for source in (readme, extension_readme):
            self.assertIn("customer_read_customers", source)
            self.assertIn("customer_read_orders", source)
            self.assertIn("api_access", source)
            self.assertIn("Shopify Files/CDN", source)


if __name__ == "__main__":
    unittest.main()
