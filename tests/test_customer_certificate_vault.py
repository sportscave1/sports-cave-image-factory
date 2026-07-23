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
REDESIGN_EXTENSION = EXTENSION.with_name("CollectorVaultRedesign.jsx")


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
            "read_files",
            "write_files",
            "customer_read_customers",
            "customer_read_orders",
        ):
            self.assertIn(scope, scopes)
        self.assertNotIn("read_images", scopes)
        self.assertNotIn("write_images", scopes)

    def test_customer_account_extension_uses_shopify_auth_without_external_network(self):
        source = (
            ROOT
            / "shopify_customer_account"
            / "extensions"
            / "customer-certificate-vault"
            / "shopify.extension.toml"
        ).read_text(encoding="utf-8")
        self.assertIn('target = "customer-account.page.render"', source)
        self.assertRegex(source, r"(?m)^\s*api_access\s*=\s*true\s*$")
        self.assertNotRegex(source, r"(?m)^\s*network_access\s*=\s*true\s*$")
        self.assertNotIn('key = "api_base_url"', source)

    def test_gallery_removes_old_dashboard_clutter(self):
        source = REDESIGN_EXTENSION.read_text(encoding="utf-8")
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
        source = REDESIGN_EXTENSION.read_text(encoding="utf-8")
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
        source = REDESIGN_EXTENSION.read_text(encoding="utf-8")
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

    def test_collection_retry_starts_a_new_customer_account_request(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertIn("setRetryKey((value) => value + 1)", source)
        self.assertIn("[retryKey]", source)
        self.assertIn(
            "shopify://customer-account/api/${API_VERSION}/graphql.json",
            source,
        )
        self.assertNotIn("/api/collector-vault/bootstrap", source)
        self.assertNotIn("api.sessionToken.get()", source)

    def test_frame_checkout_clicks_are_guarded_and_idempotent(self):
        source = REDESIGN_EXTENSION.read_text(encoding="utf-8")
        self.assertIn('frameState.status === "adding"', source)
        self.assertIn("const idempotencyKey = allowRepeat", source)
        self.assertIn("certificate-${stableReferencePart(certificate.reference)}", source)
        self.assertIn("frameRequest.checkout_url", source)
        self.assertIn("Continue to secure checkout", source)

    def test_frame_product_lookup_uses_stable_shopify_gid(self):
        source = REDESIGN_EXTENSION.read_text(encoding="utf-8")
        self.assertIn("query CollectorVaultFrameProduct($id: ID!)", source)
        self.assertIn("product(id: $id)", source)
        self.assertIn("variables: {id: frameConfig.product_id}", source)
        self.assertNotIn("product(handle: $handle)", source)

    def test_mobile_layout_uses_wrapping_grids_and_touch_targets(self):
        source = REDESIGN_EXTENSION.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("repeat(auto-fit, minmax(min(100%"), 2)
        self.assertNotIn("overflowX", source)
        self.assertIn('minBlockSize="44px"', source)
        self.assertIn('minInlineSize="44px"', source)

    def test_customer_data_and_private_tokens_are_not_embedded_in_frontend(self):
        source = REDESIGN_EXTENSION.read_text(encoding="utf-8")
        production_source = EXTENSION.read_text(encoding="utf-8")
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
            self.assertNotIn(secret, production_source)

    def test_existing_account_navigation_is_left_to_shopify_host(self):
        source = EXTENSION.read_text(encoding="utf-8")
        readme = (
            ROOT / "shopify_customer_account" / "README.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("function AccountHeader", source)
        self.assertIn("Shopify renders full-page extensions inside its native", readme)
        self.assertIn("customer account menu", readme)

    def test_production_restores_original_order_metafield_certificate_flow(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertIn("COLLECTOR_VAULT_REDESIGN_ENABLED = false", source)
        self.assertIn(
            'metafield(namespace: "sports_cave", key: "certificates_json")',
            source,
        )
        self.assertIn("collectCertificates(orderNodes, customer)", source)
        self.assertIn("View Certificate", source)
        self.assertIn("Download PDF", source)
        self.assertIn("Your collection is waiting", source)
        self.assertNotIn("CollectorVaultRedesign", source)
        self.assertNotIn("review_prompt", source)
        self.assertNotIn("frame_product", source)
        self.assertNotIn("/api/collector-vault/bootstrap", source)

    def test_phase_one_gallery_is_compact_premium_and_responsive(self):
        source = EXTENSION.read_text(encoding="utf-8")
        for removed in (
            "Your Sports Cave Collector Vault",
            "Collector Record",
            "Latest addition",
            "Active Collector",
            "Verified Sports Cave Record",
            "Numbered Collector Release",
        ):
            self.assertNotIn(removed, source)
        self.assertIn("<s-page>", source)
        self.assertNotIn('heading="My Collection"', source)
        self.assertNotIn("authenticatedEditionLabel", source)
        self.assertIn('gridTemplateColumns="minmax(0, 1200px)"', source)
        self.assertGreaterEqual(
            source.count("repeat(auto-fit, minmax(min(100%"),
            3,
        )
        self.assertIn('background="subdued"', source)
        self.assertIn('objectFit="contain"', source)
        self.assertIn('loading={eager ? "eager" : "lazy"}', source)
        card = source[
            source.index("function CertificateCard"):
            source.index("function CertificatePreview")
        ]
        self.assertEqual(card.count('variant="primary"'), 1)
        self.assertIn("View Certificate", card)
        self.assertIn("Download PDF", card)
        self.assertIn("Download Print", card)

    def test_phase_one_viewer_uses_native_modal_and_existing_asset_urls(self):
        source = EXTENSION.read_text(encoding="utf-8")
        viewer = source[source.index("function CertificateViewer"):]
        self.assertIn('id={modalId}', viewer)
        self.assertIn('accessibilityLabel={`Certificate viewer for ${title}`}', viewer)
        self.assertIn('size="max"', viewer)
        self.assertIn("onAfterHide={onClose}", viewer)
        self.assertIn('command="--hide"', viewer)
        self.assertIn("certificate.certificate_preview_image_url", source)
        self.assertIn("certificate.certificate_pdf_url", viewer)
        self.assertIn("certificate.certificate_print_jpg_url", viewer)
        self.assertIn("Download Certificate", viewer)
        self.assertIn("Close", viewer)
        self.assertNotIn("Order It Framed", source)
        self.assertNotIn("Leave a Review", viewer)
        self.assertNotIn("Judge.me", source)
        self.assertNotIn("review_prompt", source)
        self.assertNotIn("frame_product", source)
        self.assertNotIn("/api/collector-vault/", source)

    def test_review_banner_is_a_static_secure_external_link(self):
        source = EXTENSION.read_text(encoding="utf-8")
        banner = source[
            source.index("function ReviewBanner"):
            source.index("function LoadingState")
        ]
        self.assertIn("How does it look in your space?", banner)
        self.assertIn(
            "Share a quick review and help another fan see the real thing.",
            banner,
        )
        self.assertIn(
            'const REVIEWS_PAGE_URL = "https://www.sportscaveshop.com/pages/reviews";',
            source,
        )
        self.assertIn("href={REVIEWS_PAGE_URL}", banner)
        self.assertIn('target="_blank"', banner)
        self.assertIn(
            'accessibilityLabel="Leave a review on Sports Cave"',
            banner,
        )
        self.assertIn('accessibilityVisibility="hidden"', banner)
        self.assertIn("[1, 2, 3, 4, 5].map", banner)
        self.assertIn('type="star"', banner)
        self.assertIn('tone="warning"', banner)
        self.assertIn('objectFit="contain"', banner)
        self.assertIn('loading="lazy"', banner)
        self.assertIn("certificate?.purchased_image_url", banner)
        self.assertIn("certificate?.certificate_preview_image_url", banner)
        self.assertLess(
            source.index("<ReviewBanner"),
            source.index("<CertificateGallery"),
        )
        self.assertNotIn("api.sessionToken", banner)
        self.assertNotIn("fetch(", banner)
        self.assertNotIn("/api/", banner)

    def test_review_thumbnail_uses_authenticated_line_item_artwork_only(self):
        source = EXTENSION.read_text(encoding="utf-8")
        query = source[
            source.index("const CERTIFICATES_QUERY"):
            source.index("function Extension")
        ]
        for field in (
            "lineItems(first: 100)",
            "productId",
            "variantId",
            "sku",
            "image {",
            "url",
            "altText",
            "width",
            "height",
        ):
            self.assertIn(field, query)
        self.assertIn("attachPurchasedArtwork(", source)
        self.assertIn("collectCertificates(orderNodes, customer)", source)
        self.assertNotIn("overflowX", source)

        card = source[
            source.index("function CertificateCard"):
            source.index("function CertificatePreview")
        ]
        self.assertIn("<CertificatePreview", card)
        self.assertNotIn("purchased_image_url", card)
        for action in ("View Certificate", "Download PDF", "Download Print"):
            self.assertIn(action, card)
        gallery = source[
            source.index("function CertificateGallery"):
            source.index("function CertificateCard")
        ]
        self.assertIn(
            'minmax(min(100%, 320px), 1fr)',
            gallery,
        )

    def test_redesign_is_retained_but_not_the_production_module(self):
        production = EXTENSION.read_text(encoding="utf-8")
        redesign = REDESIGN_EXTENSION.read_text(encoding="utf-8")
        self.assertIn("/api/collector-vault/bootstrap", redesign)
        self.assertIn("Frame the proof.", redesign)
        self.assertIn("Submit review", redesign)
        self.assertNotIn("/api/collector-vault/bootstrap", production)


if __name__ == "__main__":
    unittest.main()
