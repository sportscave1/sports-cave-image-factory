import {
  certificatesFromMetafield,
  normalizeCertificate,
  safeHttpsUrl,
} from "./legacy-certificate-utils.js";

export function attachPurchasedArtwork(certificates, orders, customer) {
  const certificateKeys = new Set(
    (certificates || []).map((certificate) => certificate.key),
  );
  const artworkByCertificateKey = new Map();

  for (const order of orders || []) {
    const lineItems = lineItemNodes(order);
    if (!lineItems.length) continue;

    for (const record of certificatesFromMetafield(order.metafield)) {
      const certificate = normalizeCertificate(record, order, customer);
      if (
        !certificate
        || !certificateKeys.has(certificate.key)
        || artworkByCertificateKey.has(certificate.key)
      ) {
        continue;
      }
      const artwork = artworkFromLineItem(
        matchPurchasedLineItem(record, lineItems),
      );
      if (artwork) {
        artworkByCertificateKey.set(certificate.key, artwork);
      }
    }
  }

  return (certificates || []).map((certificate) => {
    const artwork = artworkByCertificateKey.get(certificate.key);
    return artwork ? {...certificate, ...artwork} : certificate;
  });
}

export function matchPurchasedLineItem(record, lineItems) {
  const items = (lineItems || []).filter(Boolean);
  if (!record || !items.length) return null;

  const identifiers = [
    [
      record.shopify_line_item_id || record.line_item_id,
      (item) => item.id,
    ],
    [
      record.shopify_variant_id || record.variant_id,
      (item) => item.variantId,
    ],
    [
      record.shopify_product_id || record.product_id,
      (item) => item.productId,
    ],
    [
      record.sku || record.variant_sku || record.product_sku,
      (item) => item.sku,
    ],
  ];

  for (const [recordValue, lineItemValue] of identifiers) {
    const match = uniqueIdentifierMatch(items, recordValue, lineItemValue);
    if (match) return match;
  }

  return items.length === 1 ? items[0] : null;
}

function lineItemNodes(order) {
  const connection = order?.lineItems;
  if (Array.isArray(connection)) return connection;
  if (Array.isArray(connection?.nodes)) return connection.nodes;
  if (Array.isArray(connection?.edges)) {
    return connection.edges.map((edge) => edge?.node).filter(Boolean);
  }
  return [];
}

function uniqueIdentifierMatch(items, expectedValue, itemValue) {
  const expected = identifierValue(expectedValue);
  if (!expected) return null;
  const matches = items.filter(
    (item) => identifierValue(itemValue(item)) === expected,
  );
  return matches.length === 1 ? matches[0] : null;
}

function artworkFromLineItem(lineItem) {
  const imageUrl = safeHttpsUrl(lineItem?.image?.url);
  if (!imageUrl) return null;
  const suppliedAlt = stringValue(lineItem.image.altText);
  const lineItemName = stringValue(lineItem.name);
  return {
    purchased_image_url: imageUrl,
    purchased_image_alt: suppliedAlt
      || `${lineItemName || "Sports Cave artwork"} purchased artwork`,
    purchased_image_width: positiveInt(lineItem.image.width),
    purchased_image_height: positiveInt(lineItem.image.height),
  };
}

function identifierValue(value) {
  const raw = stringValue(value);
  if (!raw) return "";
  const parts = raw.split("/").filter(Boolean);
  return parts[parts.length - 1] || raw;
}

function stringValue(value) {
  return String(value || "").trim();
}

function positiveInt(value) {
  const number = Number.parseInt(value, 10);
  return Number.isFinite(number) && number > 0 ? number : 0;
}
