export function collectionSubheading(count) {
  const value = Number.isFinite(Number(count)) ? Number(count) : 0;
  return `${value} authenticated ${value === 1 ? "edition" : "editions"}`;
}

export function editionLabel(certificate) {
  const number = positiveInt(certificate?.edition_number);
  const limit = positiveInt(certificate?.edition_limit);
  if (!number || !limit) return "Edition details pending";
  return `Edition #${String(number).padStart(3, "0")} of ${limit}`;
}

export function purchaseDateLabel(value, formatter) {
  const raw = String(value || "").trim();
  if (!raw) return "Purchase date unavailable";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return `Purchased ${raw}`;
  const formatted = formatter
    ? formatter(date, {day: "numeric", month: "long", year: "numeric"})
    : new Intl.DateTimeFormat(undefined, {
        day: "numeric",
        month: "long",
        year: "numeric",
      }).format(date);
  return `Purchased ${formatted}`;
}

export function formatFramePrice(money, formatNumber) {
  const amount = Number(money?.amount);
  const currency = String(money?.currencyCode || "").toUpperCase();
  if (!Number.isFinite(amount) || !currency) return "";
  const digits = Number.isInteger(amount) ? 0 : 2;
  const number = formatNumber
    ? formatNumber(amount, {
        minimumFractionDigits: digits,
        maximumFractionDigits: 2,
      })
    : amount.toLocaleString(undefined, {
        minimumFractionDigits: digits,
        maximumFractionDigits: 2,
      });
  const prefixes = {
    AUD: "AU$",
    USD: "US$",
    CAD: "CA$",
    NZD: "NZ$",
    GBP: "£",
    EUR: "€",
  };
  return `${prefixes[currency] || `${currency} `}${number}`;
}

export function chooseFrameVariant(
  product,
  configuredVariantId,
  expectedHandle = "framed-collector-certificate",
  expectedProductId = "",
) {
  if (
    !product
    || (expectedHandle && product.handle !== expectedHandle)
    || (expectedProductId && product.id !== expectedProductId)
    || !product.availableForSale
  ) return null;
  const variants = product.variants?.nodes || [];
  const selected = configuredVariantId
    ? variants.find((variant) => variant.id === configuredVariantId)
    : variants[0];
  const amount = Number(selected?.price?.amount);
  const currency = String(selected?.price?.currencyCode || "").trim();
  return selected?.availableForSale && Number.isFinite(amount) && currency ? selected : null;
}

export function frameCartInput(variantId, requestReference) {
  return {
    lines: [
      {
        merchandiseId: variantId,
        quantity: 1,
        attributes: [
          {
            key: "_sports_cave_frame_request",
            value: requestReference,
          },
        ],
      },
    ],
  };
}

export function inputValue(event) {
  return String(event?.currentTarget?.value ?? event?.target?.value ?? "");
}

export function fileFromDropEvent(event) {
  const candidates = [
    event?.files,
    event?.detail?.files,
    event?.currentTarget?.files,
    event?.target?.files,
  ];
  for (const candidate of candidates) {
    if (candidate && candidate.length) return candidate[0];
  }
  return null;
}

export function isAllowedReviewPhoto(file, maxBytes = 6 * 1024 * 1024) {
  if (!file) return {ok: false, error: "Choose a JPG, PNG or WebP image."};
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    return {ok: false, error: "Photo must be a JPG, PNG or WebP image."};
  }
  if (!Number(file.size) || Number(file.size) > maxBytes) {
    return {ok: false, error: "Photo must be smaller than 6 MB."};
  }
  return {ok: true, error: ""};
}

export function positiveInt(value) {
  const number = Number.parseInt(value, 10);
  return Number.isFinite(number) && number > 0 ? number : 0;
}
