/** @jsxImportSource preact */
/// <reference types="@shopify/ui-extensions/customer-account.page.render" />
import "@shopify/ui-extensions/preact";
import {render} from "preact";
import {useEffect, useRef, useState} from "preact/hooks";
import {useApi} from "@shopify/ui-extensions/customer-account/preact";

import {
  collectCertificates,
  customerSafeErrorMessage,
} from "./legacy-certificate-utils.js";
import {attachPurchasedArtwork} from "./collection-artwork-utils.js";
import {loadCollectionOrders} from "./collection-order-pages.js";
import {accountCountry, compactTitle, compactVariant, pairedProducts, comparePrice, UPSELL_QUERY, FRAME_PRICE_QUERY, marketFrames} from "./account-commerce.js";
import {collectionThumbnail} from "./collection-image-utils.js";
import {timedOperation, operationForPath} from "./collection-performance.js";
import {AccountReview} from "./AccountReview.jsx";
import {formatFramePrice, frameCartInput} from "./vault-utils.js";
import {createFrameOfferLoader} from "./frame-offer-loader.js";

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
const CERTIFICATES_QUERY = `query SportsCaveCustomerCertificates($after: String) {
  customer {
    id
    orders(first: 50, reverse: true, after: $after) {
      pageInfo { hasNextPage endCursor }
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
  const [activeKey, setActiveKey] = useState("");
  const apiBaseUrl = configuredApiBaseUrl(api);
  const frameLoader = useRef(null);
  if (!frameLoader.current || frameLoader.current.api !== api || frameLoader.current.base !== apiBaseUrl) {
    frameLoader.current = {api, base: apiBaseUrl, loader: createFrameOfferLoader({
      bootstrap: () => vaultRequest(api, apiBaseUrl, "/api/collector-vault/bootstrap?include_review=false"),
      prices: async (product, country) => {
        const result = /** @type {any} */ (await timedOperation(api, apiBaseUrl, 'frame_prices', async () => {
          const response = await api.query(FRAME_PRICE_QUERY, {variables: {id: product.product_id, country}});
          if (response.errors?.length) throw new Error("Frame prices unavailable");
          return response;
        }));
        return marketFrames(product, result.data?.product);
      },
    })};
  }
  const offerLoader = frameLoader.current.loader;

  useEffect(() => {
    let mounted = true;

    async function loadCertificates() {
      setStatus("loading");
      setErrorMessage("");
      try {
        const fetchCustomerPage = (_url, options) => fetch(`shopify://customer-account/api/${API_VERSION}/graphql.json`, options);
        const {customer, orders: orderNodes} = await timedOperation(api, apiBaseUrl, 'collection_orders', () => loadCollectionOrders(fetchCustomerPage, API_VERSION, CERTIFICATES_QUERY));
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
  const activeCertificate = certificates.find(item => item.key === activeKey) || firstCertificate;
  const country = useCountry(api);
  const [reviewLoad, setReviewLoad] = useState({status: "loading", prompt: null});
  const [reviewRetry, setReviewRetry] = useState(0);
  const reviewPrompt = reviewLoad.prompt;
  const [vaultData, setVaultData] = useState(null);

  useEffect(() => {
    let active = true;
    setVaultData(null);
    offerLoader.bootstrap()
      .then((payload) => {
        if (!active) return;
        setVaultData(payload);
        // Fallback for an older API during a rolling release.
        if (payload.review_prompt) setReviewLoad({status: "ready", prompt: payload.review_prompt});
      }).catch(() => {}); // Existing assets remain usable if offers are unavailable.
    return () => { active = false; };
  }, [retryKey, offerLoader]);

  useEffect(() => {
    const controller = new AbortController();
    setReviewLoad({status: "loading", prompt: null});
    vaultRequest(api, apiBaseUrl, "/api/collector-vault/review-prompt", {signal: controller.signal})
      .then(payload => {
        if (!controller.signal.aborted) setReviewLoad({status: "ready", prompt: payload.review_prompt || null});
      }).catch(() => {
        if (!controller.signal.aborted) setReviewLoad(current => current.prompt ? current : {status: "error", prompt: null});
      });
    return () => controller.abort();
  }, [api, apiBaseUrl, retryKey, reviewRetry]);

  useEffect(() => {
    // Prepare country-specific prices before the popup is opened; deduplicated
    // with its request if a customer opens it before warming has finished.
    offerLoader.context(country).catch(() => {});
  }, [country, offerLoader, retryKey]);

  useEffect(() => {
    if (status !== "ready" || !vaultData) return;
    const payload = vaultData;
        setCertificates((items) => items.map((certificate) => {
          const owned = matchingFrameCertificate(payload.certificates, certificate);
          const preview = vaultAssetUrl(apiBaseUrl, owned?.preview_url);
          return {...certificate,
            frame_preview_url: preview ? `${preview}&frame=black` : "",
            certificate_preview_image_url: certificate.certificate_preview_image_url || preview,
            certificate_print_jpg_url: certificate.certificate_print_jpg_url || vaultAssetUrl(apiBaseUrl, owned?.print_url),
            certificate_download_url: vaultAssetUrl(apiBaseUrl, owned?.print_url),
          };
        }));
  }, [status, vaultData, apiBaseUrl]);

  return (
    <s-query-container>
      <s-grid
        gridTemplateColumns="minmax(0, 1fr)"
        justifyContent="center"
        inlineSize="100%"
      >
        <s-stack gap="base">
          {status === "loading" ? <LoadingState /> : null}
          {status === "error" ? (
            <ErrorState
              message={errorMessage}
              onRetry={() => setRetryKey((value) => value + 1)}
            />
          ) : null}
          {status === "ready" ? (
            <AccountReview api={api} certificate={certificates.find(item => item.shopify_product_id === reviewPrompt?.shopify_product_id) || firstCertificate} prompt={reviewPrompt} reviewStatus={reviewLoad.status} onRetryReview={() => setReviewRetry(value => value + 1)} request={(path, options) => vaultRequest(api, apiBaseUrl, path, options)} />
          ) : null}
          {status === "ready" && certificates.length === 0 ? (
            <EmptyState />
          ) : null}
          {status === "ready" && certificates.length > 0 ? (
            <CollectionShowcase
              certificates={certificates}
              activeCertificate={activeCertificate}
              onSelect={setActiveKey}
              onOpen={(certificate, framingOnly = false) => setSelectedCertificate({...certificate, framingOnly})}
            />
          ) : null}
          {status === "ready" && certificates.length > 0 ? (
            <CollectionUpsells key={`${country}-${activeCertificate?.shopify_product_id || activeCertificate?.key}`} api={api} apiBaseUrl={apiBaseUrl} country={country} certificate={activeCertificate} />
          ) : null}
        </s-stack>
      </s-grid>
      <CertificateViewer
        certificate={selectedCertificate}
        api={api}
        apiBaseUrl={apiBaseUrl}
        country={country}
        offerLoader={offerLoader}
        onClose={() => setSelectedCertificate(null)}
      />
    </s-query-container>
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
      gridTemplateColumns="@container (inline-size > 750px) 1fr 1fr, 1fr"
      gap="large"
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

function CollectionShowcase({certificates, activeCertificate, onSelect, onOpen}) {
  if (!activeCertificate) return null;
  const active = activeCertificate;
  const index = Math.max(0, certificates.findIndex(item => item.key === active.key));
  const browse = offset => onSelect(certificates[(index + offset + certificates.length) % certificates.length].key);
  const edition = item => editionLabel(item.edition_display).replace(/^Edition #/, "");
  const count = `${certificates.length} numbered ${certificates.length === 1 ? "edition" : "editions"}`;
  const preview = active.certificate_preview_image_url;
  const card = (item, mobile = false) => <s-grid gridTemplateColumns={mobile ? "minmax(0, 1fr) minmax(0, 1fr)" : "80px minmax(0, 1fr) auto"} gap="small" alignItems="center">
    {item.purchased_image_url ? <s-image src={collectionThumbnail(item.purchased_image_url)} alt={item.purchased_image_alt || item.product_title} aspectRatio="4/3" objectFit={mobile ? "contain" : "cover"} loading="eager" /> : <s-box minBlockSize="48px" />}
    <s-stack gap="small-400"><s-text type="strong">{compactTitle(item.product_title)}</s-text><s-text color="subdued">{compactVariant(item.variant_title)}</s-text>{mobile ? <s-text>{edition(item)}</s-text> : null}</s-stack>
    {!mobile ? <s-text>{edition(item)} ›</s-text> : null}
  </s-grid>;
  return <s-stack gap="base">
    <s-grid gridTemplateColumns="@container (inline-size > 850px) 'minmax(0, 0.7fr) minmax(0, 1.3fr)', 'minmax(0, 1fr)'" gap="base" alignItems="start">
      <s-stack gap="base">
        <s-box display="@container (inline-size > 850px) auto, none"><s-stack gap="small-400"><s-heading>My Collection</s-heading><s-text type="emphasis">{count}</s-text></s-stack></s-box>
        <s-box display="@container (inline-size > 850px) auto, none"><s-stack gap="small-400">
          {certificates.map(item => <s-clickable key={item.key} onClick={() => onSelect(item.key)}
            accessibilityLabel={`${compactTitle(item.product_title)}, ${compactVariant(item.variant_title)}, edition ${edition(item)}${item.key === active.key ? ", selected" : ""}`}
            border={item.key === active.key ? "large" : "none"} background={item.key === active.key ? "subdued" : "transparent"}
            borderRadius="large" padding="small" minBlockSize="72px">{card(item)}</s-clickable>)}
        </s-stack></s-box>
        <s-box display="@container (inline-size > 850px) none, auto">
          <s-stack gap="small-400">
            <s-scroll-box key={active.key} overflow="hidden auto" accessibilityLabel="Swipe through your editions, then tap an edition to view its certificate">
              <s-stack direction="inline" gap="small" minInlineSize={`${certificates.length * 300}px`}>
                {certificates.slice(index).concat(certificates.slice(0, index)).map(item => <s-clickable key={item.key}
                  onClick={() => onSelect(item.key)} minInlineSize="280px" maxInlineSize="280px" accessibilityLabel={`${compactTitle(item.product_title)}, ${compactVariant(item.variant_title)}, edition ${edition(item)}${item.key === active.key ? ", selected" : ""}`}
                  border={item.key === active.key ? "large" : "base"} borderRadius="large" padding="small" background="subdued">
                  {card(item, true)}
                </s-clickable>)}
              </s-stack>
            </s-scroll-box>
            {certificates.length > 1 ? <s-grid gridTemplateColumns="44px minmax(0, 1fr) 44px" alignItems="center">
              <s-clickable accessibilityLabel="Previous edition" onClick={() => browse(-1)} minInlineSize="44px" minBlockSize="44px" padding="small"><s-icon type="chevron-left" size="large" /></s-clickable>
              <s-stack alignItems="center" accessibilityLabel={`Edition ${index + 1} of ${certificates.length}`}><s-text color="subdued">{index + 1}/{certificates.length}</s-text></s-stack>
              <s-clickable accessibilityLabel="Next edition" onClick={() => browse(1)} minInlineSize="44px" minBlockSize="44px" padding="small"><s-icon type="chevron-right" size="large" /></s-clickable>
            </s-grid> : null}
          </s-stack>
        </s-box>
      </s-stack>
      <s-stack gap="small">
        {preview ? <s-image src={preview} alt={`Certificate of authenticity for ${active.product_title}, edition ${edition(active)}`} aspectRatio="1.415" objectFit="contain" loading="eager" sizes="(min-width: 850px) 70vw, 100vw" /> : <CertificatePreview certificate={{...active, frame_preview_url: ""}} eager />}
        <s-grid gridTemplateColumns="minmax(0, 1.1fr) minmax(0, 1fr)" gap="small" alignItems="center">
          {active.certificate_pdf_url ? <s-button inlineSize="fill" variant="primary" command="--show" commandFor="certificate-viewer" onClick={() => onOpen(active, true)}>Frame certificate</s-button> : <s-badge>Certificate processing</s-badge>}
          {active.certificate_pdf_url ? <s-button inlineSize="fill" variant="secondary" command="--show" commandFor="certificate-viewer" onClick={() => onOpen(active)}>View certificate</s-button> : null}
        </s-grid>
        {active.certificate_download_url ? <s-link href={active.certificate_download_url} target="auto">Download printable certificate</s-link> : null}
        {active.frame_preview_url ? <s-box display="none" accessibilityVisibility="hidden"><s-image src={active.frame_preview_url} srcSet={`${active.frame_preview_url}&w=400 400w, ${active.frame_preview_url}&w=1000 1000w`} sizes="(min-width: 520px) 560px, 160px" alt="" loading="eager" /></s-box> : null}
      </s-stack>
    </s-grid>
    <s-divider />
  </s-stack>;
}

function CertificateCard({certificate, onOpen}) {
  const hasPdf = Boolean(certificate.certificate_pdf_url);
  const hasPrint = Boolean(certificate.certificate_print_jpg_url);
  const title = certificate.product_title || "Sports Cave limited edition";

  return (
    <s-box
      padding="small"
      border="base"
      borderRadius="base"
      background="subdued"
      blockSize="100%"
    >
      <s-grid
        gridTemplateRows="auto minmax(0, 1fr) auto"
        gap="small"
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
          <s-text type="strong">{title}</s-text>
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

        <s-stack gap="small-200">
          {hasPdf ? <s-grid gridTemplateColumns="1fr"><s-button inlineSize="fill" variant="primary" command="--show" commandFor="certificate-viewer"
            onClick={() => onOpen(certificate,true)}>Get certificate framed</s-button></s-grid> : null}
          <s-grid gridTemplateColumns="1fr 1fr" alignItems="center" gap="small">
            {hasPdf ? <s-clickable command="--show" commandFor="certificate-viewer" padding="small-200" minBlockSize="44px" accessibilityLabel="View certificate"
              onClick={() => onOpen(certificate)}><s-text>View certificate</s-text></s-clickable> : null}
            {hasPrint ? <s-link href={certificate.certificate_print_jpg_url} target="_blank">Free print download</s-link> : null}
          </s-grid>
          {!hasPdf ? <s-badge tone="neutral">Certificate processing</s-badge> : null}
        </s-stack>
      </s-grid>
    </s-box>
  );
}

function CertificatePreview({certificate, eager = false, previewUrl = ""}) {
  const title = certificate.product_title || "Sports Cave artwork";
  const hasDownload = Boolean(
    certificate.certificate_pdf_url
      || certificate.certificate_print_jpg_url,
  );
  const imageUrl = previewUrl || certificate.frame_preview_url || certificate.certificate_preview_image_url;
  if (imageUrl) {
    return (
      <s-box
        background="base"
        border="base"
        borderRadius="small"
        overflow="hidden"
      >
        <s-image
          src={imageUrl}
          alt={`Certificate preview for ${title}`}
          aspectRatio={eager ? (certificate.frame_preview_url || previewUrl ? "1/1" : "16/9") : "4/3"}
          objectFit="contain"
          loading={eager ? "eager" : "lazy"}
          sizes="(min-width: 750px) 50vw, 100vw"
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

function CertificateViewer({certificate, api, apiBaseUrl, country, offerLoader, onClose}) {
  const modalId = "certificate-viewer";
  const title = certificate?.product_title || "Certificate";
  const framingOnly = Boolean(certificate?.framingOnly);
  const [frameOffer, setFrameOffer] = useState({
    status: "idle",
    product: null,
    certificateReference: "", previewUrl: "",
  });
  const [frameColor, setFrameColor] = useState("Black");
  const [checkoutState, setCheckoutState] = useState({
    status: "idle",
    message: "",
    checkoutUrl: "",
  });
  const cartReady = checkoutState.status === "ready" && Boolean(checkoutState.checkoutUrl);
  const selectedProduct = (frameOffer.product?.variants || []).find((v) => v.color === frameColor) || frameOffer.product;

  useEffect(() => {
    const controller = new AbortController();
    setCheckoutState({status: "idle", message: "", checkoutUrl: ""});
    setFrameColor("Black");
    if (!certificate) {
      setFrameOffer({
        status: "idle",
        product: null,
        certificateReference: "", previewUrl: "",
      });
      return () => controller.abort();
    }

    setFrameOffer({
      status: "loading",
      product: null,
      certificateReference: "", previewUrl: "",
    });
    async function loadFrameOffer() {
      try {
        const payload = offerLoader ? await offerLoader.context(country) : await vaultRequest(
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
        let product = payload.frame_product;
        if (!offerLoader && product?.available) {
          const prices=await api.query(FRAME_PRICE_QUERY,{variables:{id:product.product_id,country}});
          if (prices.errors?.length) throw new Error('Frame prices unavailable');
          product=marketFrames(product,prices.data?.product);
        }
        if (controller.signal.aborted) return;
        if (
          !ownedCertificate?.reference
          || !product?.available
          || !product?.variant_id
        ) {
          setFrameOffer({
            status: "unavailable",
            product: null,
            certificateReference: "", previewUrl: "",
          });
          return;
        }
        setFrameOffer({
          status: "ready",
          product,
          previewUrl: vaultAssetUrl(apiBaseUrl, ownedCertificate.preview_url),
          certificateReference: ownedCertificate.reference,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        setFrameOffer({
          status: "error",
          product: null,
          certificateReference: "", previewUrl: "",
        });
      }
    }
    loadFrameOffer();
    return () => controller.abort();
  }, [api, apiBaseUrl, certificate?.key, country, offerLoader]);

  const addFramedCertificate = async () => {
    if (
      frameOffer.status !== "ready"
      || checkoutState.status === "adding"
    ) {
      return;
    }
    const product = (frameOffer.product.variants || []).find((v) => v.color === frameColor) || frameOffer.product;
    setCheckoutState({
      status: "adding",
      message: "Adding your framed certificate...",
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
            idempotency_key: `${frameIdempotencyKey(certificate)}-${frameColor.toLowerCase()}`,
            allow_repeat: false,
            country,
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
          message: "Added to cart",
          checkoutUrl: request.cart_handoff_url,
        });
        return;
      }
      const cartPayload = await api.query(CART_CREATE_MUTATION, {
        variables: {
          input: {...frameCartInput(product.variant_id, String(request.request_reference)), buyerIdentity:{countryCode:country}},
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
        message: "Added to cart",
        checkoutUrl: request.cart_handoff_url,
      });
    } catch (_error) {
      setCheckoutState({
        status: "error",
        message: "Could not add your certificate. Please try again.",
        checkoutUrl: "",
      });
    }
  };

  return (
    <s-modal
      id={modalId}
      heading={cartReady ? "Your framed certificate cart" : framingOnly ? "Frame your certificate" : title}
      accessibilityLabel={`Certificate viewer for ${title}`}
      size="large-100"
      padding="none"
      onAfterHide={onClose}
    >
      <s-query-container>
      {certificate ? (
        <s-grid gridTemplateColumns="minmax(0, 1120px)" justifyContent="center">
        <s-box padding="@container (inline-size > 520px) base, none">
        <s-grid
          gridTemplateColumns={framingOnly ? "@container (inline-size > 520px) 'minmax(0, 1.1fr) minmax(0, 1fr)', 'minmax(0, 1fr)'" : "1fr"}
          gap="@container (inline-size > 520px) large, none"
          alignItems="stretch"
        >
          {framingOnly && frameOffer.previewUrl ? <FramedCertificatePreview certificate={certificate} previewUrl={frameOffer.previewUrl} color={frameColor} /> : <CertificatePreview certificate={certificate} previewUrl={!framingOnly
              ? frameOffer.previewUrl || certificate.certificate_preview_image_url
              : frameOffer.previewUrl
                ? `${frameOffer.previewUrl}&frame=${frameColor.toLowerCase()}`
                : certificate.frame_preview_url || certificate.certificate_preview_image_url
          } eager />}
          <s-box padding="@container (inline-size > 520px) none, small">
          <s-stack gap="@container (inline-size > 520px) large, small" blockSize="100%" justifyContent="space-between">
            <s-stack gap="small-400">
              <s-heading>{compactTitle(title)}</s-heading>
              {certificate.edition_display ? (
                <s-text type="emphasis">
                  {editionLabel(certificate.edition_display).replace("#", "")}
                </s-text>
              ) : null}
              {cartReady ? <s-badge tone="auto" icon="check">Added to cart</s-badge> : null}
              {framingOnly ? <s-box display="@container (inline-size > 520px) auto, none"><s-text>Your numbered certificate, professionally printed and framed.</s-text></s-box> : null}
              {framingOnly ? <s-text color="subdued">Small · 21 × 30 cm</s-text> : null}
            </s-stack>
            {framingOnly && frameOffer.status === "loading" ? (
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
            {cartReady ? (
              <s-stack gap="large">
                <s-box padding="base" background="subdued" borderRadius="large">
                  <s-stack gap="base">
                    <s-text type="strong">{frameColor} frame · Quantity 1</s-text>
                    <s-text type="strong">{formatFramePrice(selectedProduct?.contextual_price, api.i18n.formatNumber)}</s-text>
                    <s-text color="subdued">Shipping and taxes calculated at checkout.</s-text>
                  </s-stack>
                </s-box>
                <s-text color="subdued">Your existing store cart items will be included at checkout.</s-text>
                <s-grid gridTemplateColumns="1fr" gap="base">
                  <s-button variant="primary" href={checkoutState.checkoutUrl}>Continue to cart</s-button>
                  <s-button variant="secondary" command="--hide" commandFor={modalId}>Continue browsing My Collection</s-button>
                </s-grid>
              </s-stack>
            ) : framingOnly && frameOffer.status === "ready" ? (
              <FramedCertificateOffer
                product={frameOffer.product}
                frameColor={frameColor}
                onColorChange={(color) => {
                  setFrameColor(color);
                  setCheckoutState({status: "idle", message: "", checkoutUrl: ""});
                }}
                checkoutState={checkoutState}
                onAdd={addFramedCertificate}
                formatNumber={api.i18n.formatNumber}
              />
            ) : null}
            {framingOnly && ["error", "unavailable"].includes(frameOffer.status) ? (
              <s-text color="subdued">Framing is temporarily unavailable. Please try again shortly.</s-text>
            ) : null}
          </s-stack>
          </s-box>
        </s-grid>
        </s-box>
        </s-grid>
      ) : (
        <s-text color="subdued">Choose a certificate to view it.</s-text>
      )}
      </s-query-container>
    </s-modal>
  );
}

function FramedCertificatePreview({certificate, previewUrl, color}) {
  return <s-grid gridTemplateColumns="@container (inline-size > 520px) 'minmax(0, 1fr)', '160px'" justifyContent="center" alignItems="center">
    <s-box borderRadius="large" overflow="hidden">
    {["Black", "Oak", "White"].map(frame => (
      <s-box key={frame} display={frame === color ? "auto" : "none"} accessibilityVisibility={frame === color ? "visible" : "hidden"}>
        <s-image src={`${previewUrl}&frame=${frame.toLowerCase()}`}
          srcSet={`${previewUrl}&frame=${frame.toLowerCase()}&w=400 400w, ${previewUrl}&frame=${frame.toLowerCase()}&w=1000 1000w`}
          alt={`${frame} framed certificate for ${certificate.product_title || "your edition"}`}
          aspectRatio="1/1" objectFit="contain" loading="eager"
          sizes="(min-width: 520px) 560px, 160px" />
      </s-box>
    ))}
    </s-box>
  </s-grid>;
}

function FramedCertificateOffer({
  product,
  frameColor,
  onColorChange,
  checkoutState,
  onAdd,
  formatNumber,
}) {
  const price = formatFramePrice(
    ((product.variants || []).find((v) => v.color === frameColor) || product).contextual_price,
    formatNumber,
  );

  return (
    <s-box>
      <s-stack gap="@container (inline-size > 520px) large, small">
        <s-heading>Choose frame</s-heading>
        <s-grid gridTemplateColumns="repeat(3, minmax(0, 1fr))" gap="small">
          {(product.variants?.length ? product.variants : [{color: "Black"}]).map((variant) => (
            <s-clickable key={variant.color} border={frameColor === variant.color ? "large" : "base"}
              borderRadius="large" overflow="hidden" disabled={checkoutState.status === "adding"}
              accessibilityLabel={`${variant.color} frame${frameColor === variant.color ? ", selected" : ""}`}
              onClick={() => onColorChange(variant.color)}>
              <s-stack gap="none" alignItems="center">
                <s-box inlineSize="100%" display="@container (inline-size > 520px) auto, none">
                  <s-image src={`https://cdn.shopify.com/s/files/1/0722/2332/6515/files/sports-cave-${variant.color.toLowerCase()}-frame-swatch.webp?v=1785548629&width=320`}
                    alt={`${variant.color} frame detail`} aspectRatio="1/1" objectFit="cover" loading="eager" />
                </s-box>
                <s-box inlineSize="100%" display="@container (inline-size > 520px) none, auto">
                  <s-image src={`https://cdn.shopify.com/s/files/1/0722/2332/6515/files/sports-cave-${variant.color.toLowerCase()}-frame-swatch.webp?v=1785548629&width=320`}
                    alt={`${variant.color} frame detail`} aspectRatio="2/1" objectFit="cover" loading="eager" />
                </s-box>
                <s-box padding="small-400" minBlockSize="32px"><s-text type="strong">{frameColor === variant.color ? "✓ " : ""}{variant.color}</s-text></s-box>
              </s-stack>
            </s-clickable>
          ))}
        </s-grid>
        {checkoutState.checkoutUrl ? (
          <s-stack gap="base">
            <s-badge tone="auto" icon="check">Added to cart</s-badge>
          <s-button
            variant="primary"
            href={checkoutState.checkoutUrl}
          >
            Checkout now
          </s-button>
          </s-stack>
        ) : checkoutState.status === "ordered" ? (
          <s-badge tone="neutral" icon="check">
            Framed certificate ordered
          </s-badge>
        ) : (
          <s-button
            inlineSize="fill"
            variant="primary"
            onClick={onAdd}
            loading={checkoutState.status === "adding"}
          >
            <s-box paddingBlock="small"><s-text type="strong">Add to cart · {price}</s-text></s-box>
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

function CollectionUpsells({api, apiBaseUrl, country, certificate}) {
  const [products, setProducts] = useState([]);
  const [status, setStatus] = useState("loading");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    async function load() {
      try {
        if (!certificate?.shopify_product_id) { setProducts([]); setStatus("empty"); return; }
        const recommended = await vaultRequest(api, apiBaseUrl,
          `/api/collector-vault/recommendations?fields=ids&country=${country}&product_id=${encodeURIComponent(certificate?.shopify_product_id || "")}`, {signal: controller.signal});
        if (controller.signal.aborted) return;
        const ids = (recommended.products || []).slice(0, 8).map((p) => p.id);
        if (!ids.length) {
          if (!controller.signal.aborted) { setProducts([]); setStatus("empty"); }
          return;
        }
        const result = await timedOperation(api, apiBaseUrl, 'pair_products', async () => {
          const response = await api.query(UPSELL_QUERY, {variables: {ids, country}});
          if (response.errors?.length) throw new Error("Products unavailable");
          return response;
        });
        // Preserve the smart rank even when Shopify returns nodes in another order.
        const nodes = pairedProducts(ids, result.data?.nodes);
        if (!controller.signal.aborted) { setProducts(nodes); setStatus(nodes.length ? "ready" : "empty"); }
      } catch (_error) {
        if (!controller.signal.aborted) setStatus("error");
      }
    }
    load();
    return () => controller.abort();
  }, [api, apiBaseUrl, retry, country, certificate?.shopify_product_id]);
  return <s-stack gap="base">
    <s-heading>Pairs with your {compactTitle(certificate?.product_title || "selected")} edition</s-heading>
    {status === "loading" ? <s-grid gridTemplateColumns="repeat(2, minmax(0, 1fr))" gap="large" accessibilityLabel="Finding your recommendations">
      {[0, 1].map(index => <s-grid key={index} gridTemplateColumns="@container (inline-size > 850px) '152px minmax(0, 1fr)', '1fr'" gap="base" alignItems="center"><s-box minBlockSize="@container (inline-size > 850px) 114px, 120px" background="subdued" borderRadius="base" /><s-box minBlockSize="32px" /></s-grid>)}
    </s-grid> : null}
    {status === "error" ? <s-stack gap="small"><s-text>Recommendations are temporarily unavailable.</s-text>
      <s-button variant="secondary" onClick={() => setRetry(retry + 1)}>Try again</s-button></s-stack> : null}
    {status === "empty" ? <s-text color="subdued">More editions for your collection are coming soon.</s-text> : null}
    <s-grid gridTemplateColumns="repeat(2, minmax(0, 1fr))" gap="large" alignItems="stretch">
      {products.map(product => <s-link key={product.id} href={`https://www.sportscaveshop.com/products/${product.handle}?country=${country}`} target="_blank">
        <s-grid gridTemplateColumns="@container (inline-size > 850px) '152px minmax(0, 1fr)', '1fr'" gap="base" alignItems="center">
          {product.featuredImage?.url ? <s-image src={product.featuredImage.url} alt={product.featuredImage.altText || product.title} aspectRatio="4/3" objectFit="contain" loading="lazy" /> : null}
          <s-text type="strong">{compactTitle(product.title)}</s-text>
        </s-grid>
      </s-link>)}
    </s-grid>
  </s-stack>;
}

function UpsellProduct({product, api, onAdd}) {
  const variants = product.variants.nodes.filter((v) => v.availableForSale);
  const [variantId, setVariantId] = useState(variants[0]?.id || "");
  const [cart, setCart] = useState({status: "idle", url: ""});
  const variant = variants.find((v) => v.id === variantId);
  const image = variant?.image || product.featuredImage;
  const add = async () => {
    if (!variant || cart.status === "adding") return;
    setCart({status: "adding", url: ""});
    try {
      const url = await onAdd(variant.id);
      setCart({status: "ready", url});
    } catch (_error) { setCart({status: "error", url: ""}); }
  };
  return <s-box padding="small" border="base" borderRadius="base" background="subdued">
    <s-stack gap="small">
      {image?.url ? <s-image src={image.url} alt={image.altText || product.title} aspectRatio="4/3" objectFit="contain" loading="lazy" /> : null}
      <s-text type="strong">{compactTitle(product.title)}</s-text>
      <s-select label="Frame and size" value={variantId} disabled={cart.status === "adding"}
        onChange={(event) => { setVariantId((/** @type {HTMLSelectElement} */ (event.currentTarget)).value); setCart({status: "idle", url: ""}); }}>
        {variants.map((v) => <s-option key={v.id} value={v.id}>{v.title}</s-option>)}
      </s-select>
      {comparePrice(variant) ? <s-text color="subdued">RRP {formatFramePrice(comparePrice(variant), api.i18n.formatNumber)}</s-text> : null}
      <s-grid gridTemplateColumns="1fr">
      {cart.url ? <s-button inlineSize="fill" variant="primary" href={cart.url} target="_blank">Checkout · {formatFramePrice(variant?.price, api.i18n.formatNumber)}</s-button>
        : <s-button inlineSize="fill" variant="primary" onClick={add} loading={cart.status === "adding"} disabled={!variant}>Add to cart · {formatFramePrice(variant?.price, api.i18n.formatNumber)}</s-button>}
      </s-grid>
      {cart.status === "error" ? <s-text>Could not create your cart. Please try again.</s-text> : null}
    </s-stack>
  </s-box>;
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

function vaultAssetUrl(apiBaseUrl, value) {
  const path = String(value || "");
  return path.startsWith("/api/collector-vault/asset?token=")
    ? `${apiBaseUrl}${path}`
    : "";
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
  return timedOperation(api, apiBaseUrl, operationForPath(path), () => performVaultRequest(api, apiBaseUrl, path, options));
}

async function performVaultRequest(api, apiBaseUrl, path, options = {}) {
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

function useCountry(api) {
  const [country,setCountry]=useState(()=>accountCountry(api));
  useEffect(()=> {
    const signal=api.localization?.country;
    setCountry(accountCountry(api));
    return signal?.subscribe?.(()=>setCountry(accountCountry(api)));
  },[api]);
  return country;
}
