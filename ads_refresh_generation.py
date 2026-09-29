"""Creative Refresh generation context; production schemas remain owned by ads_page."""
from copy import deepcopy
import json


def source_context(source=None):
    source = deepcopy(source or {})
    return {"source_winner": source} if source else {}


def build_prompt(ads, product, category, country, campaign_type, url, context,
                 *, campaign_moment=None, product_metadata=None):
    winner = ads.normalize_creative_refresh_context(context)
    source = winner.get("source_winner") or {}
    identity = {"product_name": product, "category": category, "country": country,
                "campaign_type": campaign_type, "product_url": url}
    carousel = campaign_type == "Carousel"
    template = (ads.build_carousel_copy_csv(identity, template=True) if carousel
                else ads.build_standard_ads_csv(product_name=product))
    count = ("Create ONE refreshed FIVE-CARD carousel (Card 1 through Card 5). Preserve the useful "
             "sequence/storytelling principle of the reference. Use the exact existing New Ads card fields, "
             "five headline options, five descriptions and five primary texts in the supplied template."
             if carousel else "Create THREE refreshed creative directions, REFRESH 1, REFRESH 2 and REFRESH 3. "
             "Each needs primary text, headline, description, CTA guidance and a standalone image prompt.")
    visual = ads.build_campaign_moment_visual_context(campaign_moment, selected_country=country)
    return f"""SPORTS CAVE — CREATIVE REFRESH
{ads.CREATIVE_REFRESH_WINNER_CONTEXT_VERSION}

CURRENT WINNER / SELECTED REFERENCE CREATIVE
Product: {product}
Category: {category}
Market: {country}
Campaign format: {campaign_type}
Product page URL: {url}
Winning primary text:
{winner['winning_primary_text']}
Winning headline:
{winner['winning_headline']}
Winning description: {source.get('description') or 'Not supplied'}
Winning CTA: {source.get('cta') or 'Not supplied'}
Source evidence (factual context, not customer copy):
{json.dumps(source, ensure_ascii=False, default=str)}
Verified product context: {json.dumps(product_metadata or {}, ensure_ascii=False, default=str)}

ATTACHMENT 1 — WINNING META AD IMAGE
Winning image: attached as reference image 1. Download original winning image from Sports Cave OS.
Use this to understand the successful visual direction, composition, mood, framing, room styling,
hook, hierarchy, collector presentation and creative approach. It is not the artwork authority.

ATTACHMENT 2 — CANONICAL BLACK-FRAME WEBSITE PRODUCT IMAGE
Canonical product image: attached as reference image 2.
Use this as the authoritative reference for the exact Sports Cave artwork/product. Do not redesign,
replace, distort or invent a different artwork. Never reconstruct the artwork from the winning ad.
Keep the same product, exact artwork, frame, proportions and Sports Cave collector positioning.

ATTACHMENT 3 — SPORTS CAVE ADS CSV TEMPLATE
Fill the supplied New Ads CSV with exactly its existing headers, identity cells and row structure.
Populate every required production field, including the blank strategy labels for single-image rows.

OBJECTIVE
Analyse the selected reference and identify the visual/copy principle that appears to be working.
Preserve the winning creative DNA. Evolve it rather than discard it. Create NEW executions that
prevent creative fatigue, recognisably related to the reference but not duplicates or unrelated styles.
Vary composition, crop, room, product scale, lighting, angle, hierarchy or emotional hook in controlled ways.
Do not describe inconclusive signals or mixed components as a statistically proven winner.
Only use actual supplied evidence; no invented performance claims, offers, scarcity or endorsements.

{count}

{ads.build_country_language_guidance(country)}
{ads.build_carousel_card_copy_rules() if carousel else ads.build_standard_ads_output_contract()}

COPY AND IMAGE OUTPUT
Return the copy in the supplied CSV and generate the matching creative images, one per creative/card.
Every image prompt must be standalone, name {product}, and preserve the exact attachment 2 product.
Generate square 1080 x 1080 images with premium photorealistic collector presentation, accurate frame geometry and legible mobile composition.
For single-image rows, each image_prompt must be at least 200 characters, with no cross-references.
For Carousel preserve the New Ads card order and fields; use {url} for every card destination.
Return a completed downloadable UTF-8 CSV; quote commas and paragraph breaks correctly.
No extra schema, columns or identity changes. Import it into Sports Cave OS, then attach generated images.

{ads.build_campaign_moment_copy_relevance_block(campaign_moment, selected_country=country, campaign_type=campaign_type)}

VISUAL CAMPAIGN MOMENT RULE
{visual or 'Do not inject the Campaign Moment, event, seasonal props or promotion into visual instructions.'}
Campaign Moment must never overwrite the reference creative logic. Use only explicitly entered promotions.

EXACT CSV TEMPLATE
{template.decode('utf-8-sig')}
""".strip()
