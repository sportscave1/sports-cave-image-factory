/** @jsxImportSource preact */
import "@shopify/ui-extensions/preact";
import {render} from "preact";
import {useEffect, useMemo, useState} from "preact/hooks";

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

  useEffect(() => {
    let mounted = true;

    async function loadCertificates() {
      try {
        const response = await fetch(
          `shopify://customer-account/api/${API_VERSION}/graphql.json`,
          {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({query: CERTIFICATES_QUERY}),
          },
        );
        const payload = await response.json();
        if (payload.errors?.length) {
          throw new Error(customerSafeErrorMessage(payload.errors));
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
  }, []);

  const summary = useMemo(() => collectionSummary(certificates), [certificates]);

  return (
    <s-page
      heading="My Collection"
      subheading="Your numbered Sports Cave collector certificates."
    >
      <VaultIntro />
      {status === "loading" ? <LoadingState /> : null}
      {status === "error" ? <ErrorState message={errorMessage} /> : null}
      {status === "ready" && certificates.length === 0 ? <EmptyState /> : null}
      {status === "ready" && certificates.length > 0 ? (
        <s-stack gap="base">
          <CollectorSummary summary={summary} />
          {certificates.map((certificate) => (
            <CertificateCard key={certificate.key} certificate={certificate} />
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
          Every numbered release in your collection is recorded here with its official certificate of authenticity.
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
        <s-spinner size="base" accessibilityLabel="Loading certificates"></s-spinner>
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
          When you purchase a numbered Sports Cave release, your certificate of authenticity will appear here.
        </s-text>
        <s-link href={SHOP_LATEST_DROPS_URL} target="_blank">
          Shop Latest Drops
        </s-link>
      </s-stack>
    </s-section>
  );
}

function ErrorState({message}) {
  return (
    <s-banner heading="Certificates unavailable" tone="critical">
      {message || "Certificate vault permissions are still being updated. Please try again shortly."}
    </s-banner>
  );
}

function CollectorSummary({summary}) {
  return (
    <s-section heading="Collector Record">
      <s-grid gridTemplateColumns="repeat(auto-fit, minmax(150px, 1fr))" gap="base">
        <SummaryTile label="Certificates owned" value={String(summary.certificateCount)} />
        <SummaryTile label="Numbered releases" value={String(summary.releaseCount)} />
        <SummaryTile label="Latest edition" value={summary.latestEdition || "-"} />
        <SummaryTile label="Collector status" value="Active Collector" />
      </s-grid>
      {summary.latestProduct ? (
        <s-text color="subdued">Latest addition: {summary.latestProduct}</s-text>
      ) : null}
    </s-section>
  );
}

function SummaryTile({label, value}) {
  return (
    <s-box padding="base" border="base" borderRadius="base" background="subdued">
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
    <s-box padding="base" border="base" borderRadius="base" background="subdued">
      <s-stack gap="base">
        <s-stack direction="inline" gap="small">
          <s-badge tone="neutral">Numbered Collector Release</s-badge>
          <s-badge tone="neutral">Official Certificate</s-badge>
          <s-badge tone="neutral">Verified Sports Cave Record</s-badge>
        </s-stack>

        <s-grid gridTemplateColumns="repeat(auto-fit, minmax(260px, 1fr))" gap="base">
          <s-stack gap="base">
            <s-stack gap="small-400">
              <s-heading>{certificate.product_title || "Sports Cave limited edition"}</s-heading>
              {certificate.variant_title ? <s-text color="subdued">{certificate.variant_title}</s-text> : null}
            </s-stack>

            <s-grid gridTemplateColumns="repeat(auto-fit, minmax(150px, 1fr))" gap="base">
              <CertificateDetail label="Edition" value={certificate.edition_display} />
              <CertificateDetail label="Order" value={certificate.shopify_order_name} />
              <CertificateDetail label="Purchased" value={certificate.purchase_date_display} />
              <CertificateIdDetail value={certificate.certificate_id} />
            </s-grid>
          </s-stack>

          <s-stack gap="base">
            {hasPreview ? (
              <s-image
                src={certificate.certificate_preview_image_url}
                alt={`Certificate preview for ${certificate.product_title || "Sports Cave artwork"}`}
                aspectRatio="16/9"
                objectFit="cover"
                loading="lazy"
              ></s-image>
            ) : (
              <s-box padding="base" border="base" borderRadius="base">
                <s-stack gap="small-200">
                  <s-text type="strong">Certificate preview coming soon</s-text>
                  <s-text color="subdued">Your official PDF certificate is still available below.</s-text>
                </s-stack>
              </s-box>
            )}
          </s-stack>
        </s-grid>

        <s-stack direction="inline" gap="base">
          {hasPdf ? (
            <CertificateAssetButton href={certificate.certificate_pdf_url} label="View Certificate" variant="primary" />
          ) : null}
          {hasPrint ? (
            <CertificateAssetButton href={certificate.certificate_print_jpg_url} label="Download Print Certificate" />
          ) : null}
          {hasPdf ? (
            <CertificateAssetButton href={certificate.certificate_pdf_url} label="Download PDF" />
          ) : null}
          {!hasPdf ? <s-badge tone="neutral">Certificate processing</s-badge> : null}
        </s-stack>

        {(hasPdf || hasPrint) ? (
          <s-text color="subdued">Opens in a new tab. Use your browser save or download option to print.</s-text>
        ) : null}
      </s-stack>
    </s-box>
  );
}

function CertificateAssetButton({href, label, variant = "secondary"}) {
  if (variant === "primary") {
    return (
      <s-button href={href} target="_blank" variant="primary">
        {label}
      </s-button>
    );
  }

  return (
    <s-button href={href} target="_blank" variant="secondary">
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

function collectCertificates(orders, customer) {
  const seen = new Set();
  const rows = [];

  for (const order of orders || []) {
    const certificates = certificatesFromMetafield(order.metafield);
    for (const certificate of certificates) {
      const normalized = normalizeCertificate(certificate, order, customer);
      if (!normalized) continue;
      if (seen.has(normalized.key)) continue;
      seen.add(normalized.key);
      rows.push(normalized);
    }
  }

  return rows;
}

function certificatesFromMetafield(metafield) {
  if (!metafield) return [];
  const raw = metafield.jsonValue ?? metafield.value;
  const parsed = typeof raw === "string" ? parseJson(raw) : raw;
  if (Array.isArray(parsed)) return parsed;
  return Array.isArray(parsed?.certificates) ? parsed.certificates : [];
}

function normalizeCertificate(record, order, customer) {
  if (!record || typeof record !== "object") return null;
  if (!matchesContext(record.shopify_customer_id, customer?.id)) return null;
  if (!matchesContext(record.shopify_order_id, order?.id)) return null;
  const recordOrderName = stringValue(record.shopify_order_name || record.order_name);
  if (recordOrderName && order?.name && recordOrderName !== order.name) return null;

  const orderName = stringValue(recordOrderName || order.name);
  const lineItemId = stringValue(record.shopify_line_item_id);
  const editionNumber = positiveInt(record.edition_number);
  const unitIndex = positiveInt(record.line_item_unit_index) || 1;
  const certificateId = stringValue(record.certificate_id);
  const pdfUrl = safeHttpsUrl(record.certificate_pdf_url || record.certificate_file_url || record.pdf_url);
  const printUrl = safeHttpsUrl(record.certificate_print_jpg_url);
  const previewUrl = safeHttpsUrl(record.certificate_preview_image_url);

  return {
    key: [
      orderName,
      lineItemId,
      editionNumber || "",
      unitIndex,
      certificateId,
    ].join("|"),
    product_title: stringValue(record.product_title),
    product_handle: stringValue(record.product_handle),
    variant_title: stringValue(record.variant_title),
    edition_display: editionDisplay(record),
    certificate_id: certificateId,
    shopify_order_name: orderName,
    purchase_date: stringValue(record.purchase_date || record.created_at || order.processedAt),
    purchase_date_display: dateDisplay(record.purchase_date || record.created_at || order.processedAt),
    certificate_pdf_url: pdfUrl,
    certificate_print_jpg_url: printUrl,
    certificate_preview_image_url: previewUrl,
  };
}

function collectionSummary(certificates) {
  const releaseKeys = new Set();
  for (const certificate of certificates || []) {
    releaseKeys.add(certificate.product_handle || certificate.product_title || certificate.certificate_id);
  }
  const latest = (certificates || [])[0] || {};
  return {
    certificateCount: (certificates || []).length,
    releaseCount: releaseKeys.size,
    latestEdition: latest.edition_display || "",
    latestProduct: latest.product_title || "",
  };
}

function matchesContext(recordValue, contextValue) {
  const recordText = stringValue(recordValue);
  const contextText = stringValue(contextValue);
  return !recordText || !contextText || recordText === contextText;
}

function parseJson(value) {
  try {
    return JSON.parse(value || "{}");
  } catch (_error) {
    return {};
  }
}

function stringValue(value) {
  return String(value || "").trim();
}

function positiveInt(value) {
  const number = Number.parseInt(value, 10);
  return Number.isFinite(number) && number > 0 ? number : 0;
}

function editionDisplay(record) {
  const number = positiveInt(record.edition_number);
  const total = positiveInt(record.edition_limit || record.edition_total);
  if (number && total) return `#${String(number).padStart(3, "0")} / ${total}`;

  const display = stringValue(record.display_edition || record.edition_display);
  return display.includes("/") ? display.replace("/", " / ") : display;
}

function dateDisplay(value) {
  const raw = stringValue(value);
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

function safeHttpsUrl(value) {
  const raw = stringValue(value);
  if (!raw) return "";
  try {
    const url = new URL(raw);
    return url.protocol === "https:" ? raw : "";
  } catch (_error) {
    return "";
  }
}

function customerSafeErrorMessage(error) {
  const raw = Array.isArray(error)
    ? error.map((item) => item?.message || "").join(" ")
    : error instanceof Error
      ? error.message
      : stringValue(error);
  const normalized = raw.toLowerCase();
  if (
    normalized.includes("access denied")
    || normalized.includes("customer_read_customers")
    || normalized.includes("customer_read_orders")
    || normalized.includes("scope")
  ) {
    return "Certificate vault permissions are still being updated. Please try again shortly.";
  }
  return "We could not load your Sports Cave certificates. Please try again later.";
}
