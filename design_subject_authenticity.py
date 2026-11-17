"""Source-photo verification and restoration for full artwork passes."""

AUTHENTICITY_HEADING = "**MANDATORY PHOTOGRAPHIC AUTHENTICITY AND INTEGRATION CHECK**"
_SOURCE_COMPARISON = (
    f"{AUTHENTICITY_HEADING}\n\n"
    "Apply this check after each full-artwork generation, after any subject restoration, and "
    "on the assembled PSD. Use the verified original photograph as the authority. The existing "
    "retry cap applies to image-generation calls. Masking, alignment, edge cleanup, tonal matching "
    "and placement are ordinary finishing work and can continue after that cap. Follow the "
    "existing continuation rules.\n\n"
    "Compare the source photograph and artwork side by side at 100% and at normal viewing "
    "size. Prioritise facial identity and expression, then natural skin, then anatomy, uniform "
    "and equipment. Check the eyes and gaze, eyelids, eyebrows, nose, mouth and teeth, jaw, ears, "
    "hairline and facial proportions. Preserve the source expression, genuine marks and natural "
    "skin texture. Look for invented wrinkles, scars, etched lines, exaggerated pores, waxy skin, "
    "excessive smoothing and artificial sharpening on the face, neck, arms and hands. Judge "
    "realism by fidelity to the source. Compare visible sponsors, logos, lettering and equipment "
    "directly with the source for AI warping, redrawing or lost details.\n\n"
)

_MASK_FINISH = (
    "Refine the mask along the outer silhouette and throughout visible openings, such as gaps "
    "between fingers or in equipment. Remove the original background from those gaps while "
    "preserving real edges and fine detail such as hair, straps and equipment bars. Clean up any "
    "displaced generated edges beneath the repair so the subject has one coherent outline. "
    "Refine complex edges beyond a rough selection, broad feather or colour threshold. Inspect "
    "at full size against the final scene and use temporary light and dark backgrounds to reveal "
    "residue when available. Remove temporary inspection backgrounds before saving.\n\n"
)

_SOURCE_RESTORATION = (
    "Restore visible discrepancies with original photograph pixels and a precise mask. Preserve "
    "the source proportions and perspective. Match exposure, colour, sharpness and edges to "
    "integrate the restored area naturally. Where needed use a connected region such as the face, "
    "head, helmet and neck so the restoration reads as a single photograph. Avoid rectangular "
    "source overlays. Recheck against the source and in the complete composition. Check that "
    "the face, neck and body share consistent photographic texture, lighting and detail. Correct "
    "halos, seams, ghosting, mismatched softness and cutout edges. If the generated body has "
    "artificial detail, reduce it around the restoration. Keep the source face free of repainting "
    "and artificial sharpening.\n\n"
)

_RESTORATION_RECOVERY = (
    "If faithful restoration is difficult, refine the source mask, find a clearer verified "
    "original, or compose around authenticated visible details. Preserve the strongest composition "
    "and authentic expression. Avoid repeated facial regeneration and approximate likenesses.\n\n"
)

_FALLBACK_FINISH = (
    "**FALLBACK COLLECTOR FINISH**\n\n"
    "After source-based correction, apply a subtle unifying tonal treatment if a texture "
    "mismatch remains. Keep grunge, distressing and abstract texture on the background and "
    "decorative elements. On the subject, use only restrained colour, contrast and sharpness "
    "matching that preserves natural skin and facial detail. Keep scratches, heavy grain and "
    "dark overlays off the subject and inspect the result again.\n\n"
)

_UNRESOLVED_REVIEW = (
    "Give visible masking and blending defects a focused finishing pass where the tools and source "
    "allow. If authenticity or integration still cannot be verified, retain the strongest "
    "faithful version and record the specific discrepancy in REVIEW NOTES. Continue the existing "
    "saves, verification and delivery steps for the available work. Mark the unresolved candidate "
    "needs_attention in review metadata where saved, and preserve any verified PSD it was meant "
    "to replace. Report what the photo comparison verified and what remains uncertain. Never "
    "claim an AI detector passed, the subject is unchanged or the artwork is print-ready without "
    "supporting verification.\n\n"
)

AUTHENTICITY_CHECK = (
    _SOURCE_COMPARISON + _SOURCE_RESTORATION + _MASK_FINISH + _RESTORATION_RECOVERY
    + _FALLBACK_FINISH + _UNRESOLVED_REVIEW
)

CREATE_DESIGN_AUTHENTICITY_CHECK = (
    f"{_SOURCE_COMPARISON}"
    "**TARGETED AUTHENTICITY RESTORATION — PRESERVE PREMIUM SCENE INTEGRATION**\n\n"
    "Keep the strongest complete generated artwork as the visual foundation. Restore visible "
    "discrepancies with original photograph pixels and a precise mask. Use the smallest "
    "coherent source region that resolves the defect. Expand to the head, helmet or neck only "
    "when needed for seamless integration. Keep successful pose, uniform detail, composition "
    "and body integration unless a visible error warrants a change. Avoid a full-athlete "
    "source cutout as the default fix and keep rectangular photo overlays out of the artwork.\n\n"
    f"{_MASK_FINISH}"
    "Match exposure, colour, contrast, shadow, texture and sharpness with restrained photographic "
    "grading. Preserve facial features, natural skin, genuine marks and the source perspective. "
    "Match texture through photographic detail and consistent tones. Keep decorative grunge, "
    "scratches and abstract patterns off skin. Reduce artificial detail around a restored face "
    "instead of repainting or sharpening it to match.\n\n"
    "Build depth through consistent light direction, softness and colour. Preserve natural form "
    "shadows on the body and clothing and use environmental or cast shadows where supported by "
    "the scene. Add contact shadows only at actual points of contact. In airborne action, keep "
    "the subject visibly separated from the ground and place any ground shadow consistently with "
    "the athlete’s height and scene lighting. Avoid generic drop shadows, dark outlines, "
    "artificial rim glows and exaggerated reflections. Keep the athlete dominant through "
    "controlled foreground, subject and background contrast, compatible focus and natural edge "
    "transitions. Preserve working depth and lighting, changing them only where the artwork benefits.\n\n"
    "After every restoration, inspect the full subject outline and corrected regions at 100% and "
    "normal viewing size. Correct remnants of the source background, coloured fringes, halos, "
    "jagged edges, doubled contours, abrupt texture changes and lighting mismatches. Match edge "
    "sharpness to the source photograph and scene. Address defects directly. Avoid using "
    "darkness, blur, smoke or heavy grain to conceal them. Keep a correction only when "
    "it improves the intended defect without weakening authenticity, integration or composition. "
    "If a more faithful face introduces a worse cutout or disconnected body, revert it and use "
    "a smaller repair or another targeted finishing correction.\n\n"
    f"{_RESTORATION_RECOVERY}{_FALLBACK_FINISH}"
    "Complete the digital integration review before selecting the final artwork. Physical print "
    "proofing is separate from digital artwork inspection.\n\n"
    f"{_UNRESOLVED_REVIEW}"
)


REVIEW_SUBJECT_PRESERVATION = (
    "**REVIEW REPLACEMENT — EXISTING SUBJECT PRESERVED**\n\n"
    "Missing original source photographs alone must not prevent an improved revision from "
    "replacing the current Review artwork when comparison with the exact pre-edit PSD "
    "demonstrates that the existing protected facial features, identity and expression are "
    "preserved, there is no visible deterioration in subject accuracy, and the PSD and "
    "collector-layer checks pass. Inspect the existing face pixels and the assembled revision "
    "side by side at 100% and normal viewing size, accounting for authorised placement and "
    "proportional scale. Preserve existing facial features; do not regenerate or approximate "
    "them to satisfy this condition. Record the comparison evidence in REVIEW NOTES.\n\n"
    "The pre-edit PSD is evidence of preservation, not proof of original photographic "
    "authenticity. Carry inherited or unresolved source-verification limitations into the "
    "matching JSON as needs_attention with specific review_notes. Replacing a Review draft "
    "does not certify photographic authenticity, print readiness or permission to publish. "
    "If the improved revision wins under these conditions, complete verified replacement, "
    "update and verify the matching JSON, and clean up this edit’s temporary files without "
    "waiting for publication approval or missing source photographs. Preserve the original "
    "recoverably until replacement verification succeeds.\n\n"
    "Visible deterioration, altered protected facial features, inability to verify preservation "
    "against the current PSD, failed required PSD/collector checks or a revision conflict "
    "still require correction or retention of the original. Continue independent work under "
    "the existing recovery limits and report the exact unresolved operation.\n\n"
)

EDIT_AUTHENTICITY_CHECK = (
    _SOURCE_COMPARISON.replace(
        "Use the verified original photograph as the authority.",
        "Use verified original photographs when available. If they remain unavailable after "
        "the existing recovery attempts, use the exact pre-edit PSD as the preservation "
        "baseline under REVIEW REPLACEMENT — EXISTING SUBJECT PRESERVED. In that case, "
        "perform the comparisons below against the retained pre-edit pixels and report "
        "source-photo authenticity separately as unverified.",
    )
    + REVIEW_SUBJECT_PRESERVATION
    + _SOURCE_RESTORATION.replace(
        "Restore visible discrepancies with original photograph pixels and a precise mask.",
        "Restore visible discrepancies with original photograph pixels and a precise mask "
        "when available. For the preserved-subject Review path, restore protected regions "
        "from the exact pre-edit PSD pixels instead; do not claim this establishes source-photo authenticity.",
    )
    + _MASK_FINISH + _RESTORATION_RECOVERY + _FALLBACK_FINISH
    + "Give visible masking and blending defects a focused finishing pass within the existing "
      "limits. Apply the preserved-subject Review eligibility rule above rather than treating "
      "missing source-photo evidence alone as a replacement veto. Record inherited or "
      "unresolved source verification in REVIEW NOTES and needs_attention metadata. If "
      "protected-subject preservation or the required PSD checks fail, retain the current "
      "PSD and staged work. Report what was compared and what remains uncertain. Never "
      "claim photographic authenticity or print readiness without supporting verification.\n\n"
)
