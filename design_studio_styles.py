from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
import re


STYLE_REQUIRED_LABEL = "Style required"
STYLE_REGISTRY_VERSION = "sports_cave_design_styles_v2"

SUPPORTED_IMAGE_ROLES = (
    "hero_exact_photo",
    "secondary_exact_photo",
    "exact_moment_photo",
    "archival_restoration_source",
    "existing_artwork_target",
    "rival_one_photo",
    "rival_two_photo",
    "rear_jersey_one",
    "rear_jersey_two",
    "driver_photo",
    "vehicle_exact_photo",
    "trophy_exact_photo",
    "venue_reference",
    "equipment_reference",
    "historical_reference",
    "signature_asset",
    "plaque_asset",
)

SUPPORTED_USE_MODES = (
    "visible_whole_photo",
    "visible_cutout",
    "reference_only",
    "signature_asset",
    "edit_target",
)

DEFAULT_USE_MODE_BY_ROLE = {
    "hero_exact_photo": "visible_cutout",
    "secondary_exact_photo": "visible_cutout",
    "exact_moment_photo": "visible_whole_photo",
    "archival_restoration_source": "visible_whole_photo",
    "existing_artwork_target": "edit_target",
    "rival_one_photo": "visible_cutout",
    "rival_two_photo": "visible_cutout",
    "rear_jersey_one": "visible_cutout",
    "rear_jersey_two": "visible_cutout",
    "driver_photo": "visible_cutout",
    "vehicle_exact_photo": "visible_cutout",
    "trophy_exact_photo": "visible_cutout",
    "venue_reference": "reference_only",
    "equipment_reference": "reference_only",
    "historical_reference": "reference_only",
    "signature_asset": "signature_asset",
    "plaque_asset": "visible_cutout",
}

LEGACY_IMAGE_ROLE_ALIASES = MappingProxyType(
    {
        "hero_image": "hero_exact_photo",
        "player_image": "hero_exact_photo",
        "action_image": "hero_exact_photo",
        "secondary_image": "secondary_exact_photo",
        "moment_image": "exact_moment_photo",
        "identity_reference": "historical_reference",
        "uniform_reference": "equipment_reference",
        "background": "venue_reference",
        "background_image": "venue_reference",
        "venue": "venue_reference",
        "equipment": "equipment_reference",
        "vehicle": "vehicle_exact_photo",
        "car_image": "vehicle_exact_photo",
        "trophy": "trophy_exact_photo",
        "plaque": "plaque_asset",
    }
)

VISIBLE_USE_MODES = {"visible_whole_photo", "visible_cutout", "edit_target"}


@dataclass(frozen=True)
class DesignStyle:
    slug: str
    label: str
    description: str
    example: str
    maximum_distinct_human_subjects: int
    maximum_intentionally_composed_human_figures: int
    required_image_roles: tuple[str, ...]
    optional_image_roles: tuple[str, ...]
    research_rules: str
    find_images_rules: str
    generation_rules: str
    harsh_review_rules: str
    minimum_named_principals: int = 0
    exact_named_principals: int | None = None
    skip_find_images_by_default: bool = False
    legacy_prompt_key: str = ""


def _style(
    slug,
    label,
    description,
    example,
    max_people,
    max_figures,
    required,
    optional,
    research,
    find_images,
    generation,
    review,
    *,
    minimum=0,
    exact=None,
    skip_find_images=False,
    legacy_prompt_key="",
):
    return DesignStyle(
        slug=slug,
        label=label,
        description=description,
        example=example,
        maximum_distinct_human_subjects=max_people,
        maximum_intentionally_composed_human_figures=max_figures,
        required_image_roles=tuple(required),
        optional_image_roles=tuple(optional),
        research_rules=research.strip(),
        find_images_rules=find_images.strip(),
        generation_rules=generation.strip(),
        harsh_review_rules=review.strip(),
        minimum_named_principals=minimum,
        exact_named_principals=exact,
        skip_find_images_by_default=skip_find_images,
        legacy_prompt_key=legacy_prompt_key,
    )


_STYLES = (
    _style(
        "ultimate_moment",
        "Ultimate Moment",
        "One exact sporting instant that fans recognise immediately.",
        "The Catch",
        2,
        2,
        ("exact_moment_photo",),
        ("venue_reference", "historical_reference", "signature_asset"),
        """
If the task is broad, verify up to five candidate exact moments and select the strongest commercial and emotional choice. Explain why fans recognise it; verify the event, date, venue, result and participants; identify the definitive photographic direction and exact search terms; provide five short collector titles and one final brief. If the task names a precise moment, verify that moment and do not replace it.
""",
        """
Return: EXACT MOMENT candidates first; then exact venue, scoreboard or event details; then SIGNATURES last when useful. Prioritise the highest-resolution authentic photograph of the exact moment and genuinely different authentic angles. Do not create player-by-player face carousels or add a generic portrait.
""",
        """
Use one definitive authentic photograph of the exact moment as the artwork foundation. Prefer the complete photograph. Preserve every participant already inside it; do not extract and rebuild them or add a generic athlete cutout. Use restrained grading, authentic period grain, vignette, negative space, title, event details and border only.
""",
        "Confirm the exact historical photograph, participants, event, date, venue and result. Reject any recreated or substituted moment.",
    ),
    _style(
        "rivalry_faceoff",
        "Rivalry Face-Off",
        "Two true rivals with equal visual authority and immediate tension.",
        "Peter Brock vs Allan Moffat",
        2,
        2,
        ("rival_one_photo", "rival_two_photo"),
        ("vehicle_exact_photo", "venue_reference", "historical_reference", "signature_asset"),
        """
Verify the rivals' shared history, overlapping era, defining meetings, correct teams or equipment and strongest source-photo directions. Build a factual two-sided brief with equal status and believable competitive tension.
""",
        """
Return separate groups in this order: RIVAL ONE final-use candidates; RIVAL TWO final-use candidates; shared rivalry, venue or era references; SIGNATURES with one per rival last. Never mix both rivals into one candidate carousel or return a third person.
""",
        """
Use exactly one selected real photograph for each rival. Give both equal scale, status and visual weight with natural opposing orientation where the sources support it. Never mirror text, uniforms, equipment or liveries. No third person. A matching car may support each motorsport rival only when the design remains minimal.
""",
        "Require exactly two rivals, no third person, equal scale, equal authority and correct left/right asset and signature mapping.",
        minimum=2,
        exact=2,
    ),
    _style(
        "legends_jersey_display",
        "Legends Jersey Display",
        "Two iconic rear jerseys presented as an equal-status legacy piece.",
        "Messi vs Ronaldo - Legends Never Die",
        2,
        2,
        ("rear_jersey_one", "rear_jersey_two"),
        ("equipment_reference", "historical_reference", "signature_asset"),
        """
Verify each legend's genuine rear-view image, exact kit, club or country, era, surname, number, badges and stitching. Establish the shared legacy story without inventing a rear view.
""",
        """
Return separate groups for legend one rear-view full-body candidates and legend two rear-view full-body candidates; then correct kit/name/number references and minimal shared atmosphere; then one signature per legend last. Say clearly when a suitable authentic rear image does not exist.
""",
        """
Use exactly two genuine rear or rear three-quarter source photographs at equal scale. Preserve the real jersey surname, number, colours, badges and stitching. Never create a rear view from a front-facing photograph or generate lettering. Place each verified signature beneath or near the correct legend.
""",
        "Confirm both views are genuine rear views and every jersey surname, number, kit and era is exact. Reject generated jersey lettering.",
        minimum=2,
        exact=2,
    ),
    _style(
        "nostalgic_tribute",
        "Nostalgic Tribute",
        "A person-first emotional tribute built around one specific memory.",
        "Shane Warne bowing at the MCG",
        1,
        1,
        ("hero_exact_photo",),
        ("venue_reference", "historical_reference", "signature_asset"),
        """
Identify the strongest emotionally recognisable gesture, farewell, candid expression, celebration or personal moment. Verify the era and venue and explain why that image unlocks affection rather than feeling generic.
""",
        """
Return the strongest emotionally specific final-use hero candidates first, then a small set of genuine alternatives, then the correct nostalgic venue or era reference, then one verified signature last.
""",
        """
Use one dominant authentic hero photograph and one distinct athlete only. Do not duplicate the athlete. Support the memory with restrained warm light, stadium shadow, gentle haze, authentic grain and dark edges. Avoid fantasy lighting, synthetic crowds and generic action montage treatment.
""",
        "Judge emotional specificity, authentic memory and restraint. Reject generic action, duplicated athletes or fantasy styling.",
        minimum=1,
        exact=1,
    ),
    _style(
        "motorsport_driver_car",
        "Motorsport: Driver & Car",
        "One driver paired with the exact car that defines the achievement.",
        "Peter Brock with the correct Bathurst-winning car",
        1,
        1,
        ("driver_photo", "vehicle_exact_photo"),
        ("venue_reference", "equipment_reference", "historical_reference", "signature_asset"),
        """
Verify the driver, season, race, team, car model, race number, sponsors, suit, helmet, wheels, body shape, livery, circuit and achievement as one historically matched set.
""",
        """
Return separate groups for the driver in the correct suit and era; the exact car and livery from useful authentic angles; the exact circuit and event atmosphere; then one verified driver signature last.
""",
        """
Use one driver and one exact real car from the same verified season, race, team and livery. Never modernise, reliver or regenerate the car, and never pair a driver from one season with another season's car. The car may be largest. Keep track atmosphere restrained.
""",
        "Verify the exact car, livery, race number, sponsors, suit, helmet, race, season and circuit. Reject every cross-era mismatch.",
        minimum=1,
        exact=1,
    ),
    _style(
        "minimalist_hero",
        "Minimalist Hero",
        "A clean single-athlete design with strong negative space.",
        "CR7",
        1,
        2,
        ("hero_exact_photo",),
        ("secondary_exact_photo", "equipment_reference", "signature_asset"),
        """
Verify the athlete, correct kit, season and equipment; identify the strongest clean action pose and minimal title direction that remains readable at Shopify-thumbnail size.
""",
        """
Return clean, high-resolution, cutout-friendly action candidates first; optionally one genuinely complementary second image of the same athlete; then accurate kit/equipment detail; then one authentic signature last. Do not return stadium or trophy montages.
""",
        """
Use one distinct athlete. Default to one dominant source photograph. A second real photograph may be visible only when it is the same athlete and clearly strengthens the design; maximum two visible figures. Use black or charcoal, restrained gold texture, minimal typography and genuine negative space. No detailed stadium, crowd, trophy collage or extra player.
""",
        "Check that one athlete dominates, no more than two real poses of that same person appear, negative space is genuine and unnecessary detail is absent.",
        minimum=1,
        exact=1,
    ),
    _style(
        "championship_achievement",
        "Championship / Achievement",
        "A verified trophy, record, award or completed achievement.",
        "The Garden's Crown",
        1,
        2,
        ("hero_exact_photo", "trophy_exact_photo"),
        ("secondary_exact_photo", "venue_reference", "historical_reference", "signature_asset"),
        """
Verify the achievement, trophy or award, exact result, date, event, venue, uniform and celebration. Mark hypothetical concepts internally and never present them as verified history.
""",
        """
Return the exact trophy or achievement photograph first, then exact celebration/action, correct trophy close-up, subtle venue/city/scoreboard references and one signature last.
""",
        """
Use one distinct athlete and a dominant authentic trophy, celebration or achievement photograph. A second visible photograph may only show the same athlete and only when needed. Preserve the exact trophy, result, date, event, venue and uniform. Never invent a future or hypothetical achievement as fact.
""",
        "Verify the trophy, result, date, event and uniform. Reject invented achievements and confirm no second distinct hero was added.",
        minimum=1,
        exact=1,
    ),
    _style(
        "vintage_restoration",
        "Vintage Restoration",
        "One genuine archival photograph restored as a restrained collector series.",
        "One-Two Finish",
        2,
        2,
        ("archival_restoration_source",),
        ("historical_reference", "signature_asset"),
        """
Identify the definitive original photograph, event, date, venue, participants, result and most credible high-resolution archival source. Verify historical names, car numbers and context. Do not propose a modern re-enactment.
""",
        """
Return the definitive authentic archival photograph and largest credible scan first. Add another authentic photograph only if it is a genuinely stronger final option, then exact historical fact references, then a verified signature only when appropriate. Do not fill a carousel with duplicate scans or alternate crops.
""",
        """
Use the whole archival photograph wherever possible. Preserve authentic film grain, age, contrast and period character. Correct dust, fading, levels and print damage conservatively only. Never rebuild faces, hands, cars, crowds, track details or missing scenery; never smooth grain into AI detail; never colourise unless explicitly requested. Incidental people already inside the source may remain but must not become new heroes.
""",
        "Confirm authentic grain and period character remain. Reject invented restoration detail, modern re-enactment, synthetic sharpening or generated people and vehicles.",
    ),
    _style(
        "update_existing",
        "Update Existing Design",
        "A surgical update to an existing approved Sports Cave artwork.",
        "Update a plaque, title, number or expired edition",
        0,
        0,
        ("existing_artwork_target",),
        ("signature_asset",),
        """
Inspect the existing approved artwork and the exact requested change. Verify only the replacement facts or assets needed. Do not research unrelated redesign directions.
""",
        """
Skip Find Images by default. If the requested edit needs a replacement asset, return only that exact verified replacement and no general inspiration carousel.
""",
        """
Treat the uploaded completed design as the immutable edit target. Change only the requested element. Preserve every unrequested subject, face, pose, layout, title, typography, signature, border, plaque and colour treatment. Do not regenerate the whole artwork for a local edit. Add no people. If a legacy design already contains more than two people, preserve them and warn rather than silently removing anyone.
""",
        "Confirm only the requested elements changed and every unrequested pixel-level design decision, subject and signature was preserved.",
        skip_find_images=True,
        legacy_prompt_key="design-studio::upgrade-existing-design",
    ),
)

_STYLE_REGISTRY = MappingProxyType({style.slug: style for style in _STYLES})


@lru_cache(maxsize=1)
def get_style_registry():
    return _STYLE_REGISTRY


def style_slugs():
    return tuple(get_style_registry())


def style_labels():
    return tuple(style.label for style in get_style_registry().values())


def normalize_design_style(value):
    clean = "_".join(str(value or "").strip().casefold().replace("/", " ").replace("-", " ").split())
    if clean in get_style_registry():
        return clean
    raw_label = " ".join(str(value or "").strip().casefold().split())
    for style in get_style_registry().values():
        if raw_label == " ".join(style.label.casefold().split()):
            return style.slug
    return ""


def get_design_style(value):
    return get_style_registry().get(normalize_design_style(value))


def design_style_label(value, fallback=STYLE_REQUIRED_LABEL):
    style = get_design_style(value)
    return style.label if style else fallback


_STYLE_WORDS = {
    "sports", "cave", "cinematic", "minimal", "minimalist", "collector",
    "limited", "edition", "thin", "border", "premium", "realistic",
    "artwork", "design", "tribute", "moment", "ultimate", "championship",
    "achievement", "vintage", "restoration", "nostalgic", "the", "new",
    "create", "make", "update", "existing", "versus", "vs", "faceoff",
}


def _clean_subject_name(value):
    text = " ".join(str(value or "").replace("_", " ").split()).strip(" -,:;()[]{}")
    text = re.sub(r"^(?:create|make|design|build|new|premium)\s+", "", text, flags=re.I)
    words = [word for word in text.split() if word]
    if not words or len(words) > 5:
        return ""
    lowered = {re.sub(r"[^a-z]", "", word.casefold()) for word in words}
    if not lowered or lowered.issubset(_STYLE_WORDS) or any(word in _STYLE_WORDS for word in lowered):
        return ""
    if any(character.isdigit() for character in text):
        return ""
    return text


def _subject_from_item(value):
    if isinstance(value, dict):
        for key in ("subject_name", "name", "full_name", "athlete", "player", "driver"):
            if value.get(key):
                return _clean_subject_name(value.get(key))
        return ""
    return _clean_subject_name(value)


def principal_subjects(details=None, task_text=""):
    details = dict(details or {})
    values = []
    for key in ("principal_subject_one", "principal_subject_two"):
        if details.get(key):
            values.append(details[key])
    for key in ("principal_subjects", "named_principals", "people"):
        nested = details.get(key)
        if isinstance(nested, (list, tuple, set)):
            values.extend(nested)
        elif nested:
            values.append(nested)
    if not values:
        text = str(task_text or "")
        versus = re.search(
            r"([A-Z][A-Za-z'.-]*(?:\s+[A-Z][A-Za-z'.-]*){0,3})\s+(?:vs\.?|versus)\s+([A-Z][A-Za-z'.-]*(?:\s+[A-Z][A-Za-z'.-]*){0,3})",
            text,
        )
        if versus:
            values.extend(versus.groups())
        else:
            values.extend(
                match.group(0)
                for match in re.finditer(
                    r"\b[A-Z][a-z'.-]+(?:\s+[A-Z][a-z'.-]+){1,3}\b",
                    text,
                )
            )
    subjects = []
    seen = set()
    for value in values:
        subject = _subject_from_item(value)
        if not subject or subject.casefold() in seen:
            continue
        seen.add(subject.casefold())
        subjects.append(subject)
    return subjects


def validate_design_request(style_slug, details=None, task_text=""):
    style = get_design_style(style_slug)
    if style is None:
        return [STYLE_REQUIRED_LABEL]
    subjects = principal_subjects(details, task_text)
    errors = []
    if len(subjects) > 2:
        errors.append(
            "This task exceeds the new Sports Cave limit of two principal people. "
            "Reduce it to one or two subjects before generating prompts."
        )
        return errors
    if style.exact_named_principals is not None and len(subjects) != style.exact_named_principals:
        count_word = "one" if style.exact_named_principals == 1 else "two"
        errors.append(f"{style.label} requires exactly {count_word} named principal subject(s).")
    elif len(subjects) < style.minimum_named_principals:
        errors.append(f"{style.label} requires named principal subject details before prompts can be generated.")
    if len(subjects) > style.maximum_distinct_human_subjects and style.slug != "update_existing":
        errors.append(
            f"{style.label} allows no more than {style.maximum_distinct_human_subjects} distinct principal people."
        )
    return errors


SPORT_ADAPTERS = MappingProxyType(
    {
        "motorsport": "Verify the exact season, race, circuit, car, livery, race number, sponsors, suit and helmet as one matched historical set.",
        "basketball": "Verify the exact team, season, jersey number, arena and game or achievement; preserve authentic jersey lettering and footwear.",
        "football": "Verify the exact club or country, competition, season, kit, shirt number, stadium and match context.",
        "cricket": "Verify the exact team, series, venue, whites or coloured kit, equipment and score or match context.",
        "combat": "Verify the exact opponent context, event, venue, trunks or fight kit, belt and result without adding an unrequested fighter.",
        "american_sports": "Verify the exact league, team, season, uniform, number, equipment, venue and game context.",
        "golf_tennis": "Verify the exact tournament, year, venue, clothing, equipment, trophy and result with restrained championship atmosphere.",
        "generic": "Verify the exact sport, era, uniform, equipment, venue and result required by the selected source photograph.",
    }
)


def select_sport_adapter(sport="", task_text="", style_slug=""):
    text = f"{sport} {task_text}".casefold()
    if style_slug == "motorsport_driver_car" or re.search(r"\b(f1|formula 1|nascar|supercars?|motorsport|driver|car|bathurst|racing|motogp)\b", text):
        return "motorsport"
    if re.search(r"\b(nba|basketball)\b", text):
        return "basketball"
    if re.search(r"\b(soccer|football|premier league|world cup|champions league)\b", text):
        return "football"
    if re.search(r"\b(cricket|ashes|test match|bbl|ipl)\b", text):
        return "cricket"
    if re.search(r"\b(boxing|ufc|mma|fighter|fight)\b", text):
        return "combat"
    if re.search(r"\b(nfl|baseball|mlb|nhl|ice hockey|gridiron)\b", text):
        return "american_sports"
    if re.search(r"\b(golf|tennis|pga|atp|wta)\b", text):
        return "golf_tennis"
    return "generic"


def _normalise_token(value):
    return "_".join(str(value or "").strip().casefold().replace("-", " ").split())


def normalise_selected_assets(selected_assets=None):
    records = []
    seen = set()
    for item in selected_assets or ():
        if not isinstance(item, dict):
            continue
        reference = next(
            (
                str(item.get(key) or "").strip()
                for key in ("file_path", "path", "image_reference", "reference", "url", "asset_id")
                if str(item.get(key) or "").strip()
            ),
            "",
        )
        role = _normalise_token(item.get("role") or item.get("image_role"))
        role = LEGACY_IMAGE_ROLE_ALIASES.get(role, role)
        if not reference or role not in SUPPORTED_IMAGE_ROLES:
            continue
        use_mode = _normalise_token(item.get("use_mode")) or DEFAULT_USE_MODE_BY_ROLE[role]
        if use_mode not in SUPPORTED_USE_MODES:
            use_mode = DEFAULT_USE_MODE_BY_ROLE[role]
        subject_name = _clean_subject_name(item.get("subject_name") or item.get("name"))
        key = (reference.casefold(), role, use_mode, subject_name.casefold())
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "reference": reference,
                "role": role,
                "use_mode": use_mode,
                "subject_name": subject_name,
            }
        )
    return records


def verified_signature_assets(selected_assets=None, subjects=None):
    allowed = {subject.casefold() for subject in subjects or ()}
    records = []
    seen_subjects = set()
    for asset in normalise_selected_assets(selected_assets):
        subject = asset.get("subject_name") or ""
        if asset["role"] != "signature_asset" or not subject:
            continue
        key = subject.casefold()
        if key not in allowed or key in seen_subjects:
            continue
        seen_subjects.add(key)
        records.append(asset)
    return records


def _task_variables(task_text, details, subjects):
    details = dict(details or {})
    fields = (
        ("DESIGN TITLE", "design_title"),
        ("SPORT", "sport"),
        ("TEAM / COUNTRY", "team_country"),
        ("SEASON / ERA", "season_era"),
        ("EVENT / MOMENT", "event_moment"),
        ("VENUE / LOCATION", "venue_location"),
        ("UNIFORM / EQUIPMENT / LIVERY", "uniform_equipment_livery"),
        ("ESSENTIAL TEXT", "essential_text"),
        ("SPECIAL INSTRUCTIONS", "special_instructions"),
    )
    lines = ["TASK VARIABLES", f"TASK: {str(task_text or '').strip() or '[PASTED TASK]'}"]
    if subjects:
        lines.append(f"PRINCIPAL SUBJECTS: {'; '.join(subjects)}")
    for label, key in fields:
        value = " ".join(str(details.get(key) or "").split())
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def _adapter_block(adapter_key):
    return f"SPORT ADAPTER - {adapter_key.upper()}\n{SPORT_ADAPTERS[adapter_key]}"


COMMON_RESEARCH_RULES = """
SPORTS CAVE DESIGN STUDIO V2 - RESEARCH

A winning design starts with the right verified moment and the right final-use photograph. Use reliable current and archival research. Verify facts, names, dates, results, uniforms, equipment and venue details required by this style. Do not find or display images yet. Do not generate artwork. Stop after a concise final creative brief.
""".strip()

COMMON_FIND_IMAGES_RULES = """
SPORTS CAVE DESIGN STUDIO V2 - FIND IMAGES

Find final-use authentic photographs, not facial pieces for AI reconstruction. Open and inspect each source page. Prefer official teams, leagues, photographers, editorial archives and major publications. Select the largest credible original; prefer 1200px or more and 2000px or more when available. Authentic historical grain is acceptable.

Reject AI images, artwork, posters, framed products, cards, fan edits, signed photographs used as hero references, marketplace memorabilia, screenshots, large watermarks, wrong-era subjects and duplicate crops. Do not substitute a sharper wrong-era image. Return only genuinely useful assets and do not fill a carousel to meet a quota.

Keep signatures last. Return at most one verified isolated signature for each valid named principal. If it cannot be verified, omit it. The visible response must be image-only apart from short carousel labels.
""".strip()

COMMON_GENERATION_RULES = """
SPORTS CAVE DESIGN STUDIO V2 - GENERATION

Create a premium landscape 4:3 Sports Cave limited-edition collector artwork from the selected final-use photographs.

IMMUTABLE SOURCE ASSETS
Every selected final-use photograph is an immutable asset. Composite the original photograph itself. Never redraw, regenerate, face-swap, re-pose or reconstruct a person, car, uniform, trophy or historical moment. Never combine a face from one image with a body from another. Respect the original crop; if styling conflicts with preservation, simplify the styling.

Use every selected image according to its explicit role and use mode. Only visible_whole_photo, visible_cutout and edit_target assets may appear visibly. Reference-only images provide facts and must never be used to rebuild a face, body, vehicle or scene. Do not place every reference visibly.

HUMAN AND BACKGROUND LIMITS
Use no more intentionally composed figures than the selected style permits. Never add generated athletes, teammates, opponents, coaches, spectators or recognisable crowd figures. Incidental people already inside one immutable historical photograph may remain only inside that photograph. Keep the background subtle, dark and relevant; the hero photograph carries the emotion.

COLLECTOR FINISH
Preserve natural skin, fabric, film grain and photographic texture. Use restrained black, charcoal, team colour and subtle warm-gold details, minimal accurate typography and clean negative space. Include a thin premium Sports Cave border fully inside the canvas. Keep every subject, word, signature, plaque and effect inside the border with a safe gap. Use an exact plaque only when supplied; never invent one. Use at most one verified signature per principal, mapped to the correct person; never generate or imitate a missing signature. The result must feel framed-first, print-ready, realistic and sellable, never like newly generated AI artwork.
""".strip()

COMMON_REVIEW_RULES = """
SPORTS CAVE DESIGN STUDIO V2 - HARSH REVIEW

Give a deliberately harsh commercial review of the supplied finished design. Score it out of 10. Identify visible failures, then give one precise correction brief.

Check: original source preservation; face, body, pose, uniform, vehicle, trophy and equipment accuracy; no AI reconstruction; correct era and venue; the style's human-figure limit; no extra generated people; clear hero hierarchy; minimal background; authentic signature mapping; exact typography; full border containment; landscape 4:3; Shopify-thumbnail readability; framed collector appeal; print readiness; and whether fans would genuinely buy it.
""".strip()


def build_research_prompt(style_slug, task_text, details=None):
    style = get_design_style(style_slug)
    if style is None:
        return STYLE_REQUIRED_LABEL
    subjects = principal_subjects(details, task_text)
    adapter = select_sport_adapter((details or {}).get("sport"), task_text, style.slug)
    return "\n\n".join(
        (COMMON_RESEARCH_RULES, f"STYLE - {style.label}\n{style.research_rules}", _adapter_block(adapter), _task_variables(task_text, details, subjects))
    )


def build_find_images_prompt(style_slug, task_text, details=None):
    style = get_design_style(style_slug)
    if style is None:
        return STYLE_REQUIRED_LABEL
    subjects = principal_subjects(details, task_text)
    adapter = select_sport_adapter((details or {}).get("sport"), task_text, style.slug)
    roles = ", ".join(style.required_image_roles)
    optional = ", ".join(style.optional_image_roles) or "none"
    return "\n\n".join(
        (
            COMMON_FIND_IMAGES_RULES,
            f"STYLE - {style.label}\n{style.find_images_rules}",
            f"IMAGE ROLE CONTRACT\nRequired: {roles}. Optional: {optional}. Assign one supported role and use mode to every selected asset.",
            _adapter_block(adapter),
            _task_variables(task_text, details, subjects),
        )
    )


def build_generation_prompt(style_slug, task_text, details=None, selected_assets=None):
    style = get_design_style(style_slug)
    if style is None:
        return STYLE_REQUIRED_LABEL
    subjects = principal_subjects(details, task_text)
    adapter = select_sport_adapter((details or {}).get("sport"), task_text, style.slug)
    assets = normalise_selected_assets(selected_assets)
    signatures = verified_signature_assets(assets, subjects)
    signature_refs = {item["reference"].casefold() for item in signatures}
    filtered_assets = [
        asset for asset in assets
        if asset["role"] != "signature_asset" or asset["reference"].casefold() in signature_refs
    ]
    asset_lines = ["SELECTED ASSET USE PLAN"]
    if filtered_assets:
        for asset in filtered_assets:
            subject = f"; subject={asset['subject_name']}" if asset.get("subject_name") else ""
            asset_lines.append(
                f"* {asset['reference']} | role={asset['role']} | use_mode={asset['use_mode']}{subject}"
            )
    else:
        asset_lines.append("* Use only the actual image files supplied with this request and assign their roles before generating.")
    if signatures:
        asset_lines.extend(["", "VERIFIED SIGNATURE MAPPING"])
        asset_lines.extend(f"* {item['subject_name']} -> {item['reference']}" for item in signatures)
    return "\n\n".join(
        (
            COMMON_GENERATION_RULES,
            (
                f"STYLE - {style.label}\n"
                f"Maximum distinct principal people: {style.maximum_distinct_human_subjects}. "
                f"Maximum intentionally composed figures: {style.maximum_intentionally_composed_human_figures}.\n"
                f"Required selected image roles: {', '.join(style.required_image_roles)}. "
                f"Optional roles: {', '.join(style.optional_image_roles) or 'none'}.\n"
                f"{style.generation_rules}"
            ),
            _adapter_block(adapter),
            _task_variables(task_text, details, subjects),
            "\n".join(asset_lines),
        )
    )


def build_harsh_review_prompt(style_slug, task_text, details=None):
    style = get_design_style(style_slug)
    if style is None:
        return STYLE_REQUIRED_LABEL
    subjects = principal_subjects(details, task_text)
    return "\n\n".join(
        (
            COMMON_REVIEW_RULES,
            f"STYLE-SPECIFIC REVIEW - {style.label}\n{style.harsh_review_rules}",
            _task_variables(task_text, details, subjects),
        )
    )


def build_prompt_bundle(style_slug, task_text, details=None, selected_assets=None):
    errors = validate_design_request(style_slug, details, task_text)
    if errors:
        return {"errors": errors, "research": "", "find_images": "", "generation": "", "review": ""}
    return {
        "errors": [],
        "research": build_research_prompt(style_slug, task_text, details),
        "find_images": build_find_images_prompt(style_slug, task_text, details),
        "generation": build_generation_prompt(style_slug, task_text, details, selected_assets),
        "review": build_harsh_review_prompt(style_slug, task_text, details),
    }
