/** @jsxImportSource preact */
/// <reference types="@shopify/ui-extensions/customer-account.page.render" />
import "@shopify/ui-extensions/preact";
import {render} from "preact";
import {useEffect, useState} from "preact/hooks";
import {useApi} from "@shopify/ui-extensions/customer-account/preact";

import {
  collectCertificates,
  customerSafeErrorMessage,
} from "./legacy-certificate-utils.js";
import {attachPurchasedArtwork} from "./collection-artwork-utils.js";
import {formatFramePrice, frameCartInput} from "./vault-utils.js";

export const COLLECTOR_VAULT_REDESIGN_ENABLED = false;

const API_VERSION = "2026-04";
const DEFAULT_API_BASE_URL = "https://sports-cave-image-factory.onrender.com";
const SHOP_LATEST_DROPS_URL = "https://www.sportscaveshop.com";
const REVIEWS_PAGE_URL = "https://www.sportscaveshop.com/pages/reviews";
const CART_CREATE_MUTATION = `mutation SportsCaveFramedCertificateCart($input: CartInput!) {
  cartCreate(input: $input) {
    cart { id checkoutUrl }
    userErrors { field message }
  }
}`;
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
  const api = useApi();
  const [status, setStatus] = useState("loading");
  const [certificates, setCertificates] = useState([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [selectedCertificate, setSelectedCertificate] = useState(null);
  const apiBaseUrl = configuredApiBaseUrl(api);

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
        api={api}
        apiBaseUrl={apiBaseUrl}
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

function CertificateViewer({certificate, api, apiBaseUrl, onClose}) {
  const modalId = "certificate-viewer";
  const title = certificate?.product_title || "Certificate";
  const [frameOffer, setFrameOffer] = useState({
    status: "idle",
    product: null,
    certificateReference: "",
  });
  const [checkoutState, setCheckoutState] = useState({
    status: "idle",
    message: "",
    checkoutUrl: "",
  });

  useEffect(() => {
    const controller = new AbortController();
    setCheckoutState({status: "idle", message: "", checkoutUrl: ""});
    if (!certificate) {
      setFrameOffer({
        status: "idle",
        product: null,
        certificateReference: "",
      });
      return () => controller.abort();
    }

    setFrameOffer({
      status: "loading",
      product: null,
      certificateReference: "",
    });
    async function loadFrameOffer() {
      try {
        const payload = await vaultRequest(
          api,
          apiBaseUrl,
          "/api/collector-vault/bootstrap",
          {signal: controller.signal},
        );
        if (controller.signal.aborted) return;
        const ownedCertificate = matchingFrameCertificate(
          payload.certificates,
          certificate,
        );
        const product = payload.frame_product;
        if (
          !ownedCertificate?.reference
          || !product?.available
          || !product?.variant_id
        ) {
          setFrameOffer({
            status: "unavailable",
            product: null,
            certificateReference: "",
          });
          return;
        }
        setFrameOffer({
          status: "ready",
          product,
          certificateReference: ownedCertificate.reference,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        setFrameOffer({
          status: "error",
          product: null,
          certificateReference: "",
        });
      }
    }
    loadFrameOffer();
    return () => controller.abort();
  }, [api, apiBaseUrl, certificate?.key]);

  const addFramedCertificate = async () => {
    if (
      frameOffer.status !== "ready"
      || checkoutState.status === "adding"
    ) {
      return;
    }
    const product = frameOffer.product;
    setCheckoutState({
      status: "adding",
      message: "Preparing secure checkout...",
      checkoutUrl: "",
    });
    try {
      const request = await vaultRequest(
        api,
        apiBaseUrl,
        "/api/collector-vault/frame/request",
        {
          method: "POST",
          body: {
            certificate_reference: frameOffer.certificateReference,
            frame_variant_id: product.variant_id,
            idempotency_key: frameIdempotencyKey(certificate),
            allow_repeat: false,
          },
        },
      );
      if (request.status === "ordered") {
        setCheckoutState({
          status: "ordered",
          message: "Your framed certificate has already been ordered.",
          checkoutUrl: "",
        });
        return;
      }
      if (request.checkout_url) {
        setCheckoutState({
          status: "ready",
          message: "Your secure checkout is ready.",
          checkoutUrl: request.checkout_url,
        });
        return;
      }
      const cartPayload = await api.query(CART_CREATE_MUTATION, {
        variables: {
          input: frameCartInput(
            product.variant_id,
            String(request.request_reference),
          ),
        },
      });
      const cartResult = cartPayload?.data?.cartCreate;
      const cartError = cartResult?.userErrors?.[0]?.message;
      if (cartError || !cartResult?.cart?.checkoutUrl) {
        throw new Error(cartError || "Shopify checkout could not be created.");
      }
      await vaultRequest(
        api,
        apiBaseUrl,
        "/api/collector-vault/frame/cart-created",
        {
          method: "POST",
          body: {
            request_reference: request.request_reference,
            cart_id: cartResult.cart.id,
            checkout_url: cartResult.cart.checkoutUrl,
          },
        },
      );
      setCheckoutState({
        status: "ready",
        message: "Your secure checkout is ready.",
        checkoutUrl: cartResult.cart.checkoutUrl,
      });
    } catch (_error) {
      setCheckoutState({
        status: "error",
        message: "Framed checkout is temporarily unavailable.",
        checkoutUrl: "",
      });
    }
  };

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
            {frameOffer.status === "loading" ? (
              <s-stack direction="inline" gap="small" alignItems="center">
                <s-spinner
                  size="small"
                  accessibilityLabel="Loading framed certificate offer"
                ></s-spinner>
                <s-text color="subdued">
                  Loading display options...
                </s-text>
              </s-stack>
            ) : null}
            {frameOffer.status === "ready" ? (
              <FramedCertificateOffer
                product={frameOffer.product}
                checkoutState={checkoutState}
                onAdd={addFramedCertificate}
                formatNumber={api.i18n.formatNumber}
              />
            ) : null}
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

function FramedCertificateOffer({
  product,
  checkoutState,
  onAdd,
  formatNumber,
}) {
  const price = formatFramePrice(
    product.contextual_price,
    formatNumber,
  );
  const inclusions = Array.isArray(product.inclusions)
    ? product.inclusions.slice(0, 3)
    : [];

  return (
    <s-box
      padding="base"
      border="base"
      borderRadius="base"
      background="subdued"
    >
      <s-stack gap="base">
        <s-heading>Display It Framed</s-heading>
        {product.image?.url ? (
          <s-image
            src={product.image.url}
            alt={product.image.alt_text || `${product.title} product image`}
            aspectRatio="4/3"
            objectFit="contain"
            loading="lazy"
            sizes="(min-width: 760px) 30vw, 100vw"
          ></s-image>
        ) : null}
        <s-heading>{product.title}</s-heading>
        {inclusions.length ? (
          <s-stack gap="small-200">
            {inclusions.map((inclusion) => (
              <s-text key={inclusion}>{inclusion}</s-text>
            ))}
          </s-stack>
        ) : null}
        {checkoutState.checkoutUrl ? (
          <s-button
            variant="primary"
            href={checkoutState.checkoutUrl}
            target="_blank"
          >
            Continue to Secure Checkout
          </s-button>
        ) : checkoutState.status === "ordered" ? (
          <s-badge tone="neutral" icon="check">
            Framed certificate ordered
          </s-badge>
        ) : (
          <s-button
            variant="primary"
            onClick={onAdd}
            loading={checkoutState.status === "adding"}
          >
            Add Framed Certificate — {price}
          </s-button>
        )}
        {checkoutState.message ? (
          <s-text color={checkoutState.status === "error"
            ? "base"
            : "subdued"}
          >
            {checkoutState.message}
          </s-text>
        ) : null}
      </s-stack>
    </s-box>
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

function configuredApiBaseUrl(api) {
  const configured = String(api.settings?.value?.api_base_url || "").trim();
  return (configured || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}

function matchingFrameCertificate(items, certificate) {
  const certificateId = String(certificate?.certificate_id || "").trim();
  const orderName = String(certificate?.shopify_order_name || "").trim();
  if (!certificateId) return null;
  const matches = (Array.isArray(items) ? items : []).filter((item) => (
    String(item?.certificate_id || "").trim() === certificateId
    && (
      !orderName
      || String(item?.order_name || "").trim() === orderName
    )
  ));
  return matches.length === 1 ? matches[0] : null;
}

function frameIdempotencyKey(certificate) {
  const source = String(
    certificate?.key
    || `${certificate?.shopify_order_name}|${certificate?.certificate_id}`,
  );
  let hash = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `frame-${(hash >>> 0).toString(16)}`;
}

async function vaultRequest(api, apiBaseUrl, path, options = {}) {
  const method = options.method || "GET";
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const token = await api.sessionToken.get();
    const response = await fetch(`${apiBaseUrl}${path}`, {
      method,
      signal: options.signal,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "X-Sports-Cave-Request": "customer-account-extension",
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }
    if (response.status === 401 && attempt === 0) continue;
    if (!response.ok || payload.ok === false) {
      throw Object.assign(
        new Error("The framed certificate request could not be completed."),
        {status: response.status},
      );
    }
    return payload;
  }
  throw Object.assign(
    new Error("The framed certificate request could not be authenticated."),
    {status: 401},
  );
}
