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
    "Compare side by side with the verified originals at 100% and thumbnail size: eyes and gaze, "
    "eyelids, eyebrows, nose, mouth and teeth, jaw, ears, hairline, natural skin and proportions. "
    "Check anatomy, uniform, legible logos, equipment and AI warping. Treat unverified identity "
    "as unresolved.\n\n"
)
_SOURCE_FINISH = (
    "Restore visible discrepancies with original photograph pixels and a precise mask. Use the "
    "smallest coherent source region that resolves the defect. Include head, helmet or neck where "
    "needed. Clean the silhouette and internal gaps, removing source backgrounds, halos and double "
    "edges. Check against temporary light and dark backgrounds where useful, then remove them. "
    "Match perspective, exposure, colour, texture, shadows and sharpness. Recheck the whole artwork. "
    "If the repair blends poorly, refine the mask or change source or crop while preserving facial fidelity. "
    "Keep grunge and artificial sharpening off skin.\n\n"
)
_REVIEW_STATUS = (
    "Record unresolved identity or integration in REVIEW NOTES and needs_attention metadata. "
    "Continue authorised review saves and delivery. Report the actual source comparison and any "
    "unverified checks. Reserve print approval for its separate process.\n\n"
)

AUTHENTICITY_CHECK = f"{AUTHENTICITY_HEADING}\n\n{_SOURCE_COMPARISON}{_SOURCE_FINISH}{_REVIEW_STATUS}"

CREATE_DESIGN_AUTHENTICITY_CHECK = (
    f"{AUTHENTICITY_HEADING}\n\n{_SOURCE_COMPARISON}"
    "Keep the generation as the visual baseline. Repair a specific visible defect only when a "
    "verified original has enough detail at the intended placed size. Mask the smallest coherent "
    "region on a separate editable masked layer, clean its edges and match the surrounding sharpness, lighting, colour and texture. "
    "Mask closely around the repaired subject. Include surrounding photographic pixels only for "
    "necessary genuine contact details, such as a tyre meeting the track; preserve the artwork beyond them. "
    "Compare before and after at 100% and thumbnail size. Keep the repair only if it improves authenticity without "
    "introducing softness, halos or mismatched edges; otherwise revert it. If identity remains "
    "unverified or visibly wrong, keep the strongest candidate provisional.\n\n"
    + _REVIEW_STATUS
    + "For action, apply contact shadows only at actual points of contact and keep an airborne "
      "subject visibly separated from the ground. Match directional lighting and depth. Complete "
      "the digital integration review before selecting the artwork.\n\n"
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
