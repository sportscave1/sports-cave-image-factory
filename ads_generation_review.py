"""Internal creative review for New Ads, before the existing final delivery."""

VERSION = "SPORTS CAVE COMPLETE AD REVIEW V1"
RULES = f"""{VERSION}

Creative quality and variety
Build on the existing winner frameworks with fresh, product-specific fan insight.
Within each assigned route, develop a distinct emotional angle and complementary
headline and description, rather than repeating the same three generic ads with
names swapped. Use the supplied variation and recent-history context to explore
different permitted settings, light, materials and visual details. Make the ads
recognisably different from one another while preserving each route's required
scene, camera, layout, footer, typography, product fidelity and protected copy.
Vary flexible wording and scene details, not the locked frameworks or facts.

Final creative review — after images and copy, before export
Once every image, Primary Text, headline, description and CTA is complete, inspect
the actual generated images alongside their matching copy and review the entire
ad package internally before producing the final CSV and download links.
Ask for every ad and then across the set:
- Would a fan of this sport, player or team recognise and relate to this idea?
- Does the language, spelling and tone suit the selected country and sport?
- Are the terms familiar and natural to knowledgeable fans, without forced slang?
- Does anything sound or look like AI: generic phrasing, artificial rooms, implausible
  glass or shadows, distorted artwork, awkward typography or repeated compositions?
- Is the emotion specific and believable, and is the ad compelling enough to click?
- Does it look like a premium collector edition with a clear, readable product hero?
- If I clicked through to this product, would the ad give me a credible reason to
  buy, with copy and imagery that faithfully represent the actual edition?
- Do the image, on-image wording, written headline, description and CTA work together?
- Does each ad offer a distinct reason to care, rather than paraphrasing its neighbours?

Improve weak copy and regenerate any image that needs improvement, then inspect
the revised ad and its relationship to the rest of the set. Retain strong elements;
use purposeful corrections rather than repeated rewrites chasing a perfect score.
Keep fan emotion grounded in supplied verified facts and approved edition policies.
Preserve required copy frameworks, hooks, CTAs, field limits, route order and image
count. If flexible on-image wording changes, update its image and matching copy
together so the final package is consistent. Complete this review autonomously as
part of generation, without a new approval step or a separate review report.

After review, export the final approved copy to the existing CSV schema and provide
the existing final download links using the reviewed images. Keep filenames, route
mapping, completion markers and the Companion handoff exactly as already specified.
Image improvements happen during review; the final link-delivery step simply links
those completed files using the existing delivery instructions.
"""


def apply_generation_review(prompt):
    if not prompt or RULES in prompt:
        return prompt
    # Scope the former inspection-only restrictions to New Ads. Shared project
    # templates and Creative Refresh retain their existing execution contracts.
    for old, new in REVIEW_UPDATES:
        prompt = prompt.replace(old, new)
    return prompt.rstrip() + "\n\n" + RULES


REVIEW_UPDATES = (
    ("make exactly three successful image-generation calls, one image per ad, in order, subject to the failure handling below. No variants, alternatives, correction or replacement generations. Inspect without generating again and report unresolved defects.",
     "generate the three initial images, one image per ad, in order, subject to the failure handling below. Review the completed images and copy, then correct weak copy or regenerate images needing improvement before exporting. Deliver exactly three final covers, one per ad."),
    ("never repeat a successful call.", "reuse successful outputs unless the final creative review identifies an image needing improvement."),
    ("MANDATORY FINAL INSPECTION — NO ADDITIONAL IMAGE GENERATIONS", "MANDATORY FINAL INSPECTION — REVIEW BEFORE EXPORT"),
    ("Inspect the composed image before returning it and briefly report unresolved defects. Inspection must not trigger another image-generation call.",
     "Inspect the composed image before returning it and correct defects during the final creative review, regenerating that image when needed."),
    ("Inspection must not trigger another image generation; report unresolved defects briefly.",
     "Improve weak copy and regenerate images needing improvement during the final creative review before export."),
    ("- Complete matching copy, the populated CSV and supplied setup.\n- Review the outputs and report unresolved defects.",
     "- Complete matching copy, then review and improve the images and copy together.\n- Export the reviewed copy to the populated CSV and provide the supplied setup."),
    ("5. Create and attach the completed downloadable ad_copy.csv from the final copy records.",
     "4a. Complete the final creative review of all three actual images and their copy; improve weak copy and regenerate any image needing improvement, then inspect the revised set.\n5. Create and attach the completed downloadable ad_copy.csv from the final reviewed copy records."),
)
