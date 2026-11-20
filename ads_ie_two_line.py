"""Baseline 2.0 two-line variant; scenes and candidate pairs stay unchanged."""
import hashlib
import random
import re

VERSION = "SPORTS CAVE BASELINE 2.0 — TWO-LINE FOOTER V1"
FIELDS = ("footer_layout_version", "footer_second_line_kind", "footer_second_line", "meta_headline_text")

FOOTER_RULES = f"""{VERSION}
Use the Baseline 2.0 full-width opaque matte-black footer, exactly 160 px high
at 1024 × 1024; top seam is y=864, photograph 864 px (84.375%). Scale by output
width / 1024 for other sizes. Keep the existing thin champagne-gold shimmer
at the photo/footer seam, replacing the top separator in place, with softly
varying specular sheen, never a flat rule.
No added footer badge or PNG overlay. Preserve the original product, frame, rooms and glazing.
Render exactly two centred text baselines, never three:
Line 1: the exact assigned 100-variation HEADLINE from the existing approved bank.
Title type: 50 px Baskerville-style editorial serif Medium (500), warm ivory #F3EBDD,
natural kerning plus 0.03 em letter spacing. Keep gold 100 digits and their fine
underline inline, not a quantity caption or extra row.
Line 2: only the exact assigned FOOTER SECOND LINE. If kind is CTA, render
CLAIM YOUR EDITION using CTA type: 23 px Montserrat Medium, antique gold
#C7A15A, 0.10 em letter spacing. If kind is FOMO, render its exact supporting sentence
using Supporting type: 22 px Montserrat Regular, warm off-white #C5C0B5, natural kerning.
Keep 64 px horizontal margins. Centre these two lines within the same 160 px
panel: 32 px top padding, 58 px title line box, 10 px gap, 28 px second-line
box and 32 px bottom padding. No wrap, extra caption, separate CTA row or blank
third text row. Typography and colours remain Baseline 2.0; never restyle text
printed inside the original framed edition. The black footer remains fully opaque.
Inspect the actual exported JPEG at full size and 256 px: exactly these two
baselines, exact wording, title prominence, clear spacing and metallic shimmer.
Correct defects through the existing final creative review before export.
"""

HEADLINE_RULES = """WRITTEN META HEADLINE — UNUSED FOOTER LINE
For each ad, use its supplied META HEADLINE verbatim in displayed AD COPY and
the existing CSV headline cell. It is the exact line omitted from that image's
footer. When the footer's second line is CLAIM YOUR EDITION, the Meta headline
is that ad's selected FOMO sentence. When the footer's second line is the FOMO
sentence, the Meta headline is Claim Your Edition. Do not invent another heading,
apply the former product-specific headline angles or word-count targets, or
rewrite the assigned text for novelty. Repeated Claim Your Edition headlines
are intentional. The image's 100-variation title is unchanged and stays on-image.
Keep each assigned split throughout generation, review, display, reopen and CSV
export; no swapping or rerolling during final review. Preserve descriptions,
copy/CSV CTA Claim Your Edition, native Shop Now button, route order and schema.
"""

REVIEW = """Before delivery inspect every exported JPEG: exactly two footer lines,
the original assigned 100-variation title and its assigned second line. Check
the omitted FOMO/Claim Your Edition line equals that ad's displayed and CSV
Meta headline verbatim. Keep the 160 px black footer and gold shimmer. No badge,
third line or independent written heading. Use the existing final creative
review to correct defects, then verify all four original downloadable files.
"""


def active(prompt):
    return VERSION in str(prompt)


def assign(visuals, selections=()):
    for index, visual in enumerate(visuals):
        saved = selections[index] if index < len(selections) else {}
        kind = saved.get('footer_second_line_kind') if saved.get('footer_layout_version') == VERSION else None
        if kind is None:
            seed = hashlib.sha256((str(visual['resolved_seed']) + '|footer-split|' + visual['route_key']).encode()).hexdigest()
            kind = random.Random(seed).choice(('CTA', 'FOMO'))
        if kind not in ('CTA', 'FOMO'):
            raise ValueError('Saved footer split is invalid; preserve the saved pack for review.')
        visual.update(footer_layout_version=VERSION, footer_second_line_kind=kind,
                      footer_second_line='CLAIM YOUR EDITION' if kind == 'CTA' else visual['supporting_line'],
                      meta_headline_text=visual['supporting_line'] if kind == 'CTA' else 'Claim Your Edition')


def image_copy(visual):
    return (f"HEADLINE: {visual['headline_text']}\n"
            f"FOOTER SECOND LINE ({visual['footer_second_line_kind']}): {visual['footer_second_line']}")


def copy_rules(text):
    """Remove superseded IE headline directions, leaving description frameworks intact."""
    text = re.sub(r'Headline: ONE short product-specific[^\n]*',
                  "Headline: Use this ad's resolved META HEADLINE verbatim.", text)
    text = text.replace("The written headline's emotional angle must fit its assigned description style. Reassign the internal headline angle when necessary, never restructure the description to fit the headline.", '')
    text = text.replace('Keep each headline product-specific; aim for 2–6 words, preferring natural phrasing over a rigid count.', '')
    text = text.replace('on-image CTA remains CLAIM YOUR EDITION.', 'on-image wording follows the assigned two-line footer split.')
    return text
