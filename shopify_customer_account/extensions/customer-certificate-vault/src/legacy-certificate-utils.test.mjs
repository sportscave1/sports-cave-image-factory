import assert from "node:assert/strict";
import test from "node:test";

import {
  collectCertificates,
  customerSafeErrorMessage,
} from "./legacy-certificate-utils.js";

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

function order(records) {
  return {
    id: ORDER_A,
    name: "#1301",
    processedAt: "2026-06-29T10:00:00Z",
    metafield: {
      jsonValue: {certificates: records},
    },
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
