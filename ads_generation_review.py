"""Internal creative review for New Ads, before the existing final delivery."""

from ads_reserve_scenes import RULES as RESERVE_RULES, CHECKPOINT as RESERVE_CHECKPOINT

VERSION = "SPORTS CAVE COMPLETE AD REVIEW V2"
RULES = f"{VERSION}\n\nCreative quality and variety\nBuild on the existing winner frameworks with fresh, product-specific fan insight.\nWithin each assigned route, develop a distinct emotional angle and complementary\nheadline and description, rather than repeating the same three generic ads with\nnames swapped. Use the supplied variation and recent-history context to explore\ndifferent permitted settings, light, materials and visual details. Make the ads\nrecognisably different from one another while preserving each route's required\nscene, camera, layout, footer, typography, product fidelity and protected copy.\nVary flexible wording and scene details, not the locked frameworks or facts.\n\nFinal creative review — after images and copy, before export\nOnce every image, Primary Text, headline, description and CTA is complete, inspect\nthe actual generated images alongside their matching copy and review the entire\nad package internally before producing the final CSV and download links.\nAsk for every ad and then across the set:\n- Would a fan of this sport, player or team recognise and relate to this idea?\n- Does the language, spelling and tone suit the selected country and sport?\n- Are the terms familiar and natural to knowledgeable fans, without forced slang?\n- Does anything sound or look like AI: generic phrasing, artificial rooms, implausible\n  glass or shadows, distorted artwork, awkward typography or repeated compositions?\n- Is the emotion specific and believable, and is the ad compelling enough to click?\n- Does it look like a premium collector edition with a clear, readable product hero?\n- If I clicked through to this product, would the ad give me a credible reason to\n  buy, with copy and imagery that faithfully represent the actual edition?\n- Do the image, on-image wording, written headline, description and CTA work together?\n- Does each ad offer a distinct reason to care, rather than paraphrasing its neighbours?\n\nImprove weak copy and regenerate any image that needs improvement, then inspect\nthe revised ad and its relationship to the rest of the set. Retain strong elements;\nuse purposeful corrections rather than repeated rewrites chasing a perfect score.\nKeep fan emotion grounded in supplied verified facts and approved edition policies.\nPreserve required copy frameworks, hooks, CTAs, field limits, route order and image\ncount. If flexible on-image wording changes, update its image and matching copy\ntogether so the final package is consistent. Complete this review autonomously as\npart of generation, without a new approval step or a separate review report.\n\nAfter review, export the final approved copy to the existing CSV schema and provide\nthe existing final download links using the reviewed images. Keep filenames, route\nmapping, completion markers and the Companion handoff exactly as already specified.\nImage improvements happen during review; the final link-delivery step simply links\nthose completed files using the existing delivery instructions.\n\n{RESERVE_RULES}"


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
     "Inspect the completed images and copy; correct defects during the final creative review, regenerating an image needing improvement before export."),
    ("- Complete matching copy, the populated CSV and supplied setup.\n- Review the outputs and report unresolved defects.",
     "- Complete matching copy, then review and improve the images and copy together.\n- Export the reviewed copy to the populated CSV and provide the supplied setup."),
    ("5. Create and attach the completed downloadable ad_copy.csv from the final copy records.",
     RESERVE_CHECKPOINT + "\n4b. Complete the final creative review of all three actual images and their copy; improve weak copy and regenerate any image needing improvement, then inspect the revised set.\n5. Create and attach the completed downloadable ad_copy.csv from the final reviewed copy records."),
)
