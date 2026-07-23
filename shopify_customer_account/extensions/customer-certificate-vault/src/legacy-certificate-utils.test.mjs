import assert from "node:assert/strict";
import test from "node:test";

import {
  collectCertificates,
  customerSafeErrorMessage,
} from "./legacy-certificate-utils.js";
import {attachPurchasedArtwork} from "./collection-artwork-utils.js";

const CUSTOMER_A = "gid://shopify/Customer/101";
const CUSTOMER_B = "gid://shopify/Customer/202";
const ORDER_A = "gid://shopify/Order/301";

function certificate(overrides = {}) {
  return {
    shopify_customer_id: CUSTOMER_A,
    shopify_order_id: ORDER_A,
    shopify_order_name: "#1301",
    shopify_line_item_id: "gid://shopify/LineItem/401",
    product_title: "The Mountain Chooses",
    product_handle: "the-mountain-chooses",
    edition_number: 27,
    edition_limit: 100,
    certificate_id: "SC-1301-027",
    certificate_pdf_url: "https://cdn.shopify.com/files/certificate.pdf",
    certificate_preview_image_url: "https://cdn.shopify.com/files/preview.webp",
    ...overrides,
  };
}

function order(records, lineItems = []) {
  return {
    id: ORDER_A,
    name: "#1301",
    processedAt: "2026-06-29T10:00:00Z",
    metafield: {
      jsonValue: {certificates: records},
    },
    lineItems: {
      nodes: lineItems,
    },
  };
}

function lineItem(overrides = {}) {
  return {
    id: "gid://shopify/LineItem/401",
    name: "The Mountain Chooses Wall Art",
    productId: "gid://shopify/Product/501",
    variantId: "gid://shopify/ProductVariant/601",
    sku: "SC-MOUNTAIN-S",
    image: {
      url: "https://cdn.shopify.com/products/mountain.webp",
      altText: "Payne and Feeney artwork",
      width: 1200,
      height: 1200,
    },
    ...overrides,
  };
}

test("owned order metafields return genuine certificate records", () => {
  const rows = collectCertificates(
    [order([certificate()])],
    {id: CUSTOMER_A},
  );
  assert.equal(rows.length, 1);
  assert.equal(rows[0].product_title, "The Mountain Chooses");
  assert.equal(rows[0].edition_display, "#027 / 100");
  assert.equal(
    rows[0].certificate_pdf_url,
    "https://cdn.shopify.com/files/certificate.pdf",
  );
});

test("a customer without certificate metafields gets an empty collection", () => {
  assert.deepEqual(
    collectCertificates(
      [{...order([]), metafield: null}],
      {id: CUSTOMER_A},
    ),
    [],
  );
});

test("a certificate for another customer or order is rejected", () => {
  const rows = collectCertificates(
    [
      order([
        certificate({shopify_customer_id: CUSTOMER_B}),
        certificate({shopify_order_id: "gid://shopify/Order/999"}),
      ]),
    ],
    {id: CUSTOMER_A},
  );
  assert.deepEqual(rows, []);
});

test("a missing preview never removes an otherwise valid certificate", () => {
  const rows = collectCertificates(
    [order([certificate({certificate_preview_image_url: ""})])],
    {id: CUSTOMER_A},
  );
  assert.equal(rows.length, 1);
  assert.equal(rows[0].certificate_preview_image_url, "");
  assert.ok(rows[0].certificate_pdf_url);
});

test("stable line item IDs attach the correct purchased artwork to each edition", () => {
  const records = [
    certificate({
      certificate_id: "SC-1301-027",
      shopify_line_item_id: "gid://shopify/LineItem/401",
      shopify_product_id: "gid://shopify/Product/501",
    }),
    certificate({
      certificate_id: "SC-1301-012",
      shopify_line_item_id: "gid://shopify/LineItem/402",
      shopify_product_id: "gid://shopify/Product/502",
      product_title: "Into the Limit",
      edition_number: 12,
    }),
  ];
  const orderNode = order(records, [
    lineItem(),
    lineItem({
      id: "gid://shopify/LineItem/402",
      name: "Into the Limit Wall Art",
      productId: "gid://shopify/Product/502",
      variantId: "gid://shopify/ProductVariant/602",
      sku: "SC-LIMIT-S",
      image: {
        url: "https://cdn.shopify.com/products/limit.webp",
        altText: "Formula One artwork",
        width: 1400,
        height: 1000,
      },
    }),
  ]);
  const rows = attachPurchasedArtwork(
    collectCertificates([orderNode], {id: CUSTOMER_A}),
    [orderNode],
    {id: CUSTOMER_A},
  );

  assert.equal(rows[0].purchased_image_url, "https://cdn.shopify.com/products/mountain.webp");
  assert.equal(rows[0].purchased_image_alt, "Payne and Feeney artwork");
  assert.equal(rows[1].purchased_image_url, "https://cdn.shopify.com/products/limit.webp");
  assert.equal(rows[1].purchased_image_alt, "Formula One artwork");
});

test("duplicate purchases remain mapped by their distinct line item IDs", () => {
  const records = [
    certificate({
      certificate_id: "SC-1301-027",
      shopify_line_item_id: "401",
      shopify_product_id: "gid://shopify/Product/501",
    }),
    certificate({
      certificate_id: "SC-1301-028",
      shopify_line_item_id: "402",
      shopify_product_id: "gid://shopify/Product/501",
      edition_number: 28,
    }),
  ];
  const orderNode = order(records, [
    lineItem(),
    lineItem({
      id: "gid://shopify/LineItem/402",
      image: {
        url: "https://cdn.shopify.com/products/mountain-second.webp",
        altText: "",
        width: 1200,
        height: 1200,
      },
    }),
  ]);
  const rows = attachPurchasedArtwork(
    collectCertificates([orderNode], {id: CUSTOMER_A}),
    [orderNode],
    {id: CUSTOMER_A},
  );

  assert.equal(rows[0].purchased_image_url, "https://cdn.shopify.com/products/mountain.webp");
  assert.equal(rows[1].purchased_image_url, "https://cdn.shopify.com/products/mountain-second.webp");
  assert.equal(
    rows[1].purchased_image_alt,
    "The Mountain Chooses Wall Art purchased artwork",
  );
});

test("product title changes do not affect stable product ID matching", () => {
  const record = certificate({
    shopify_line_item_id: "",
    shopify_product_id: "gid://shopify/Product/501",
    product_title: "Original Product Name",
  });
  const orderNode = order([record], [
    lineItem({name: "Completely Renamed Product"}),
  ]);
  const rows = attachPurchasedArtwork(
    collectCertificates([orderNode], {id: CUSTOMER_A}),
    [orderNode],
    {id: CUSTOMER_A},
  );

  assert.equal(rows[0].purchased_image_url, "https://cdn.shopify.com/products/mountain.webp");
});

test("missing or ambiguous line item images never attach the wrong artwork", () => {
  const missingImageRecord = certificate({
    shopify_line_item_id: "gid://shopify/LineItem/401",
    shopify_product_id: "gid://shopify/Product/501",
  });
  const missingImageOrder = order([missingImageRecord], [
    lineItem({image: null}),
  ]);
  const missingImageRows = attachPurchasedArtwork(
    collectCertificates([missingImageOrder], {id: CUSTOMER_A}),
    [missingImageOrder],
    {id: CUSTOMER_A},
  );
  assert.equal(missingImageRows[0].purchased_image_url, undefined);
  assert.ok(missingImageRows[0].certificate_preview_image_url);

  const ambiguousRecord = certificate({
    shopify_line_item_id: "",
    shopify_variant_id: "",
    shopify_product_id: "gid://shopify/Product/501",
    sku: "",
  });
  const ambiguousOrder = order([ambiguousRecord], [
    lineItem(),
    lineItem({
      id: "gid://shopify/LineItem/402",
      image: {
        url: "https://cdn.shopify.com/products/wrong.webp",
        altText: "Wrong item",
      },
    }),
  ]);
  const ambiguousRows = attachPurchasedArtwork(
    collectCertificates([ambiguousOrder], {id: CUSTOMER_A}),
    [ambiguousOrder],
    {id: CUSTOMER_A},
  );
  assert.equal(ambiguousRows[0].purchased_image_url, undefined);
});

test("only explicit authentication failures use session-expired copy", () => {
  assert.match(
    customerSafeErrorMessage({status: 401}),
    /session has expired/,
  );
  assert.match(
    customerSafeErrorMessage(new Error("database unavailable")),
    /could not load/,
  );
  assert.doesNotMatch(
    customerSafeErrorMessage(new Error("database unavailable")),
    /session has expired/,
  );
});
