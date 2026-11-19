"""Facial identity and source-photo checks shared by artwork workflows."""

IDENTITY_HEADING = "**IDENTITY OVERRIDES GENERATION CONTINUITY**"
IDENTITY_OVERRIDES_CONTINUITY = (
    f"{IDENTITY_HEADING}\n\n"
    "Use the verified original photograph as the identity authority on every pass, including "
    "supporting faces. Carry forward successful composition and styling only. Never lock, "
    "regenerate or carry forward an altered face. Preserve facial features, proportions, gaze, "
    "expression, genuine marks and natural texture. Subtle changes to body placement, crop, "
    "scale or lighting may serve the design within the authorised scope and source rules. "
    "Keep the depicted anatomy, pose and sporting details truthful. If face repair fails, find "
    "a higher-resolution verified original or adapt the subject’s scale and crop. A recognisably "
    "different face fails identity and is ineligible as an accepted final design even if a "
    "Review PSD was saved.\n\n"
)

AUTHENTICITY_HEADING = "**MANDATORY PHOTOGRAPHIC AUTHENTICITY AND INTEGRATION CHECK**"
_SOURCE_COMPARISON = (
    "At 100% zoom, compare the final assembled PSD directly and side by side with the actual "
    "verified full-resolution photographs. Inspect the story-carrying areas first: every visible "
    "face and expression, eyes and gaze, eyelids, eyebrows, nose, mouth and teeth, jaw, ears, "
    "hairline, natural skin and proportions; both hands with their contact points, limb connections, "
    "jersey numbers, equipment markings, ball seams and lettering, and any background figure "
    "prominent enough to distract. Look for invented lettering, warped features, artificial skin "
    "marks, doubled edges and mismatched sharpness. Compare a real grip, equipment geometry, "
    "camera perspective and natural motion blur together; do not sharpen individual letters or "
    "redraw fingers to make uncertain detail look convincing. Treat unverified identity as unresolved.\n\n"
)
_SOURCE_FINISH = (
    "When generation changes a recognisable feature, restore the affected area with original "
    "source pixels on separate editable masked layers. Use a coherent source area, including "
    "enough surrounding photograph to keep anatomy, light, texture and edges continuous. If "
    "several connected details drift, restore the whole photographic interaction together, "
    "including both hands and ball or both interacting bodies and their spacing. Include head, "
    "helmet and neck where needed for identity continuity. Never guess obscured anatomy or "
    "equipment lettering. Preserve natural hair and fabric edges and internal gaps; clean peripheral source backgrounds, halos and double edges without "
    "erasing contact points, genuine overlap or natural motion blur. Match perspective, exposure, "
    "colour, texture, shadows and sharpness with non-destructive adjustments; keep grunge and "
    "artificial sharpening off skin. After each repair, inspect that area again against the "
    "original in the finished composition at 100% and 250 px wide, without blurring the silhouette, repainting skin or fading anatomy. Refine the mask or use a "
    "clearer verified source or crop within the existing allowance when necessary; preserve "
    "successful surrounding generated artwork.\n\n"
)
_REVIEW_STATUS = (
    "Record unresolved identity or integration in REVIEW NOTES and needs_attention metadata. "
    "Continue authorised review saves and delivery. Report the actual source comparison and any "
    "unverified checks. Reserve print approval for its separate process.\n\n"
)

AUTHENTICITY_CHECK = f"{AUTHENTICITY_HEADING}\n\n{_SOURCE_COMPARISON}{_SOURCE_FINISH}{_REVIEW_STATUS}"

CREATE_DESIGN_AUTHENTICITY_CHECK = (
    f"{AUTHENTICITY_HEADING}\n\n"
    "Verify every visible athlete and sporting object against the full-resolution originals. "
    "Preserve successful generated integration when facial features, expression, hair, body, "
    "hands, pose, uniform, lettering, equipment, vehicle and ball remain faithful. A rough "
    "pre-generation cutout is a layout guide, not a required final layer. Do not automatically "
    "cover a faithful integrated subject with a whole source cutout. Choose a clearer source "
    "or reduce its placed size when source detail is insufficient; never invent missing detail "
    "or accept a lookalike.\n\n"
    + _SOURCE_COMPARISON + _SOURCE_FINISH
    + "Reject pixelation, compression, waxy skin, edge halos, mismatched sharpness and pasted-on "
      "lighting. Apply contact shadows only at actual contact points and keep an airborne "
      "subject visibly separated from the ground. Correct source integration during the "
      "existing finishing pass.\n\n"
    + _REVIEW_STATUS
)



REVIEW_SUBJECT_PRESERVATION = (
    "**REVIEW REPLACEMENT — EXISTING SUBJECT PRESERVED**\n\n"
    "If verified originals remain unavailable, compare the revision with the exact pre-edit PSD "
    "at 100% and thumbnail size. Restore protected regions from those exact pixels when needed. "
    "Account for authorised placement or proportional scale and require no visible deterioration "
    "in identity, features or expression. Record the evidence and inherited source limitation in "
    "REVIEW NOTES and needs_attention metadata. The pre-edit PSD establishes preservation only. "
    "If the edit wins and required PSD and collector-layer checks pass, continue verified replacement "
    "and cleanup in Review. If preservation cannot be verified, a discrepancy is visible, or a "
    "required file check fails, keep the current PSD and deliver available staged work.\n\n"
)

EDIT_AUTHENTICITY_CHECK = (
    f"{IDENTITY_HEADING}\n\n"
    "Search online for the exact photograph used for each visible subject in the current artwork. Use PSD or project "
    "references and match the visible pose, crop, kit and event on the original source page. "
    "Prefer the highest-resolution verified copy of that same frame and record its source. "
    "A similar pose or a different frame cannot verify the original.\n\n"
    f"{AUTHENTICITY_HEADING}\n\n"
    "Compare the current artwork and every new pass, correction and assembled render with the "
    "verified photograph at 100% and thumbnail size. Match the eyes and gaze, eyelids, eyebrows, nose, "
    "mouth, teeth, jaw, hairline, proportions, expression and authentic skin texture. Preserve "
    "real pores and marks. Keep AI-generated skin, plastic smoothing, beauty retouching, "
    "invented detail and artificial sharpening off the face. Restore any drift with the "
    "original facial pixels and a precise mask. Match lighting and edges without repainting "
    "the face. If repair fails, use a clearer copy or adjust the crop and scale. Allow slight "
    "body and positioning changes within the requested scope while preserving believable anatomy, "
    "sporting details and the original face.\n\n"
    f"{REVIEW_SUBJECT_PRESERVATION}{_REVIEW_STATUS}"
)
