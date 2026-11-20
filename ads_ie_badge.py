"""Baseline 2.1 Beta: scoped footer profiles for New Ads Instant Experience."""

VERSION = "SPORTS CAVE BASELINE 2.1 BETA — AD 2 BADGE FOOTER"
BADGE_URL = "https://sports-cave-image-factory.onrender.com/app/static/ads/blackened-gunmetal-sports-cave-medal.png"
BADGE_SHA256 = "3e614eccc8bb48f174696e91bb1d0a37f31690c49b3ba3e9b7d07d04b1155dab"
TITLE = "Claim Your Edition"

BADGE_FOOTER = f"""AD 2 ONLY — SINGLE-LINE GUNMETAL BADGE FOOTER
At 1024 × 1024, use a full-width opaque matte-black footer exactly 112 px high,
top seam y=912; the photographed room occupies the upper 912 px (89.0625%).
Keep the same thin champagne-gold shimmer on that seam. Scale all dimensions
by output width / 1024. Preserve the assigned close camera, collector hallway,
complete framed edition, physical scale and glazing; only its footer changes.
The only typeset footer text is exactly: Claim Your Edition
Use one centred baseline, 50 px Baskerville-style editorial serif Medium (500),
warm ivory #F3EBDD, natural kerning plus 0.03 em tracking. Centre on the full
canvas at x=512, y=968, inside a 58 px line box; keep 64 px horizontal margins.
No supporting/FOMO sentence, scarcity headline, number caption or separate CTA
row belongs in this footer. Keep the other ads' text out of this image.
Composite the ORIGINAL transparent gunmetal medal PNG into the black panel
during the existing JPEG export, using the available file/code tool. Asset:
{BADGE_URL}
Original Dropbox: /Sportscave Team Folder/03_ASSETS/Blackened Gunmetal Sports Cave Medal.png
Dropbox file ID: id:u1tYiAa2O-AAAAAAAACu3w
SHA256: {BADGE_SHA256}
Use the original PNG pixels and alpha, uniformly resized to 88 × 88 px at
x=64, y=924. It is a subtle integrated collector seal on the black background,
behind the text layer in compositing order, separate from the centred title.
Preserve its gunmetal colour and lettering; never redraw, recolour, stretch,
duplicate or generate a replacement badge. Its existing raster lettering is
part of the asset, not an extra typeset footer line. Do not paste a screenshot
or a white/grey preview background. Keep the footer fully opaque black.
Generate the complete room/product together as usual, leaving this panel ready
for the PNG; composite before the existing final inspection and final JPEG
attachment. Never overlay again on recovered completed exports. If the original
asset is unavailable, preserve completed work and report that exact checkpoint;
do not invent a badge or claim the overlay was applied. No new approval or
handoff step. Keep the original product reference and existing workflow.
"""

SELECTION_RULES = """FOOTER CANDIDATES AND FINAL REVIEW — BASELINE 2.1 BETA
Keep generating the same three distinct approved headline/supporting-line pairs
using the existing selection logic. They are candidate pairs for Ads 1 and 3,
not three required on-image scarcity headlines. Before initial images, choose
the strongest two distinct pairs for Ads 1 and 3 from those three candidates.
During the existing final creative review, confirm the best two for fan relevance,
clarity and fit; retain their exact wording and keep each supporting sentence
with its headline. If a better candidate is selected, correct that normal ad in
the existing review, then inspect its export. Never invent a fourth candidate.
Ad 2 always uses only Claim Your Edition in its smaller badge footer. It does
not consume one of the scarcity candidates. Ads 1 and 3 keep their existing
160 px, three-line footer, typography, FOMO sentence, CTA and shimmer unchanged.
These on-image choices do not replace the three independently written Meta
headlines/descriptions or change the CSV schema, targeting or route identities.
Preserve an explicitly user-approved pair; do not reroll saved candidates on
copy, reopen, review or export. Review compares the supplied candidates only.
"""

REVIEW_CHECK = """Inspect each actual JPEG against its assigned footer profile:
Ads 1 and 3: exactly three typeset lines, selected candidate headline and matching
supporting sentence plus CLAIM YOUR EDITION, unchanged 160 px footer/shimmer.
Ad 2: exactly one typeset line, Claim Your Edition, 112 px footer/shimmer and
the original transparent gunmetal PNG seal; no added supporting or CTA row.
Correct missing footer elements or profile defects through the supplied final
creative review, keeping the rest unchanged. Check full size and mobile size,
then verify all four original attachments.
"""


def active(prompt):
    return VERSION in str(prompt)
