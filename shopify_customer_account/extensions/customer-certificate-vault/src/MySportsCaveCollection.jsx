/** @jsxImportSource preact */
import "@shopify/ui-extensions/preact";
import {render} from "preact";
import {useEffect, useMemo, useState} from "preact/hooks";

const API_VERSION = "2026-04";

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

  const certificateCount = useMemo(() => certificates.length, [certificates]);

  return (
    <s-page
      heading="My Sports Cave Collection"
      subheading="Your numbered Sports Cave collector certificates."
    >
      {status === "loading" ? <LoadingState /> : null}
      {status === "error" ? <ErrorState message={errorMessage} /> : null}
      {status === "ready" && certificateCount === 0 ? <EmptyState /> : null}
      {status === "ready" && certificateCount > 0 ? (
        <s-stack gap="base">
          {certificates.map((certificate) => (
            <CertificateCard key={certificate.key} certificate={certificate} />
          ))}
        </s-stack>
      ) : null}
    </s-page>
  );
}

function LoadingState() {
  return (
    <s-section>
      <s-stack direction="inline" gap="base" alignItems="center">
        <s-spinner size="base" accessibilityLabel="Loading certificates"></s-spinner>
        <s-text>Loading certificates...</s-text>
      </s-stack>
    </s-section>
  );
}

function EmptyState() {
  return (
    <s-section heading="No certificates yet">
      <s-stack gap="base">
        <s-text>
          No Sports Cave certificates found for this account yet.
        </s-text>
        <s-link href="shopify:customer-account/orders">View your orders</s-link>
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

function CertificateCard({certificate}) {
  const isReady = certificate.certificate_status === "Ready" && Boolean(certificate.certificate_file_url);

  return (
    <s-box padding="base" border="base" borderRadius="base">
      <s-stack gap="base">
        <s-stack gap="small-400">
          <s-heading>{certificate.product_title || "Sports Cave limited edition"}</s-heading>
          {certificate.variant_title ? <s-text color="subdued">{certificate.variant_title}</s-text> : null}
        </s-stack>

        <s-grid gridTemplateColumns="1fr 1fr" gap="base">
          <CertificateDetail label="Edition" value={certificate.edition_display} />
          <CertificateDetail label="Certificate ID" value={certificate.certificate_id} />
          <CertificateDetail label="Order" value={certificate.shopify_order_name} />
          <CertificateDetail label="Purchased" value={certificate.purchase_date_display} />
        </s-grid>

        {isReady ? (
          <s-link href={certificate.certificate_file_url}>Download Certificate</s-link>
        ) : (
          <s-badge tone="neutral">Certificate processing</s-badge>
        )}
      </s-stack>
    </s-box>
  );
}

function CertificateDetail({label, value}) {
  return (
    <s-stack gap="small-100">
      <s-text color="subdued">{label}</s-text>
      <s-text>{value || "-"}</s-text>
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
  const url = safeHttpsUrl(record.certificate_file_url || record.certificate_pdf_url);
  const status = stringValue(record.certificate_status || record.shopify_file_status);
  const statusKey = status.toLowerCase();
  const ready = ["ready", "uploaded", "certificate ready"].includes(statusKey) && Boolean(url);

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
    certificate_file_url: ready ? url : "",
    certificate_status: ready ? "Ready" : "Processing",
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
  if (number && total) return `Edition #${String(number).padStart(3, "0")} of ${total}`;

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
    month: "short",
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
