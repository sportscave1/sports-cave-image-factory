export function collectCertificates(orders, customer) {
  const seen = new Set();
  const rows = [];

  for (const order of orders || []) {
    const certificates = certificatesFromMetafield(order.metafield);
    for (const certificate of certificates) {
      const normalized = normalizeCertificate(certificate, order, customer);
      if (!normalized || seen.has(normalized.key)) continue;
      seen.add(normalized.key);
      rows.push(normalized);
    }
  }

  return rows;
}

export function certificatesFromMetafield(metafield) {
  if (!metafield) return [];
  const raw = metafield.jsonValue ?? metafield.value;
  const parsed = typeof raw === "string" ? parseJson(raw) : raw;
  if (Array.isArray(parsed)) return parsed;
  return Array.isArray(parsed?.certificates) ? parsed.certificates : [];
}

export function normalizeCertificate(record, order, customer) {
  if (!record || typeof record !== "object") return null;
  if (!matchesContext(record.shopify_customer_id, customer?.id)) return null;
  if (!matchesContext(record.shopify_order_id, order?.id)) return null;
  const recordOrderName = stringValue(
    record.shopify_order_name || record.order_name,
  );
  if (recordOrderName && order?.name && recordOrderName !== order.name) return null;

  const orderName = stringValue(recordOrderName || order.name);
  const lineItemId = stringValue(record.shopify_line_item_id);
  const editionNumber = positiveInt(record.edition_number);
  const unitIndex = positiveInt(record.line_item_unit_index) || 1;
  const certificateId = stringValue(record.certificate_id);

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
    purchase_date: stringValue(
      record.purchase_date || record.created_at || order.processedAt,
    ),
    purchase_date_display: dateDisplay(
      record.purchase_date || record.created_at || order.processedAt,
    ),
    certificate_pdf_url: safeHttpsUrl(
      record.certificate_pdf_url
      || record.certificate_file_url
      || record.pdf_url,
    ),
    certificate_print_jpg_url: safeHttpsUrl(
      record.certificate_print_jpg_url,
    ),
    certificate_preview_image_url: safeHttpsUrl(
      record.certificate_preview_image_url,
    ),
  };
}

export function collectionSummary(certificates) {
  const releaseKeys = new Set();
  for (const certificate of certificates || []) {
    releaseKeys.add(
      certificate.product_handle
      || certificate.product_title
      || certificate.certificate_id,
    );
  }
  const latest = (certificates || [])[0] || {};
  return {
    certificateCount: (certificates || []).length,
    releaseCount: releaseKeys.size,
    latestEdition: latest.edition_display || "",
    latestProduct: latest.product_title || "",
  };
}

export function customerSafeErrorMessage(error) {
  if (isAuthenticationError(error)) {
    return "Your customer session has expired. Refresh this page and sign in again.";
  }

  const raw = errorText(error).toLowerCase();
  if (
    raw.includes("access denied")
    || raw.includes("customer_read_customers")
    || raw.includes("customer_read_orders")
    || raw.includes("scope")
  ) {
    return "Certificate permissions are still being updated. Please try again shortly.";
  }
  return "We could not load your Sports Cave certificates. Please try again.";
}

export function isAuthenticationError(error) {
  if (Number(error?.status) === 401) return true;
  return (error?.graphQLErrors || []).some((item) => (
    String(item?.extensions?.code || "").toUpperCase() === "UNAUTHENTICATED"
  ));
}

export function editionDisplay(record) {
  const number = positiveInt(record.edition_number);
  const total = positiveInt(record.edition_limit || record.edition_total);
  if (number && total) return `#${String(number).padStart(3, "0")} / ${total}`;

  const display = stringValue(record.display_edition || record.edition_display);
  return display.includes("/") ? display.replace("/", " / ") : display;
}

export function dateDisplay(value) {
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

export function safeHttpsUrl(value) {
  const raw = stringValue(value);
  if (!raw) return "";
  try {
    const url = new URL(raw);
    return url.protocol === "https:" ? raw : "";
  } catch (_error) {
    return "";
  }
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

function errorText(error) {
  if (Array.isArray(error?.graphQLErrors)) {
    return error.graphQLErrors.map((item) => item?.message || "").join(" ");
  }
  if (Array.isArray(error)) {
    return error.map((item) => item?.message || "").join(" ");
  }
  return error instanceof Error
    ? error.message
    : String(error || "").trim();
}
