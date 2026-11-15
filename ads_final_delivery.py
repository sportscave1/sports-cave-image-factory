"""Final delivery instructions only; never changes image generation or CSV."""

VERSION = "SPORTS CAVE FINAL IMAGE DOWNLOAD LINKS V1"
RULES = f"""{VERSION}
At the end of every completed three-image ad package, alongside the existing downloadable CSV link, also provide three separate clickable download links in the original generation order, labelled exactly:
- Download Ad 1 — [existing scene name]
- Download Ad 2 — [existing scene name]
- Download Ad 3 — [existing scene name]
Replace each bracketed placeholder with that image's existing assigned scene name, verbatim; do not invent or rename scenes. Each link must point to its corresponding actual completed generated image file, retaining the Ad 1/2/3 association. Reuse the existing generated files and the environment's real attachment/download links. Do not regenerate, modify or duplicate images to provide these links, and never invent URLs or claim a missing file exists. If an actual file/link is unavailable, report that specific unavailable download honestly without generating another image. This is an addition to final delivery only: preserve the existing CSV link, schema, ad copy, image count and generation workflow unchanged."""


def apply_final_delivery(prompt):
    return prompt if RULES in prompt else RULES + "\n\n" + prompt
