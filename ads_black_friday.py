"""Copy-only seasonal substitution; the saved Normal Prompt remains authoritative."""
import re

SUBHEADLINE = "EARLY BIRD BLACK FRIDAY"

# Only footer-subheadline instructions may differ. Keep these substitutions explicit
# so a prompt-template change cannot silently erase unrelated creative instructions.
FOOTER_REPLACEMENTS = (
    ("three different approved footer headlines and distinct supporting lines in every set",
     "three different approved footer headlines and the same EARLY BIRD BLACK FRIDAY supporting line in every set"),
    ("approved selected headline and supporting-line wording, with maximum eligible variety",
     "approved selected headline wording with maximum eligible variety and the exact EARLY BIRD BLACK FRIDAY supporting line"),
    ("Supporting text is clearly secondary in softer warm off-white.",
     "Supporting text is clearly secondary to both headline and CTA in muted antique gold (#B59A65), slightly more muted than the unchanged main CTA."),
    ("Restore the exact saved supporting sentence and historical selection rules; never invent replacement wording. Set it in Montserrat Regular, 24–26 px at 1024 px, softer warm off-white, centred on one line.",
     "Replace the emotional/FOMO supporting sentence and all its historical options with exactly EARLY BIRD BLACK FRIDAY. Across all three ads, set it in Montserrat Light (300), 20–22 px at 1024 px (approximately 15–20% smaller than the original 24–26 px; use this fixed target, never compound reductions), muted antique gold (#B59A65), with controlled 0.03–0.05 em letter spacing, horizontally centred on one line. Avoid bold, heavy or blocky lettering. Keep it clearly readable at mobile size and visually secondary to both headline and CTA."),
    ("supporting line 24–26 px, Montserrat Regular;",
     "supporting line 20–22 px, Montserrat Light (300), controlled 0.03–0.05 em letter spacing;"),
    ("- Express one clean supporting thought on exactly one line at the shared secondary supporting-copy target below.",
     "- Render exactly EARLY BIRD BLACK FRIDAY on one line at the shared smaller secondary supporting-copy target below, in muted antique gold (#B59A65). Keep its existing position between the headline and unchanged CTA, with balanced compact inter-line spacing inside the existing 18–20% opaque matte-black footer; no added padding, blank rows or empty black space. Keep the headline dominant and the existing footer height, spacing and proportions; no sale stickers, discount percentages or additional banners."),
)


def build_black_friday_prompt(normal_prompt):
    """Derive the current three-cover footer variant without rerolling any choices."""
    if "\nADS_IE_COMBINED_EXECUTION_V1\n" not in "\n" + normal_prompt:
        raise ValueError("Black Friday requires the current Instant Experience footer template.")
    seasonal, count = re.subn(r"(?m)^(SUPPORTING LINE: )[^\r\n]+",
                              lambda match: match[1] + SUBHEADLINE, normal_prompt)
    if count != 3:
        raise ValueError("Expected three resolved footer supporting lines.")
    for original, replacement in FOOTER_REPLACEMENTS:
        if seasonal.count(original) != 1:
            raise ValueError("The footer template has changed; review the seasonal substitutions.")
        seasonal = seasonal.replace(original, replacement)
    return seasonal
