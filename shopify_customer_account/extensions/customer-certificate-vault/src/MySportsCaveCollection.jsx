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
import {accountCountry, compactTitle, comparePrice, UPSELL_QUERY, FRAME_PRICE_QUERY, marketFrames} from "./account-commerce.js";
import {AccountReview} from "./AccountReview.jsx";
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
  const apiBaseUrl = configuredApiBaseUrl(api);

  useEffect(() => {
    let mounted = true;

    async function loadCertificates() {
      setStatus("loading");
      setErrorMessage("");
      try {
        const fetchCustomerPage = (_url, options) => fetch(`shopify://customer-account/api/${API_VERSION}/graphql.json`, options);
        const {customer, orders: orderNodes} = await loadCollectionOrders(fetchCustomerPage, API_VERSION, CERTIFICATES_QUERY);
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
  const country = useCountry(api);
  const [reviewPrompt, setReviewPrompt] = useState(null);

  useEffect(() => {
    if (status !== "ready") return;
    const controller = new AbortController();
    vaultRequest(api, apiBaseUrl, "/api/collector-vault/bootstrap", {signal: controller.signal})
      .then((payload) => {
        if (controller.signal.aborted) return;
        setReviewPrompt(payload.review_prompt || null);
        setCertificates((items) => items.map((certificate) => {
          const owned = matchingFrameCertificate(payload.certificates, certificate);
          const preview = vaultAssetUrl(apiBaseUrl, owned?.preview_url);
          return {...certificate,
            frame_preview_url: preview ? `${preview}&frame=black` : "",
            certificate_preview_image_url: certificate.certificate_preview_image_url || preview,
            certificate_print_jpg_url: certificate.certificate_print_jpg_url || vaultAssetUrl(apiBaseUrl, owned?.print_url),
          };
        }));
      }).catch(() => {}); // Existing certificate assets remain usable independently.
    return () => controller.abort();
  }, [status, retryKey, api, apiBaseUrl]);

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
            <AccountReview certificate={firstCertificate} prompt={reviewPrompt} request={(path, options) => vaultRequest(api, apiBaseUrl, path, options)} />
          ) : null}
          {status === "ready" && certificates.length === 0 ? (
            <EmptyState />
          ) : null}
          {status === "ready" && certificates.length > 0 ? (
            <CertificateGallery
              certificates={certificates}
              onOpen={(certificate, framingOnly = false) => setSelectedCertificate({...certificate, framingOnly})}
            />
          ) : null}
          {status === "ready" && certificates.length > 0 ? (
            <CollectionUpsells api={api} apiBaseUrl={apiBaseUrl} country={country} />
          ) : null}
        </s-stack>
      </s-grid>
      <CertificateViewer
        certificate={selectedCertificate}
        api={api}
        apiBaseUrl={apiBaseUrl}
        country={country}
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
    <s-scroll-box overflow="hidden auto" inlineSize="100%" accessibilityLabel="Your certificates — swipe to explore">
    <s-grid
      gridTemplateColumns={`@container (inline-size > 900px) repeat(4, minmax(0, 1fr)), (inline-size > 650px) repeat(2, minmax(0, 1fr)), repeat(${certificates.length}, minmax(260px, 82vw))`}
      gap="small"
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
    </s-scroll-box>
  );
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

        <s-grid
          gridTemplateColumns="repeat(auto-fit, minmax(min(100%, 100px), 1fr))"
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
              command="--show"
              commandFor="certificate-viewer"
              onClick={() => onOpen(certificate, true)}
              variant="secondary"
            >
              Get Certificate Framed
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

function CertificatePreview({certificate, eager = false, previewUrl}) {
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

function CertificateViewer({certificate, api, apiBaseUrl, country, onClose}) {
  const modalId = "certificate-viewer";
  const title = certificate?.product_title || "Certificate";
  const framingOnly = Boolean(certificate?.framingOnly);
  const [frameOffer, setFrameOffer] = useState({
    status: "idle",
    product: null,
    certificateReference: "",
  });
  const [frameColor, setFrameColor] = useState("Black");
  const [checkoutState, setCheckoutState] = useState({
    status: "idle",
    message: "",
    checkoutUrl: "",
  });

  useEffect(() => {
    const controller = new AbortController();
    setCheckoutState({status: "idle", message: "", checkoutUrl: ""});
    setFrameColor("Black");
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
        let product = payload.frame_product;
        if (product?.available) {
          const prices=await api.query(FRAME_PRICE_QUERY,{variables:{id:product.product_id,country}});
          if (prices.errors?.length) throw new Error('Frame prices unavailable');
          product=marketFrames(product,prices.data?.product);
        }
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
          previewUrl: vaultAssetUrl(apiBaseUrl, ownedCertificate.preview_url),
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
  }, [api, apiBaseUrl, certificate?.key, country]);

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
      heading={framingOnly ? "Get your certificate framed" : title}
      accessibilityLabel={`Certificate viewer for ${title}`}
      size="large-100"
      padding="base"
      onAfterHide={onClose}
    >
      {certificate ? (
        <s-grid
          gridTemplateColumns={framingOnly ? "repeat(auto-fit, minmax(min(100%, 240px), 1fr))" : "1fr"}
          gap="large"
          alignItems="start"
        >
          <CertificatePreview certificate={certificate} previewUrl={!framingOnly
              ? frameOffer.previewUrl || certificate.certificate_preview_image_url
              : frameOffer.previewUrl
                ? `${frameOffer.previewUrl}&frame=${frameColor.toLowerCase()}`
                : certificate.certificate_preview_image_url
          } eager />
          <s-stack gap="large">
            <s-stack gap="small-400">
              <s-heading>{title}</s-heading>
              {certificate.edition_display ? (
                <s-text type="strong">
                  {editionLabel(certificate.edition_display)}
                </s-text>
              ) : null}
              {framingOnly ? <s-text>Your numbered certificate, professionally printed and framed.</s-text> : null}
              {framingOnly ? <s-text color="subdued">Small · 21 × 30 cm (8.3 × 11.8 in)</s-text> : null}
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
            {framingOnly && frameOffer.status === "ready" ? (
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
        </s-grid>
      ) : (
        <s-text color="subdued">Choose a certificate to view it.</s-text>
      )}
    </s-modal>
  );
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
      <s-stack gap="large">
        <s-heading>Choose frame</s-heading>
        <s-grid gridTemplateColumns="repeat(3, minmax(0, 1fr))" gap="small">
          {(product.variants?.length ? product.variants : [{color: "Black"}]).map((variant) => (
            <s-clickable key={variant.color} border={frameColor === variant.color ? "large" : "base"}
              borderRadius="base" disabled={checkoutState.status === "adding"}
              accessibilityLabel={`${variant.color} frame${frameColor === variant.color ? ", selected" : ""}`}
              onClick={() => onColorChange(variant.color)}>
              <s-stack gap="small" alignItems="center">
                <s-image src={`https://cdn.shopify.com/s/files/1/0722/2332/6515/files/sports-cave-${variant.color.toLowerCase()}-frame-swatch.webp?v=1785548629`}
                  alt={`${variant.color} frame detail`} aspectRatio="1/1" objectFit="cover" />
                <s-text type="strong">{frameColor === variant.color ? "✓ " : ""}{variant.color}</s-text>
              </s-stack>
            </s-clickable>
          ))}
        </s-grid>
        {checkoutState.checkoutUrl ? (
          <s-stack gap="base">
            <s-badge tone="success" icon="check">Added to cart</s-badge>
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
            variant="primary"
            onClick={onAdd}
            loading={checkoutState.status === "adding"}
          >
            Add framed certificate to cart · {price}
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

function CollectionUpsells({api, apiBaseUrl, country}) {
  const sharedCart = useRef(null);
  const cartQueue = useRef(Promise.resolve());
  useEffect(() => { sharedCart.current=null; }, [country]);
  const addToCollectionCart = (variantId) => {
    const operation = cartQueue.current.then(async () => {
      const lines = [{merchandiseId: variantId, quantity: 1}];
      const result = sharedCart.current
        ? await api.query(`mutation CollectionCartAdd($cartId: ID!, $lines: [CartLineInput!]!) {
            cartLinesAdd(cartId: $cartId, lines: $lines) { cart { id checkoutUrl } userErrors { field message } }
          }`, {variables: {cartId: sharedCart.current.id, lines}})
        : await api.query(CART_CREATE_MUTATION, {variables: {input: {lines,buyerIdentity:{countryCode:country}}}});
      const created = result.data?.cartLinesAdd || result.data?.cartCreate;
      if (result.errors?.length || created?.userErrors?.length || !created?.cart?.checkoutUrl) throw new Error("Cart unavailable");
      sharedCart.current = created.cart;
      return created.cart.checkoutUrl;
    });
    cartQueue.current = operation.catch(() => {});
    return operation;
  };
  const [products, setProducts] = useState([]);
  const [status, setStatus] = useState("loading");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    async function load() {
      try {
        const recommended = await vaultRequest(api, apiBaseUrl,
          `/api/collector-vault/recommendations?country=${country}`, {signal: controller.signal});
        const ids = (recommended.products || []).slice(0, 8).map((p) => p.id);
        if (!ids.length) {
          if (!controller.signal.aborted) { setProducts([]); setStatus("empty"); }
          return;
        }
        const result = await api.query(UPSELL_QUERY, {variables: {ids, country}});
        if (result.errors?.length) throw new Error("Products unavailable");
        const nodes = (result.data?.nodes || []).filter((p) => p?.variants?.nodes?.some((v) => v.availableForSale)).slice(0, 4);
        if (!controller.signal.aborted) { setProducts(nodes); setStatus(nodes.length ? "ready" : "empty"); }
      } catch (_error) {
        if (!controller.signal.aborted) setStatus("error");
      }
    }
    load();
    return () => controller.abort();
  }, [api, apiBaseUrl, retry, country]);
  return <s-stack gap="base">
    <s-heading>Build your collection</s-heading>
    <s-text color="subdued">Selected for you · choose your frame and size.</s-text>
    {status === "loading" ? <s-spinner accessibilityLabel="Finding your recommendations" /> : null}
    {status === "error" ? <s-stack gap="small"><s-text>Recommendations are temporarily unavailable.</s-text>
      <s-button variant="secondary" onClick={() => setRetry(retry + 1)}>Try again</s-button></s-stack> : null}
    {status === "empty" ? <s-text color="subdued">More editions for your collection are coming soon.</s-text> : null}
    <s-scroll-box overflow="hidden auto" inlineSize="100%" accessibilityLabel="Recommended editions — swipe to explore">
    <s-grid gridTemplateColumns="@container (inline-size > 750px) repeat(4, minmax(0, 1fr)), repeat(4, minmax(240px, 78vw))" gap="small" alignItems="stretch">
      {products.map((product) => <UpsellProduct key={`${country}-${product.id}`} product={product} api={api} onAdd={addToCollectionCart} />)}
    </s-grid>
    </s-scroll-box>
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
        onChange={(event) => { setVariantId(event.currentTarget.value); setCart({status: "idle", url: ""}); }}>
        {variants.map((v) => <s-option key={v.id} value={v.id}>{v.title}</s-option>)}
      </s-select>
      {comparePrice(variant) ? <s-text color="subdued">RRP {formatFramePrice(comparePrice(variant), api.i18n.formatNumber)}</s-text> : null}
      <s-grid gridTemplateColumns="1fr">
      {cart.url ? <s-button variant="primary" href={cart.url} target="_blank">Checkout · {formatFramePrice(variant?.price, api.i18n.formatNumber)}</s-button>
        : <s-button variant="primary" onClick={add} loading={cart.status === "adding"} disabled={!variant}>Add to cart · {formatFramePrice(variant?.price, api.i18n.formatNumber)}</s-button>}
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
