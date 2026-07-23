/** @jsxImportSource preact */
/// <reference types="@shopify/ui-extensions/customer-account.page.render" />
import "@shopify/ui-extensions/preact";
import {render} from "preact";
import {useEffect, useMemo, useState} from "preact/hooks";

import {
  collectCertificates,
  collectionSummary,
  customerSafeErrorMessage,
} from "./legacy-certificate-utils.js";

export const COLLECTOR_VAULT_REDESIGN_ENABLED = false;

const API_VERSION = "2026-04";
const SHOP_LATEST_DROPS_URL = "https://www.sportscaveshop.com";
const CERTIFICATES_QUERY = `query SportsCaveCustomerCertificates {
  customer {
    id
    orders(first: 50, reverse: true) {
      nodes {
        id
        name
        processedAt
        metafield(namespace: "sports_cave", key: "certificates_json") {
          type
          jsonValue
          value
        }
      }
    }
  }
}`;

export default function extension() {
  render(<Extension />, document.body);
}

function Extension() {
  const [status, setStatus] = useState("loading");
  const [certificates, setCertificates] = useState([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let mounted = true;

    async function loadCertificates() {
      setStatus("loading");
      setErrorMessage("");
      try {
        const response = await fetch(
          `shopify://customer-account/api/${API_VERSION}/graphql.json`,
          {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({query: CERTIFICATES_QUERY}),
          },
        );
        let payload = {};
        try {
          payload = await response.json();
        } catch (_error) {
          payload = {};
        }
        if (!response.ok) {
          const requestError = new Error("Customer Account API request failed.");
          requestError.status = response.status;
          throw requestError;
        }
        if (payload.errors?.length) {
          const requestError = new Error("Customer Account API query failed.");
          requestError.graphQLErrors = payload.errors;
          throw requestError;
        }

        const customer = payload.data?.customer || {};
        const orderNodes = customer.orders?.nodes || [];
        const rows = collectCertificates(orderNodes, customer);
        if (mounted) {
          setCertificates(rows);
          setStatus("ready");
        }
      } catch (error) {
        if (mounted) {
          setErrorMessage(customerSafeErrorMessage(error));
          setStatus("error");
        }
      }
    }

    loadCertificates();
    return () => {
      mounted = false;
    };
  }, [retryKey]);

  const summary = useMemo(
    () => collectionSummary(certificates),
    [certificates],
  );

  return (
    <s-page
      heading="My Collection"
      subheading="Your numbered Sports Cave collector certificates."
    >
      <VaultIntro />
      {status === "loading" ? <LoadingState /> : null}
      {status === "error" ? (
        <ErrorState
          message={errorMessage}
          onRetry={() => setRetryKey((value) => value + 1)}
        />
      ) : null}
      {status === "ready" && certificates.length === 0 ? <EmptyState /> : null}
      {status === "ready" && certificates.length > 0 ? (
        <s-stack gap="base">
          <CollectorSummary summary={summary} />
          {certificates.map((certificate) => (
            <CertificateCard
              key={certificate.key}
              certificate={certificate}
            />
          ))}
        </s-stack>
      ) : null}
    </s-page>
  );
}

function VaultIntro() {
  return (
    <s-section heading="Your Sports Cave Collector Vault">
      <s-stack gap="base">
        <s-text>
          Every numbered release in your collection is recorded here with its
          official certificate of authenticity.
        </s-text>
        <s-stack direction="inline" gap="small">
          <s-badge tone="neutral">Numbered Collector Release</s-badge>
          <s-badge tone="neutral">Official Certificate</s-badge>
          <s-badge tone="neutral">Verified Sports Cave Record</s-badge>
        </s-stack>
      </s-stack>
    </s-section>
  );
}

function LoadingState() {
  return (
    <s-section>
      <s-stack direction="inline" gap="base" alignItems="center">
        <s-spinner
          size="base"
          accessibilityLabel="Loading certificates"
        ></s-spinner>
        <s-text>Loading your collector vault...</s-text>
      </s-stack>
    </s-section>
  );
}

function EmptyState() {
  return (
    <s-section heading="Your collection is waiting.">
      <s-stack gap="base">
        <s-text>
          When you purchase a numbered Sports Cave release, your certificate of
          authenticity will appear here.
        </s-text>
        <s-link href={SHOP_LATEST_DROPS_URL} target="_blank">
          Shop Latest Drops
        </s-link>
      </s-stack>
    </s-section>
  );
}

function ErrorState({message, onRetry}) {
  return (
    <s-banner heading="Certificates unavailable" tone="critical">
      <s-stack gap="base">
        <s-text>
          {message || "We could not load your Sports Cave certificates."}
        </s-text>
        <s-button variant="secondary" onClick={onRetry}>
          Try again
        </s-button>
      </s-stack>
    </s-banner>
  );
}

function CollectorSummary({summary}) {
  return (
    <s-section heading="Collector Record">
      <s-grid
        gridTemplateColumns="repeat(auto-fit, minmax(150px, 1fr))"
        gap="base"
      >
        <SummaryTile
          label="Certificates owned"
          value={String(summary.certificateCount)}
        />
        <SummaryTile
          label="Numbered releases"
          value={String(summary.releaseCount)}
        />
        <SummaryTile
          label="Latest edition"
          value={summary.latestEdition || "-"}
        />
        <SummaryTile label="Collector status" value="Active Collector" />
      </s-grid>
      {summary.latestProduct ? (
        <s-text color="subdued">
          Latest addition: {summary.latestProduct}
        </s-text>
      ) : null}
    </s-section>
  );
}

function SummaryTile({label, value}) {
  return (
    <s-box
      padding="base"
      border="base"
      borderRadius="base"
      background="subdued"
    >
      <s-stack gap="small-200">
        <s-text color="subdued">{label}</s-text>
        <s-text type="strong">{value}</s-text>
      </s-stack>
    </s-box>
  );
}

function CertificateCard({certificate}) {
  const hasPdf = Boolean(certificate.certificate_pdf_url);
  const hasPrint = Boolean(certificate.certificate_print_jpg_url);
  const hasPreview = Boolean(certificate.certificate_preview_image_url);

  return (
    <s-box
      padding="base"
      border="base"
      borderRadius="base"
      background="subdued"
    >
      <s-stack gap="base">
        <s-stack direction="inline" gap="small">
          <s-badge tone="neutral">Numbered Collector Release</s-badge>
          <s-badge tone="neutral">Official Certificate</s-badge>
          <s-badge tone="neutral">Verified Sports Cave Record</s-badge>
        </s-stack>

        <s-grid
          gridTemplateColumns="repeat(auto-fit, minmax(260px, 1fr))"
          gap="base"
        >
          <s-stack gap="base">
            <s-stack gap="small-400">
              <s-heading>
                {certificate.product_title || "Sports Cave limited edition"}
              </s-heading>
              {certificate.variant_title ? (
                <s-text color="subdued">{certificate.variant_title}</s-text>
              ) : null}
            </s-stack>

            <s-grid
              gridTemplateColumns="repeat(auto-fit, minmax(150px, 1fr))"
              gap="base"
            >
              <CertificateDetail
                label="Edition"
                value={certificate.edition_display}
              />
              <CertificateDetail
                label="Order"
                value={certificate.shopify_order_name}
              />
              <CertificateDetail
                label="Purchased"
                value={certificate.purchase_date_display}
              />
              <CertificateIdDetail value={certificate.certificate_id} />
            </s-grid>
          </s-stack>

          <s-stack gap="base">
            {hasPreview ? (
              <s-image
                src={certificate.certificate_preview_image_url}
                alt={`Certificate preview for ${
                  certificate.product_title || "Sports Cave artwork"
                }`}
                aspectRatio="16/9"
                objectFit="cover"
                loading="lazy"
              ></s-image>
            ) : (
              <s-box padding="base" border="base" borderRadius="base">
                <s-stack gap="small-200">
                  <s-text type="strong">
                    Certificate preview coming soon
                  </s-text>
                  <s-text color="subdued">
                    Your official PDF certificate is still available below.
                  </s-text>
                </s-stack>
              </s-box>
            )}
          </s-stack>
        </s-grid>

        <s-stack direction="inline" gap="base">
          {hasPdf ? (
            <CertificateAssetButton
              href={certificate.certificate_pdf_url}
              label="View Certificate"
              variant="primary"
            />
          ) : null}
          {hasPrint ? (
            <CertificateAssetButton
              href={certificate.certificate_print_jpg_url}
              label="Download Print Certificate"
            />
          ) : null}
          {hasPdf ? (
            <CertificateAssetButton
              href={certificate.certificate_pdf_url}
              label="Download PDF"
            />
          ) : null}
          {!hasPdf ? (
            <s-badge tone="neutral">Certificate processing</s-badge>
          ) : null}
        </s-stack>

        {hasPdf || hasPrint ? (
          <s-text color="subdued">
            Opens in a new tab. Use your browser save or download option to
            print.
          </s-text>
        ) : null}
      </s-stack>
    </s-box>
  );
}

function CertificateAssetButton({href, label, variant = "secondary"}) {
  return (
    <s-button href={href} target="_blank" variant={variant}>
      {label}
    </s-button>
  );
}

function CertificateDetail({label, value}) {
  return (
    <s-stack gap="small-100">
      <s-text color="subdued">{label}</s-text>
      <s-text type="strong">{value || "-"}</s-text>
    </s-stack>
  );
}

function CertificateIdDetail({value}) {
  return (
    <s-stack gap="small-100">
      <s-text color="subdued">Certificate ID</s-text>
      <s-stack direction="inline" gap="small" alignItems="center">
        <s-text type="strong">{value || "-"}</s-text>
        {value ? <s-clipboard-item text={value}></s-clipboard-item> : null}
      </s-stack>
    </s-stack>
  );
}
