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
    AUTHENTICITY_CHECK
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
    f"{AUTHENTICITY_HEADING}\n\n"
    f"{_SOURCE_COMPARISON}{_SOURCE_FINISH}{REVIEW_SUBJECT_PRESERVATION}{_REVIEW_STATUS}"
)
