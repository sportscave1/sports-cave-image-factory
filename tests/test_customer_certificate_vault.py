import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = (
    ROOT
    / "shopify_customer_account"
    / "extensions"
    / "customer-certificate-vault"
    / "src"
    / "MySportsCaveCollection.jsx"
)


class CustomerCertificateVaultTests(unittest.TestCase):
    def test_shopify_app_keeps_customer_and_admin_scopes(self):
        source = (ROOT / "shopify_customer_account" / "shopify.app.toml").read_text(
            encoding="utf-8"
        )
        match = re.search(r'^\s*scopes\s*=\s*"([^"]*)"', source, flags=re.MULTILINE)
        self.assertIsNotNone(match)
        scopes = {scope.strip() for scope in match.group(1).split(",") if scope.strip()}
        for scope in (
            "read_customers",
            "read_orders",
            "write_orders",
            "read_products",
            "write_products",
            "customer_read_customers",
            "customer_read_orders",
        ):
            self.assertIn(scope, scopes)

    def test_customer_account_extension_enables_authenticated_backend_access(self):
        source = (
            ROOT
            / "shopify_customer_account"
            / "extensions"
            / "customer-certificate-vault"
            / "shopify.extension.toml"
        ).read_text(encoding="utf-8")
        self.assertIn('target = "customer-account.page.render"', source)
        self.assertRegex(source, r"(?m)^\s*api_access\s*=\s*true\s*$")
        self.assertRegex(source, r"(?m)^\s*network_access\s*=\s*true\s*$")
        self.assertIn('key = "api_base_url"', source)

    def test_gallery_removes_old_dashboard_clutter(self):
        source = EXTENSION.read_text(encoding="utf-8")
        for removed in (
            "Your Sports Cave Collector Vault",
            "Collector Record",
            "Latest addition",
            "Download Print Certificate",
            "Verified Ownership",
        ):
            self.assertNotIn(removed, source)
        self.assertIn('heading="My Collection"', source)
        self.assertIn("collectionSubheading(certificates.length)", source)
        self.assertIn('gridTemplateColumns="repeat(auto-fit', source)
        self.assertIn('objectFit="contain"', source)
        self.assertIn('loading="lazy"', source)

    def test_certificate_cards_have_one_primary_action_and_hidden_details(self):
        source = EXTENSION.read_text(encoding="utf-8")
        card = source[source.index("function CertificateCard"):source.index("function CertificateMenu")]
        self.assertEqual(card.count('variant="primary"'), 1)
        self.assertIn("View Certificate", card)
        self.assertIn("Order It Framed", card)
        self.assertNotIn("certificate.certificate_id", card)
        details = source[
            source.index("function CertificateDetailsModal"):
            source.index("function CertificateViewer")
        ]
        self.assertIn("Certificate ID", details)
        self.assertIn("<s-clipboard-item", details)

    def test_viewer_review_and_frame_flows_use_native_accessible_overlays(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertIn('const modalId = "certificate-viewer"', source)
        self.assertIn("Certificate viewer for", source)
        self.assertIn("Download Certificate", source)
        self.assertIn("Frame the proof.", source)
        self.assertIn("Premium black frame", source)
        self.assertIn("A4 landscape", source)
        self.assertIn("Continue to secure checkout", source)
        self.assertIn('id={modalId}', source)
        self.assertIn("Submit review", source)
        self.assertIn("<s-drop-zone", source)
        self.assertIn("modalRef.current?.hideOverlay()", source)
        self.assertNotIn("document.getElementById", source)
        self.assertIn('state.status === "error"', source)
        self.assertIn('status === "loading"', source)
        self.assertIn('status === "error"', source)
        self.assertIn("certificates.length === 0", source)

    def test_frame_checkout_clicks_are_guarded_and_idempotent(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertIn('frameState.status === "adding"', source)
        self.assertIn("const idempotencyKey = allowRepeat", source)
        self.assertIn("certificate-${stableReferencePart(certificate.reference)}", source)
        self.assertIn("frameRequest.checkout_url", source)
        self.assertIn("Continue to secure checkout", source)

    def test_frame_product_lookup_uses_stable_shopify_gid(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertIn("query CollectorVaultFrameProduct($id: ID!)", source)
        self.assertIn("product(id: $id)", source)
        self.assertIn("variables: {id: frameConfig.product_id}", source)
        self.assertNotIn("product(handle: $handle)", source)

    def test_mobile_layout_uses_wrapping_grids_and_touch_targets(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("repeat(auto-fit, minmax(min(100%"), 2)
        self.assertNotIn("overflowX", source)
        self.assertIn('minBlockSize="44px"', source)
        self.assertIn('minInlineSize="44px"', source)

    def test_customer_data_and_private_tokens_are_not_embedded_in_frontend(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertIn("api.sessionToken.get()", source)
        self.assertIn("certificate_reference: certificate.reference", source)
        self.assertIn("review_reference: prompt.reference", source)
        self.assertIn("_sports_cave_frame_request", (
            ROOT
            / "shopify_customer_account"
            / "extensions"
            / "customer-certificate-vault"
            / "src"
            / "vault-utils.js"
        ).read_text(encoding="utf-8"))
        for secret in (
            "JUDGEME_PRIVATE_API_TOKEN",
            "JUDGEME_PUBLIC_API_TOKEN",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SHOPIFY_CLIENT_SECRET",
        ):
            self.assertNotIn(secret, source)

    def test_existing_account_navigation_is_left_to_shopify_host(self):
        source = EXTENSION.read_text(encoding="utf-8")
        readme = (
            ROOT / "shopify_customer_account" / "README.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("function AccountHeader", source)
        self.assertIn("Shopify renders full-page extensions inside its native", readme)
        self.assertIn("customer account menu", readme)


if __name__ == "__main__":
    unittest.main()
