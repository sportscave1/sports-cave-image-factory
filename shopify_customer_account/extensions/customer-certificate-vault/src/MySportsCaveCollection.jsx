/** @jsxImportSource preact */
/// <reference types="@shopify/ui-extensions/customer-account.page.render" />
import "@shopify/ui-extensions/preact";
import {render} from "preact";
import {useEffect, useMemo, useRef, useState} from "preact/hooks";
import {useApi} from "@shopify/ui-extensions/customer-account/preact";

import {
  chooseFrameVariant,
  collectionSubheading,
  editionLabel,
  fileFromDropEvent,
  formatFramePrice,
  frameCartInput,
  inputValue,
  isAllowedReviewPhoto,
  purchaseDateLabel,
} from "./vault-utils.js";

const DEFAULT_API_BASE_URL = "https://sports-cave-image-factory.onrender.com";
const FRAME_PRODUCT_QUERY = `query CollectorVaultFrameProduct($id: ID!) {
  product(id: $id) {
    id
    handle
    title
    availableForSale
    featuredImage { url altText width height }
    variants(first: 10) {
      nodes {
        id
        availableForSale
        price { amount currencyCode }
      }
    }
  }
}`;
const CART_CREATE_MUTATION = `mutation CollectorVaultCartCreate($input: CartInput!) {
  cartCreate(input: $input) {
    cart { id checkoutUrl }
    userErrors { field message }
  }
}`;

export default function extension() {
  render(<CollectorVault />, document.body);
}

function CollectorVault() {
  const api = useApi();
  const [status, setStatus] = useState("loading");
  const [certificates, setCertificates] = useState([]);
  const [reviewPrompt, setReviewPrompt] = useState(null);
  const [frameConfig, setFrameConfig] = useState(null);
  const [frameVariant, setFrameVariant] = useState(null);
  const [selectedCertificate, setSelectedCertificate] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [reviewSubmitted, setReviewSubmitted] = useState(false);
  const apiBaseUrl = useMemo(() => configuredApiBaseUrl(api), [api]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setStatus("loading");
      try {
        const payload = await vaultRequest(api, apiBaseUrl, "/api/collector-vault/bootstrap");
        if (!mounted) return;
        setCertificates(Array.isArray(payload.certificates) ? payload.certificates : []);
        setReviewPrompt(payload.review_prompt || null);
        setFrameConfig(payload.frame_product || null);
        setStatus("ready");
        await logEvent(api, apiBaseUrl, "collection_viewed", dailyEventKey("collection-viewed"));
      } catch (error) {
        if (!mounted) return;
        setErrorMessage(customerMessage(error));
        setStatus("error");
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [apiBaseUrl, retryKey]);

  useEffect(() => {
    let mounted = true;
    async function loadFrameProduct() {
      if (!frameConfig?.available || !frameConfig.product_id) {
        setFrameVariant(null);
        return;
      }
      try {
        const response = /** @type {any} */ (await api.query(FRAME_PRODUCT_QUERY, {
          variables: {id: frameConfig.product_id},
        }));
        const product = response?.data?.product;
        const variant = chooseFrameVariant(
          product,
          frameConfig.variant_id,
          "",
          frameConfig.product_id,
        );
        if (mounted) setFrameVariant(variant);
      } catch (_error) {
        if (mounted) setFrameVariant(null);
      }
    }
    loadFrameProduct();
    return () => {
      mounted = false;
    };
  }, [api, frameConfig]);

  const openCertificate = (certificate) => {
    setSelectedCertificate(certificate);
    logEvent(api, apiBaseUrl, "certificate_opened", eventKeyForCertificate("opened", certificate));
  };

  return (
    <s-page heading="My Collection" subheading={collectionSubheading(certificates.length)}>
      {status === "loading" ? <LoadingGallery /> : null}
      {status === "error" ? (
        <ErrorState message={errorMessage} onRetry={() => setRetryKey((value) => value + 1)} />
      ) : null}
      {status === "ready" && certificates.length === 0 ? <EmptyState /> : null}
      {status === "ready" && certificates.length > 0 ? (
        <s-stack gap="large">
          {reviewPrompt && !reviewSubmitted ? (
            <ReviewPrompt
              prompt={reviewPrompt}
              api={api}
              apiBaseUrl={apiBaseUrl}
              onSubmitted={() => {
                setReviewSubmitted(true);
                setReviewPrompt(null);
              }}
            />
          ) : null}
          {reviewSubmitted ? (
            <s-banner tone="success" heading="Review submitted ✓">
              Thank you. Your review was sent to Judge.me and may be awaiting moderation.
            </s-banner>
          ) : null}
          <s-grid
            gridTemplateColumns="repeat(auto-fit, minmax(min(100%, 360px), 1fr))"
            gap="base"
            alignItems="start"
          >
            {certificates.map((certificate, index) => (
              <CertificateCard
                key={certificate.reference}
                certificate={certificate}
                index={index}
                onOpen={openCertificate}
                api={api}
                apiBaseUrl={apiBaseUrl}
                frameVariant={frameVariant}
              />
            ))}
          </s-grid>
        </s-stack>
      ) : null}
      <CertificateViewer
        certificate={selectedCertificate}
        frameVariant={frameVariant}
        api={api}
        apiBaseUrl={apiBaseUrl}
        onFrameStatus={(reference, frameStatus, requestReference) => {
          setCertificates((items) => items.map((item) => (
            item.reference === reference
              ? {...item, frame_status: frameStatus, frame_request_reference: requestReference}
              : item
          )));
        }}
      />
    </s-page>
  );
}

function LoadingGallery() {
  return (
    <s-grid gridTemplateColumns="repeat(auto-fit, minmax(min(100%, 360px), 1fr))" gap="base">
      {[0, 1, 2, 3].map((index) => (
        <s-box key={index} padding="base" border="base" borderRadius="base">
          <s-stack gap="base">
            <s-box minBlockSize="220px" background="subdued" borderRadius="base"></s-box>
            <s-skeleton-paragraph></s-skeleton-paragraph>
            <s-skeleton-paragraph></s-skeleton-paragraph>
          </s-stack>
        </s-box>
      ))}
    </s-grid>
  );
}

function EmptyState() {
  return (
    <s-section heading="Your collection is waiting">
      <s-stack gap="base">
        <s-text>
          Numbered Sports Cave certificates appear here when their certificate assets are ready.
        </s-text>
        <s-button href="https://www.sportscaveshop.com" target="_blank">
          Shop latest releases
        </s-button>
      </s-stack>
    </s-section>
  );
}

function ErrorState({message, onRetry}) {
  return (
    <s-banner heading="Collection unavailable" tone="critical">
      <s-stack gap="base">
        <s-text>{message}</s-text>
        <s-button onClick={onRetry}>Try again</s-button>
      </s-stack>
    </s-banner>
  );
}

function CertificateCard({certificate, index, onOpen, api, apiBaseUrl, frameVariant}) {
  const menuId = `certificate-menu-${index}`;
  const frameAvailable = Boolean(frameVariant && certificate.frame_status !== "ordered");
  return (
    <s-box padding="base" border="base" borderRadius="base" background="subdued">
      <s-stack gap="base">
        <s-clickable
          accessibilityLabel={`View certificate for ${certificate.product_title}`}
          command="--show"
          commandFor="certificate-viewer"
          onClick={() => onOpen(certificate)}
          borderRadius="base"
          minBlockSize="220px"
        >
          {certificate.preview_url ? (
            <s-image
              src={absoluteAssetUrl(apiBaseUrl, certificate.preview_url)}
              alt={`Certificate for ${certificate.product_title}`}
              aspectRatio="16/9"
              objectFit="contain"
              loading="lazy"
              sizes="(min-width: 760px) 50vw, 100vw"
            ></s-image>
          ) : (
            <s-box minBlockSize="220px" padding="large" background="base" borderRadius="base">
              <s-text color="subdued">Certificate preview is processing.</s-text>
            </s-box>
          )}
        </s-clickable>
        <s-stack gap="small-400">
          <s-heading>{certificate.product_title}</s-heading>
          <s-text type="strong">{editionLabel(certificate)}</s-text>
          <s-text color="subdued">
            {purchaseDateLabel(certificate.purchase_date, api.i18n.formatDate)}
          </s-text>
        </s-stack>
        <s-stack direction="inline" gap="small" alignItems="center" justifyContent="space-between">
          <s-button
            variant="primary"
            command="--show"
            commandFor="certificate-viewer"
            onClick={() => onOpen(certificate)}
          >
            View Certificate
          </s-button>
          {certificate.frame_status === "ordered" ? (
            <s-badge tone="neutral" icon="check">Framed certificate ordered</s-badge>
          ) : frameAvailable ? (
            <s-button
              variant="secondary"
              command="--show"
              commandFor="certificate-viewer"
              onClick={() => {
                onOpen(certificate);
                logEvent(api, apiBaseUrl, "frame_offer_viewed", eventKeyForCertificate("frame-viewed", certificate));
              }}
            >
              Order It Framed
            </s-button>
          ) : null}
          <s-clickable
            accessibilityLabel={`More certificate actions for ${certificate.product_title}`}
            command="--show"
            commandFor={menuId}
            padding="small"
            minBlockSize="44px"
            minInlineSize="44px"
          >
            <s-icon type="menu-horizontal"></s-icon>
          </s-clickable>
          <CertificateMenu
            id={menuId}
            certificate={certificate}
            api={api}
            apiBaseUrl={apiBaseUrl}
            detailsModalId={`certificate-details-${index}`}
          />
        </s-stack>
        <CertificateDetailsModal certificate={certificate} id={`certificate-details-${index}`} />
      </s-stack>
    </s-box>
  );
}

function CertificateMenu({id, certificate, api, apiBaseUrl, detailsModalId}) {
  return (
    <s-menu id={id} accessibilityLabel={`Actions for ${certificate.product_title}`}>
      {certificate.pdf_url ? (
        <s-button
          href={absoluteAssetUrl(apiBaseUrl, certificate.pdf_url)}
          target="_blank"
          onClick={() => logEvent(
            api,
            apiBaseUrl,
            "certificate_downloaded",
            eventKeyForCertificate("downloaded", certificate),
          )}
        >
          Download PDF
        </s-button>
      ) : null}
      {certificate.print_url ? (
        <s-button
          href={absoluteAssetUrl(apiBaseUrl, certificate.print_url)}
          target="_blank"
          onClick={() => logEvent(
            api,
            apiBaseUrl,
            "certificate_printed",
            eventKeyForCertificate("printed", certificate),
          )}
        >
          Print certificate
        </s-button>
      ) : null}
      <s-button command="--show" commandFor={detailsModalId}>
        Certificate details
      </s-button>
    </s-menu>
  );
}

function CertificateDetailsModal({certificate, id}) {
  return (
    <s-modal
      id={id}
      heading="Certificate details"
      accessibilityLabel={`Certificate details for ${certificate.product_title}`}
      size="small"
    >
      <s-stack gap="base">
        <Detail label="Order number" value={certificate.order_name} />
        <s-stack gap="small-100">
          <s-text color="subdued">Certificate ID</s-text>
          <s-stack direction="inline" gap="small" alignItems="center">
            <s-text>{certificate.certificate_id || "Unavailable"}</s-text>
            {certificate.certificate_id ? (
              <s-clipboard-item text={certificate.certificate_id}></s-clipboard-item>
            ) : null}
          </s-stack>
        </s-stack>
      </s-stack>
      <s-button slot="primary-action" command="--hide" commandFor={id}>Close</s-button>
    </s-modal>
  );
}

function CertificateViewer({certificate, frameVariant, api, apiBaseUrl, onFrameStatus}) {
  const [frameState, setFrameState] = useState({status: "idle", message: "", checkoutUrl: ""});
  const framePrice = formatFramePrice(frameVariant?.price, api.i18n.formatNumber);
  const modalId = "certificate-viewer";

  useEffect(() => {
    setFrameState({status: "idle", message: "", checkoutUrl: ""});
  }, [certificate?.reference]);

  if (!certificate) {
    return (
      <s-modal id={modalId} heading="Certificate" size="max">
        <s-text>Choose a certificate to view it.</s-text>
        <s-button slot="primary-action" command="--hide" commandFor={modalId}>Close</s-button>
      </s-modal>
    );
  }

  const orderFrame = async (allowRepeat = false) => {
    if (!frameVariant || frameState.status === "adding") return;
    setFrameState({status: "adding", message: "Preparing your framed certificate...", checkoutUrl: ""});
    try {
      const idempotencyKey = allowRepeat
        ? `repeat-${Date.now()}`
        : `certificate-${stableReferencePart(certificate.reference)}`;
      const frameRequest = await vaultRequest(
        api,
        apiBaseUrl,
        "/api/collector-vault/frame/request",
        {
          method: "POST",
          body: {
            certificate_reference: certificate.reference,
            frame_variant_id: frameVariant.id,
            idempotency_key: idempotencyKey,
            allow_repeat: allowRepeat,
          },
        },
      );
      if (frameRequest.status === "ordered" && !allowRepeat) {
        setFrameState({
          status: "ordered",
          message: "Your framed certificate has already been ordered.",
          checkoutUrl: "",
        });
        onFrameStatus(certificate.reference, "ordered", frameRequest.request_reference);
        return;
      }
      if (frameRequest.checkout_url) {
        setFrameState({
          status: "ready",
          message: "Your secure Shopify checkout is ready.",
          checkoutUrl: frameRequest.checkout_url,
        });
        return;
      }
      const cartPayload = await api.query(CART_CREATE_MUTATION, {
        variables: {input: frameCartInput(frameVariant.id, String(frameRequest.request_reference))},
      });
      const cartResult = cartPayload?.data?.cartCreate;
      const cartError = cartResult?.userErrors?.[0]?.message;
      if (cartError || !cartResult?.cart?.checkoutUrl) {
        throw new Error(cartError || "Shopify checkout could not be created.");
      }
      await vaultRequest(api, apiBaseUrl, "/api/collector-vault/frame/cart-created", {
        method: "POST",
        body: {
          request_reference: frameRequest.request_reference,
          cart_id: cartResult.cart.id,
          checkout_url: cartResult.cart.checkoutUrl,
        },
      });
      onFrameStatus(certificate.reference, "cart_created", frameRequest.request_reference);
      setFrameState({
        status: "ready",
        message: "Your secure Shopify checkout is ready.",
        checkoutUrl: cartResult.cart.checkoutUrl,
      });
    } catch (error) {
      setFrameState({status: "error", message: customerMessage(error), checkoutUrl: ""});
    }
  };

  return (
    <s-modal
      id={modalId}
      heading={certificate.product_title}
      accessibilityLabel={`Certificate viewer for ${certificate.product_title}`}
      size="max"
      padding="base"
      onAfterShow={() => {
        if (frameVariant) {
          logEvent(
            api,
            apiBaseUrl,
            "frame_offer_viewed",
            eventKeyForCertificate("frame-modal", certificate),
          );
        }
      }}
    >
      <s-grid
        gridTemplateColumns="repeat(auto-fit, minmax(min(100%, 320px), 1fr))"
        gap="large"
        alignItems="start"
      >
        <s-box background="subdued" padding="base" borderRadius="base">
          {certificate.preview_url ? (
            <s-image
              src={absoluteAssetUrl(apiBaseUrl, certificate.preview_url)}
              alt={`Certificate for ${certificate.product_title}`}
              aspectRatio="16/9"
              objectFit="contain"
              loading="eager"
              sizes="75vw"
            ></s-image>
          ) : (
            <s-box minBlockSize="360px" padding="large">
              <s-text color="subdued">Certificate preview is processing.</s-text>
            </s-box>
          )}
        </s-box>
        <s-stack gap="large">
          <s-stack gap="small-400">
            <s-heading>{certificate.product_title}</s-heading>
            <s-text type="strong">{editionLabel(certificate)}</s-text>
            <s-text color="subdued">
              {purchaseDateLabel(certificate.purchase_date, api.i18n.formatDate)}
            </s-text>
            <s-text color="subdued">Order {certificate.order_name}</s-text>
          </s-stack>
          {certificate.pdf_url ? (
            <s-button
              variant="primary"
              href={absoluteAssetUrl(apiBaseUrl, certificate.pdf_url)}
              target="_blank"
              onClick={() => logEvent(
                api,
                apiBaseUrl,
                "certificate_downloaded",
                eventKeyForCertificate("viewer-download", certificate),
              )}
            >
              Download Certificate
            </s-button>
          ) : (
            <s-badge tone="neutral">Certificate file processing</s-badge>
          )}
          <ViewerSecondaryMenu certificate={certificate} api={api} apiBaseUrl={apiBaseUrl} />
          {frameVariant ? (
            <FrameOffer
              certificate={certificate}
              price={framePrice}
              state={frameState}
              onAdd={() => orderFrame(false)}
              onOrderAnother={() => orderFrame(true)}
            />
          ) : null}
        </s-stack>
      </s-grid>
      <s-button slot="primary-action" command="--hide" commandFor={modalId}>
        Close
      </s-button>
    </s-modal>
  );
}

function ViewerSecondaryMenu({certificate, api, apiBaseUrl}) {
  return (
    <s-stack direction="inline" gap="small" alignItems="center">
      <s-clickable
        accessibilityLabel="More certificate actions"
        command="--show"
        commandFor="viewer-actions"
        padding="small"
        minBlockSize="44px"
        minInlineSize="44px"
      >
        <s-icon type="menu-horizontal"></s-icon>
      </s-clickable>
      <s-menu id="viewer-actions" accessibilityLabel="Certificate actions">
        {certificate.print_url ? (
          <s-button
            href={absoluteAssetUrl(apiBaseUrl, certificate.print_url)}
            target="_blank"
            onClick={() => logEvent(
              api,
              apiBaseUrl,
              "certificate_printed",
              eventKeyForCertificate("viewer-print", certificate),
            )}
          >
            Print certificate
          </s-button>
        ) : null}
        <s-button command="--show" commandFor="viewer-details">
          Certificate details
        </s-button>
      </s-menu>
      <CertificateDetailsModal certificate={certificate} id="viewer-details" />
    </s-stack>
  );
}

function FrameOffer({certificate, price, state, onAdd, onOrderAnother}) {
  const ordered = certificate.frame_status === "ordered" || state.status === "ordered";
  return (
    <s-box padding="base" border="base" borderRadius="base">
      <s-stack gap="base">
        <s-stack gap="small-400">
          <s-heading>Framed Collector Certificate</s-heading>
          <s-text type="strong">Frame the proof.</s-text>
          <s-text>
            Receive your official certificate for {editionLabel(certificate)} professionally printed,
            framed and ready to display.
          </s-text>
        </s-stack>
        <s-stack gap="small-200">
          <s-text>Premium black frame</s-text>
          <s-text>A4 landscape</s-text>
          <s-text>Printed and ready to hang</s-text>
        </s-stack>
        {state.checkoutUrl ? (
          <s-button variant="primary" href={state.checkoutUrl} target="_blank">
            Continue to secure checkout
          </s-button>
        ) : ordered ? (
          <s-stack gap="small">
            <s-badge tone="neutral" icon="check">Framed certificate ordered</s-badge>
            <s-button variant="secondary" onClick={onOrderAnother} loading={state.status === "adding"}>
              Order another
            </s-button>
          </s-stack>
        ) : (
          <s-button variant="primary" onClick={onAdd} loading={state.status === "adding"}>
            Add Framed Certificate — {price}
          </s-button>
        )}
        {state.message ? (
          <s-text color={state.status === "error" ? "base" : "subdued"}>{state.message}</s-text>
        ) : null}
      </s-stack>
    </s-box>
  );
}

function ReviewPrompt({prompt, api, apiBaseUrl, onSubmitted}) {
  const [rating, setRating] = useState(0);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [photo, setPhoto] = useState(null);
  const [photoError, setPhotoError] = useState("");
  const [submitState, setSubmitState] = useState({status: "idle", message: ""});
  const modalId = "collector-review-modal";
  const readerRef = useRef(null);
  const modalRef = useRef(null);

  useEffect(() => {
    logEvent(api, apiBaseUrl, "review_prompt_viewed", dailyEventKey("review-prompt"));
    return () => {
      if (readerRef.current?.readyState === 1) readerRef.current.abort();
    };
  }, [apiBaseUrl]);

  const chooseRating = (value) => {
    setRating(value);
    logEvent(api, apiBaseUrl, "review_started", dailyEventKey(`review-started-${value}`));
  };

  const handlePhoto = (event) => {
    const file = fileFromDropEvent(event);
    const validation = isAllowedReviewPhoto(file);
    if (!validation.ok) {
      setPhoto(null);
      setPhotoError(validation.error);
      return;
    }
    const reader = new FileReader();
    readerRef.current = reader;
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      setPhoto({
        name: file.name,
        mime_type: file.type,
        size: file.size,
        base64: dataUrl.split(",", 2)[1] || "",
        preview: dataUrl,
      });
      setPhotoError("");
      logEvent(api, apiBaseUrl, "review_photo_added", dailyEventKey("review-photo"));
    };
    reader.onerror = () => setPhotoError("Photo could not be read.");
    reader.readAsDataURL(file);
  };

  const submitReview = async () => {
    if (!rating) {
      setSubmitState({status: "error", message: "Choose a star rating."});
      return;
    }
    if (body.trim().length < 10) {
      setSubmitState({status: "error", message: "Review text must be at least 10 characters."});
      return;
    }
    setSubmitState({status: "submitting", message: ""});
    try {
      await vaultRequest(api, apiBaseUrl, "/api/collector-vault/review", {
        method: "POST",
        body: {
          review_reference: prompt.reference,
          rating,
          title,
          body,
          photo: photo ? {
            mime_type: photo.mime_type,
            filename: photo.name,
            base64: photo.base64,
          } : null,
        },
      });
      setSubmitState({status: "submitted", message: "Review submitted ✓"});
      onSubmitted();
      modalRef.current?.hideOverlay();
    } catch (error) {
      setSubmitState({status: "error", message: customerMessage(error)});
    }
  };

  return (
    <s-box padding="base" border="base" borderRadius="base">
      <s-grid gridTemplateColumns="minmax(96px, 140px) minmax(0, 1fr)" gap="base" alignItems="center">
        {prompt.thumbnail_url ? (
          <s-image
            src={absoluteAssetUrl(apiBaseUrl, prompt.thumbnail_url)}
            alt={prompt.product_title}
            aspectRatio="16/9"
            objectFit="contain"
            loading="lazy"
          ></s-image>
        ) : null}
        <s-stack gap="small-400">
          <s-heading>How does it look in your space?</s-heading>
          <s-text color="subdued">
            Share a quick review and help another fan see the real thing.
          </s-text>
          <s-text type="strong">{prompt.product_title}</s-text>
          <StarRating rating={rating} onChange={chooseRating} modalId={modalId} />
          <s-stack direction="inline" gap="small">
            <s-button command="--show" commandFor={modalId} onClick={() => chooseRating(rating || 5)}>
              Leave a Review
            </s-button>
            <s-button command="--show" commandFor={modalId}>
              Add a Photo
            </s-button>
          </s-stack>
        </s-stack>
      </s-grid>
      <s-modal
        ref={modalRef}
        id={modalId}
        heading={`Review ${prompt.product_title}`}
        accessibilityLabel={`Leave a review for ${prompt.product_title}`}
        size="large"
      >
        <s-stack gap="base">
          <StarRating rating={rating} onChange={chooseRating} />
          <s-text-field
            label="Review title (optional)"
            value={title}
            maxLength={120}
            onInput={(event) => setTitle(inputValue(event))}
          ></s-text-field>
          <s-text-area
            label="Your review"
            value={body}
            minLength={10}
            maxLength={2000}
            required
            rows={5}
            onInput={(event) => setBody(inputValue(event))}
          ></s-text-area>
          <s-drop-zone
            label="Add a customer photo (optional)"
            accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
            error={photoError}
                onInput={handlePhoto}
          ></s-drop-zone>
          {photo ? (
            <s-stack gap="small">
              <s-image
                src={photo.preview}
                alt={`Selected review photo ${photo.name}`}
                aspectRatio="16/9"
                objectFit="contain"
              ></s-image>
              <s-stack direction="inline" gap="small" alignItems="center">
                <s-text>{photo.name}</s-text>
                <s-button onClick={() => setPhoto(null)}>Remove photo</s-button>
              </s-stack>
            </s-stack>
          ) : null}
          {submitState.message ? (
            <s-banner tone={submitState.status === "error" ? "critical" : "success"}>
              {submitState.message}
            </s-banner>
          ) : null}
        </s-stack>
        <s-button
          slot="primary-action"
          variant="primary"
          onClick={submitReview}
          loading={submitState.status === "submitting"}
        >
          Submit review
        </s-button>
        <s-button slot="secondary-actions" command="--hide" commandFor={modalId}>
          Cancel
        </s-button>
      </s-modal>
    </s-box>
  );
}

function StarRating({rating, onChange, modalId = ""}) {
  return (
    <s-stack direction="inline" gap="small-200" alignItems="center">
      {[1, 2, 3, 4, 5].map((value) => (
        <s-clickable
          key={value}
          accessibilityLabel={`${value} star${value === 1 ? "" : "s"}`}
          onClick={() => onChange(value)}
          command={modalId ? "--show" : undefined}
          commandFor={modalId || undefined}
          padding="small"
          minBlockSize="44px"
          minInlineSize="44px"
        >
          <s-icon
            type={value <= rating ? "star-filled" : "star"}
            tone={value <= rating ? "warning" : "neutral"}
          ></s-icon>
        </s-clickable>
      ))}
    </s-stack>
  );
}

function Detail({label, value}) {
  return (
    <s-stack gap="small-100">
      <s-text color="subdued">{label}</s-text>
      <s-text>{value || "Unavailable"}</s-text>
    </s-stack>
  );
}

function configuredApiBaseUrl(api) {
  const configured = String(api.settings?.value?.api_base_url || "").trim();
  return (configured || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}

async function vaultRequest(api, apiBaseUrl, path, options = {}) {
  const token = await api.sessionToken.get();
  const method = options.method || "GET";
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method,
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
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || "The request could not be completed.");
  }
  return payload;
}

async function logEvent(api, apiBaseUrl, event, eventKey) {
  try {
    await vaultRequest(api, apiBaseUrl, "/api/collector-vault/events", {
      method: "POST",
      body: {event, event_key: eventKey},
    });
  } catch (_error) {
    // Analytics must never interrupt certificate access.
  }
}

function absoluteAssetUrl(apiBaseUrl, path) {
  const raw = String(path || "");
  return raw.startsWith("https://") ? raw : `${apiBaseUrl}${raw.startsWith("/") ? "" : "/"}${raw}`;
}

function eventKeyForCertificate(prefix, certificate) {
  return `${prefix}:${stableReferencePart(certificate.reference)}`;
}

function stableReferencePart(reference) {
  return String(reference || "").split(".", 1)[0].slice(-48);
}

function dailyEventKey(prefix) {
  return `${prefix}:${new Date().toISOString().slice(0, 10)}`;
}

function customerMessage(error) {
  const message = String(error?.message || "").trim();
  return message || "We could not complete that request. Please try again.";
}
