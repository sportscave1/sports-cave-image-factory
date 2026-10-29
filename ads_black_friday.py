"""Copy-only seasonal substitution; the saved Normal Prompt remains authoritative."""
import re

SUBHEADLINE = "EARLY BIRD BLACK FRIDAY"

# Only footer-subheadline instructions may differ. Keep these substitutions explicit
# so a prompt-template change cannot silently erase unrelated creative instructions.
FOOTER_REPLACEMENTS = (
    ("three unique footer headlines and three unique sublines",
     "three unique footer headlines and the same EARLY BIRD BLACK FRIDAY subline"),
    ("three unique selected headlines/subline wording",
     "three unique selected headlines and the same EARLY BIRD BLACK FRIDAY subline wording"),
    ("Supporting text is clearly secondary in softer warm off-white.",
     "Supporting text is clearly secondary in subtle premium gold (#D4A54C)."),
    ("Supporting text is warm off-white.",
     "Supporting text is subtle premium gold (#D4A54C)."),
    ("With verified scarcity, exactly one line supplies the limited-edition/edition-size claim; the other adds collector or emotional meaning.",
     "Preserve the selected headline exactly; the supporting line is always EARLY BIRD BLACK FRIDAY, replacing the emotional/FOMO line, never adding a fourth line."),
    ("- Express one clean supporting thought on exactly one line at the shared secondary supporting-copy target below.",
     "- Render exactly EARLY BIRD BLACK FRIDAY on one line at the shared smaller secondary supporting-copy target below, in subtle premium gold (#D4A54C). Keep the headline dominant and the existing footer height, spacing and proportions; no sale stickers, discount percentages or additional banners."),
)


def build_black_friday_prompt(normal_prompt):
    """Derive the current three-cover footer variant without rerolling any choices."""
    if not normal_prompt.startswith("ADS_IE_COMBINED_EXECUTION_V1"):
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
