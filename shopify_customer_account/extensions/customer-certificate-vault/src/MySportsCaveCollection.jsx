/** @jsxImportSource preact */
/// <reference types="@shopify/ui-extensions/customer-account.page.render" />
import "@shopify/ui-extensions/preact";
import {render} from "preact";
import {useEffect, useState} from "preact/hooks";

import {
  collectCertificates,
  customerSafeErrorMessage,
} from "./legacy-certificate-utils.js";
import {attachPurchasedArtwork} from "./collection-artwork-utils.js";

export const COLLECTOR_VAULT_REDESIGN_ENABLED = false;

const API_VERSION = "2026-04";
const SHOP_LATEST_DROPS_URL = "https://www.sportscaveshop.com";
const REVIEWS_PAGE_URL = "https://www.sportscaveshop.com/pages/reviews";
const CERTIFICATES_QUERY = `query SportsCaveCustomerCertificates {
  customer {
    id
    orders(first: 50, reverse: true) {
      nodes {
        id
        name
        processedAt
        lineItems(first: 100) {
          nodes {
            id
            name
            productId
            variantId
            sku
            image {
              url
              altText
              width
              height
            }
          }
        }
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
  const [selectedCertificate, setSelectedCertificate] = useState(null);

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
          const requestError = Object.assign(
            new Error("Customer Account API request failed."),
            {status: response.status},
          );
          throw requestError;
        }
        const graphQLErrors = Reflect.get(payload, "errors");
        if (Array.isArray(graphQLErrors) && graphQLErrors.length) {
          const requestError = Object.assign(
            new Error("Customer Account API query failed."),
            {graphQLErrors},
          );
          throw requestError;
        }

        const responseData = Reflect.get(payload, "data") || {};
        const customer = responseData.customer || {};
        const orderNodes = customer.orders?.nodes || [];
        const rows = attachPurchasedArtwork(
          collectCertificates(orderNodes, customer),
          orderNodes,
          customer,
        );
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

  const firstCertificate = certificates[0] || null;

  return (
    <s-page>
      <s-grid
        gridTemplateColumns="minmax(0, 1200px)"
        justifyContent="center"
        inlineSize="100%"
      >
        <s-stack gap="large">
          {status === "loading" ? <LoadingState /> : null}
          {status === "error" ? (
            <ErrorState
              message={errorMessage}
              onRetry={() => setRetryKey((value) => value + 1)}
            />
          ) : null}
          {status === "ready" ? (
            <ReviewBanner certificate={firstCertificate} />
          ) : null}
          {status === "ready" && certificates.length === 0 ? (
            <EmptyState />
          ) : null}
          {status === "ready" && certificates.length > 0 ? (
            <CertificateGallery
              certificates={certificates}
              onOpen={setSelectedCertificate}
            />
          ) : null}
        </s-stack>
      </s-grid>
      <CertificateViewer
        certificate={selectedCertificate}
        onClose={() => setSelectedCertificate(null)}
      />
    </s-page>
  );
}

function ReviewBanner({certificate}) {
  const thumbnailUrl = certificate?.purchased_image_url
    || certificate?.certificate_preview_image_url;
  const thumbnailAlt = certificate?.purchased_image_url
    ? certificate.purchased_image_alt
    : `Certificate preview for ${
      certificate?.product_title || "Sports Cave certificate"
    }`;
  const hasThumbnail = Boolean(thumbnailUrl);

  return (
    <s-box
      padding="base"
      border="base"
      borderRadius="base"
      background="subdued"
    >
      <s-grid
        gridTemplateColumns="repeat(auto-fit, minmax(min(100%, 420px), 1fr))"
        gap="base"
        alignItems="center"
      >
        <s-grid
          gridTemplateColumns={hasThumbnail
            ? "96px minmax(0, 1fr)"
            : "minmax(0, 1fr)"}
          gap="base"
          alignItems="center"
        >
          {hasThumbnail ? (
            <s-box
              background="base"
              border="base"
              borderRadius="small"
              overflow="hidden"
            >
              <s-image
                src={thumbnailUrl}
                alt={thumbnailAlt}
                aspectRatio="1/1"
                objectFit="contain"
                loading="lazy"
                sizes="96px"
              ></s-image>
            </s-box>
          ) : null}
          <s-stack gap="small-400">
            <s-heading>How does it look in your space?</s-heading>
            <s-text color="subdued">
              Share a quick review and help another fan see the real thing.
            </s-text>
            <s-box accessibilityVisibility="hidden">
              <s-stack direction="inline" gap="small-200">
                {[1, 2, 3, 4, 5].map((star) => (
                  <s-icon
                    key={star}
                    type="star"
                    tone="warning"
                  ></s-icon>
                ))}
              </s-stack>
            </s-box>
          </s-stack>
        </s-grid>
        <s-stack
          direction="inline"
          justifyContent="end"
          alignItems="center"
        >
          <s-link
            href={REVIEWS_PAGE_URL}
            target="_blank"
            accessibilityLabel="Leave a review on Sports Cave"
          >
            Leave a Review
          </s-link>
        </s-stack>
      </s-grid>
    </s-box>
  );
}

function LoadingState() {
  return (
    <s-stack gap="base">
      <s-stack direction="inline" gap="small" alignItems="center">
        <s-spinner size="base" accessibilityLabel="Loading certificates">
        </s-spinner>
        <s-text color="subdued">Loading your certificates...</s-text>
      </s-stack>
      <s-grid
        gridTemplateColumns="repeat(auto-fit, minmax(min(100%, 320px), 1fr))"
        gap="base"
        alignItems="stretch"
      >
        {[0, 1, 2].map((index) => (
          <s-box
            key={index}
            padding="base"
            border="base"
            borderRadius="base"
            background="subdued"
          >
            <s-stack gap="base">
              <s-box
                minBlockSize="190px"
                background="base"
                borderRadius="small"
              ></s-box>
              <s-skeleton-paragraph></s-skeleton-paragraph>
              <s-skeleton-paragraph></s-skeleton-paragraph>
            </s-stack>
          </s-box>
        ))}
      </s-grid>
    </s-stack>
  );
}

function EmptyState() {
  return (
    <s-box
      padding="large"
      border="base"
      borderRadius="base"
      background="subdued"
    >
      <s-stack gap="base">
        <s-heading>Your collection is waiting</s-heading>
        <s-text color="subdued">
          Your numbered Sports Cave certificates will appear here.
        </s-text>
        <s-button
          href={SHOP_LATEST_DROPS_URL}
          target="_blank"
          variant="secondary"
        >
          Shop Latest Drops
        </s-button>
      </s-stack>
    </s-box>
  );
}

function ErrorState({message, onRetry}) {
  return (
    <s-banner heading="Collection unavailable" tone="critical">
      <s-stack gap="base">
        <s-text>{message || "We could not load your certificates."}</s-text>
        <s-button variant="secondary" onClick={onRetry}>
          Try again
        </s-button>
      </s-stack>
    </s-banner>
  );
}

function CertificateGallery({certificates, onOpen}) {
  return (
    <s-grid
      gridTemplateColumns="repeat(auto-fit, minmax(min(100%, 320px), 1fr))"
      gap="base"
      alignItems="stretch"
    >
      {certificates.map((certificate) => (
        <CertificateCard
          key={certificate.key}
          certificate={certificate}
          onOpen={onOpen}
        />
      ))}
    </s-grid>
  );
}

function CertificateCard({certificate, onOpen}) {
  const hasPdf = Boolean(certificate.certificate_pdf_url);
  const hasPrint = Boolean(certificate.certificate_print_jpg_url);
  const title = certificate.product_title || "Sports Cave limited edition";

  return (
    <s-box
      padding="base"
      border="base"
      borderRadius="base"
      background="subdued"
      blockSize="100%"
    >
      <s-grid
        gridTemplateRows="auto minmax(0, 1fr) auto"
        gap="base"
        blockSize="100%"
      >
        {hasPdf ? (
          <s-clickable
            accessibilityLabel={`View certificate for ${title}`}
            command="--show"
            commandFor="certificate-viewer"
            onClick={() => onOpen(certificate)}
            borderRadius="small"
          >
            <CertificatePreview certificate={certificate} />
          </s-clickable>
        ) : (
          <CertificatePreview certificate={certificate} />
        )}

        <s-stack gap="small-400">
          <s-heading>{title}</s-heading>
          {certificate.variant_title ? (
            <s-text color="subdued">{certificate.variant_title}</s-text>
          ) : null}
          {certificate.edition_display ? (
            <s-text type="strong">
              {editionLabel(certificate.edition_display)}
            </s-text>
          ) : null}
          {certificate.purchase_date_display ? (
            <s-text color="subdued">
              Purchased {certificate.purchase_date_display}
            </s-text>
          ) : null}
        </s-stack>

        <s-grid
          gridTemplateColumns="repeat(auto-fit, minmax(min(100%, 140px), 1fr))"
          gap="small"
          alignItems="stretch"
        >
          {hasPdf ? (
            <s-button
              variant="primary"
              command="--show"
              commandFor="certificate-viewer"
              onClick={() => onOpen(certificate)}
            >
              View Certificate
            </s-button>
          ) : null}
          {hasPdf ? (
            <s-button
              href={certificate.certificate_pdf_url}
              target="_blank"
              variant="secondary"
            >
              Download PDF
            </s-button>
          ) : null}
          {hasPrint ? (
            <s-button
              href={certificate.certificate_print_jpg_url}
              target="_blank"
              variant="secondary"
            >
              Download Print
            </s-button>
          ) : null}
          {!hasPdf ? (
            <s-badge tone="neutral">Certificate processing</s-badge>
          ) : null}
        </s-grid>
      </s-grid>
    </s-box>
  );
}

function CertificatePreview({certificate, eager = false}) {
  const title = certificate.product_title || "Sports Cave artwork";
  const hasDownload = Boolean(
    certificate.certificate_pdf_url
      || certificate.certificate_print_jpg_url,
  );
  if (certificate.certificate_preview_image_url) {
    return (
      <s-box
        background="base"
        border="base"
        borderRadius="small"
        overflow="hidden"
      >
        <s-image
          src={certificate.certificate_preview_image_url}
          alt={`Certificate preview for ${title}`}
          aspectRatio="16/9"
          objectFit="contain"
          loading={eager ? "eager" : "lazy"}
          sizes="(min-width: 1100px) 33vw, (min-width: 700px) 50vw, 100vw"
        ></s-image>
      </s-box>
    );
  }

  return (
    <s-box
      minBlockSize={eager ? "320px" : "190px"}
      padding="large"
      background="base"
      border="base"
      borderRadius="small"
    >
      <s-stack gap="small-200" alignItems="center" justifyContent="center">
        <s-text type="strong">Certificate preview unavailable</s-text>
        <s-text color="subdued">
          {hasDownload
            ? "Your certificate download is still available."
            : "Your certificate is still processing."}
        </s-text>
      </s-stack>
    </s-box>
  );
}

function CertificateViewer({certificate, onClose}) {
  const modalId = "certificate-viewer";
  const title = certificate?.product_title || "Certificate";

  return (
    <s-modal
      id={modalId}
      heading={title}
      accessibilityLabel={`Certificate viewer for ${title}`}
      size="max"
      padding="base"
      onAfterHide={onClose}
    >
      {certificate ? (
        <s-grid
          gridTemplateColumns="repeat(auto-fit, minmax(min(100%, 320px), 1fr))"
          gap="large"
          alignItems="start"
        >
          <CertificatePreview certificate={certificate} eager />
          <s-stack gap="large">
            <s-stack gap="small-400">
              <s-heading>{title}</s-heading>
              {certificate.variant_title ? (
                <s-text color="subdued">{certificate.variant_title}</s-text>
              ) : null}
              {certificate.edition_display ? (
                <s-text type="strong">
                  {editionLabel(certificate.edition_display)}
                </s-text>
              ) : null}
              {certificate.purchase_date_display ? (
                <s-text color="subdued">
                  Purchased {certificate.purchase_date_display}
                </s-text>
              ) : null}
            </s-stack>
            <s-grid
              gridTemplateColumns="repeat(auto-fit, minmax(min(100%, 170px), 1fr))"
              gap="small"
            >
              {certificate.certificate_print_jpg_url ? (
                <s-button
                  href={certificate.certificate_print_jpg_url}
                  target="_blank"
                  variant="secondary"
                >
                  Download Print
                </s-button>
              ) : null}
            </s-grid>
          </s-stack>
        </s-grid>
      ) : (
        <s-text color="subdued">Choose a certificate to view it.</s-text>
      )}
      {certificate?.certificate_pdf_url ? (
        <s-button
          slot="primary-action"
          href={certificate.certificate_pdf_url}
          target="_blank"
        >
          Download Certificate
        </s-button>
      ) : null}
      <s-button
        slot={certificate?.certificate_pdf_url
          ? "secondary-actions"
          : "primary-action"}
        command="--hide"
        commandFor={modalId}
      >
        Close
      </s-button>
    </s-modal>
  );
}

function editionLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const parts = raw.split("/").map((part) => part.trim());
  if (parts.length === 2 && parts[0] && parts[1]) {
    return `Edition ${parts[0]} of ${parts[1]}`;
  }
  return raw.toLowerCase().startsWith("edition")
    ? raw
    : `Edition ${raw}`;
}
