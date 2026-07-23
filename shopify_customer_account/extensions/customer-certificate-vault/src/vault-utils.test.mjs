import assert from "node:assert/strict";
import test from "node:test";

import {
  chooseFrameVariant,
  collectionSubheading,
  editionLabel,
  formatFramePrice,
  frameCartInput,
  isAllowedReviewPhoto,
  purchaseDateLabel,
} from "./vault-utils.js";


test("certificate count uses correct singular and plural copy", () => {
  assert.equal(collectionSubheading(0), "0 authenticated editions");
  assert.equal(collectionSubheading(1), "1 authenticated edition");
  assert.equal(collectionSubheading(4), "4 authenticated editions");
});

test("edition and purchase labels use collector wording", () => {
  assert.equal(
    editionLabel({edition_number: 27, edition_limit: 100}),
    "Edition #027 of 100",
  );
  assert.equal(
    purchaseDateLabel("2026-06-29T00:00:00Z", () => "29 June 2026"),
    "Purchased 29 June 2026",
  );
});

test("contextual Shopify money is unambiguous without redundant decimals", () => {
  const number = (value, options) => new Intl.NumberFormat("en-AU", options).format(value);
  assert.equal(formatFramePrice({amount: "99.00", currencyCode: "AUD"}, number), "AU$99");
  assert.equal(formatFramePrice({amount: "99.50", currencyCode: "USD"}, number), "US$99.50");
  assert.equal(formatFramePrice({amount: "80", currencyCode: "GBP"}, number), "£80");
});

test("frame variant must match configured handle, id and availability", () => {
  const product = {
    id: "gid://shopify/Product/10",
    handle: "framed-collector-certificate",
    availableForSale: true,
    variants: {
      nodes: [
        {id: "gid://shopify/ProductVariant/1", availableForSale: false},
        {
          id: "gid://shopify/ProductVariant/2",
          availableForSale: true,
          price: {amount: "99", currencyCode: "AUD"},
        },
      ],
    },
  };
  assert.equal(
    chooseFrameVariant(
      product,
      "gid://shopify/ProductVariant/2",
      "framed-collector-certificate",
      "gid://shopify/Product/10",
    )?.id,
    "gid://shopify/ProductVariant/2",
  );
  assert.equal(
    chooseFrameVariant(
      product,
      "gid://shopify/ProductVariant/2",
      "framed-collector-certificate",
      "gid://shopify/Product/11",
    ),
    null,
  );
  assert.equal(
    chooseFrameVariant(
      {...product, handle: "framed-collector-certificate-renamed"},
      "gid://shopify/ProductVariant/2",
      "",
      "gid://shopify/Product/10",
    )?.id,
    "gid://shopify/ProductVariant/2",
  );
  assert.equal(chooseFrameVariant(product, "gid://shopify/ProductVariant/1"), null);
  assert.equal(chooseFrameVariant({...product, handle: "wrong-product"}, ""), null);
  assert.equal(
    chooseFrameVariant({
      ...product,
      variants: {nodes: [{id: "missing-price", availableForSale: true}]},
    }, ""),
    null,
  );
});

test("cart line contains only the opaque private frame request reference", () => {
  const input = frameCartInput(
    "gid://shopify/ProductVariant/2",
    "5f99e0d2-724d-42d4-8ac2-8d62ca823e1b",
  );
  assert.deepEqual(input.lines[0], {
    merchandiseId: "gid://shopify/ProductVariant/2",
    quantity: 1,
    attributes: [
      {
        key: "_sports_cave_frame_request",
        value: "5f99e0d2-724d-42d4-8ac2-8d62ca823e1b",
      },
    ],
  });
  assert.equal(JSON.stringify(input).includes("email"), false);
  assert.equal(JSON.stringify(input).includes("certificate_id"), false);
});

test("review photo client validation matches server limits", () => {
  assert.equal(
    isAllowedReviewPhoto({type: "image/webp", size: 1024, name: "room.webp"}).ok,
    true,
  );
  assert.equal(
    isAllowedReviewPhoto({type: "image/svg+xml", size: 1024, name: "room.svg"}).ok,
    false,
  );
  assert.equal(
    isAllowedReviewPhoto({type: "image/jpeg", size: 7 * 1024 * 1024, name: "huge.jpg"}).ok,
    false,
  );
});
