import hashlib
import html
import json
import re
import textwrap
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from activity_log import record_activity_log
import design_schedule
import design_studio_styles
import prompt_store
from sports_cave_prompt_blocks import append_sports_cave_image_realism_rules
from ui_option_ordering import alphabetize_options


BASE_DIR = Path(__file__).resolve().parent
EXPIRED_EDITION_NEXT_CHAPTER_PROMPT_PATH = (
    BASE_DIR / "design_studio_prompts" / "expired_edition_next_chapter_prompt.txt"
)
HIGH_QUALITY_IMAGE_SEARCH_V2_PROMPT_PATH = (
    BASE_DIR
    / "design_studio_prompts"
    / "SPORTS-CAVE-HIGH-QUALITY-IMAGE-SEARCH-PROMPT-V2.txt"
)
NEW_DESIGN_TASK_CATEGORY = "New designs to complete"
MANUAL_NEW_DESIGN_TASK_OPTION = "Enter task manually"
DESIGN_STUDIO_V2_SELECTED_TASK_KEY = design_schedule.SELECTED_DESIGN_TASK_KEY
DESIGN_STUDIO_V2_STYLE_KEY = "design-studio-v2-style"
DESIGN_STUDIO_V2_LOADED_TASK_KEY = "design-studio-v2-loaded-task"
DESIGN_STUDIO_V2_STYLE_MEMORY_KEY = "design-studio-v2-style-memory"
DESIGN_STUDIO_V2_MANUAL_TASK_MEMORY_KEY = "design-studio-v2-manual-task-memory"
DESIGN_STUDIO_V2_DETAILS_MEMORY_KEY = "design-studio-v2-details-memory"
DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER = "HIGHEST-PRIORITY SOURCE SUBJECT LOCK — MANDATORY"


DESIGN_STUDIO_SUBJECT_PRESERVATION_LOCK = f"""
{DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER}

Treat every supplied hero, player, athlete, person, team, rivalry subject, car, motorcycle, jersey, uniform, trophy, or other principal sporting subject as an immutable source asset.

This is an image-editing and compositing task, not a request to regenerate, redraw, reinterpret, restyle, or create a similar version of the supplied subject.

USE THE ORIGINAL SUPPLIED SUBJECT IMAGE ITSELF.

Extract, isolate, mask, and composite the real subject from the supplied source image into the Sports Cave artwork. Preserve the source subject's authentic photographic identity and visible details. The finished subject must continue to look like the same real photograph, not an AI-generated replacement based on it.

DO NOT CHANGE THE SUBJECT

Do not change, reconstruct, enhance, beautify, stylise, repaint, redraw, reinterpret, or regenerate any supplied principal subject.

For every supplied person or athlete, preserve exactly:

* Facial identity
* Facial structure and proportions
* Eyes, eye direction, eyebrows, nose, mouth, ears and jaw
* Skin texture, age, expression and natural asymmetry
* Hair, hairline and facial hair
* Head size and the natural connection between head, neck and body
* Body shape, body proportions and muscle structure
* Pose, stance, movement and orientation
* Arms, hands, fingers, legs and feet
* Clothing, uniform, jersey, numbers, colours, stitching and equipment
* Camera angle, perspective and recognisable photographic characteristics

Do not face-swap the subject. Do not reconstruct the face. Do not create an approximate likeness. Do not "improve" facial symmetry. Do not smooth away real skin texture. Do not change the expression or eye direction. Do not replace the original head, body, hands, uniform or equipment with generated substitutes.

For teams, groups and rivalries, preserve every person separately. Do not merge identities, exchange facial features, duplicate people, remove people, change poses, change body types, or generate replacement team members.

For cars, motorcycles and other vehicles, preserve exactly:

* Original body shape and proportions
* Livery, paintwork, colours and sponsor placement
* Numbers, lettering, badges and visible markings
* Wheels, tyres, wings, aero surfaces, cockpit and mechanical details
* Camera angle, perspective, reflections and recognisable era-specific details

Do not redesign, modernise, simplify, reshape, reliver, repaint, or generate an approximate version of the supplied vehicle.

For jerseys, uniforms, trophies and sporting equipment, preserve the real object's shape, colours, numbers, text, logos, materials, stitching, wear, reflections and era-specific details. Do not invent or replace details.

BACKGROUND-FIRST ADAPTATION

Build and adapt the artwork around the preserved original subject.

The background, atmosphere, colour grading, smoke, stadium, arena, track, lighting, shadows, typography, border and collector elements must accommodate the original subject. Never alter the subject to make it fit the background or design.

Match the new environment to the subject's existing:

* Pose
* Camera angle
* Perspective
* Crop
* Direction of movement
* Light direction
* Contrast
* Era
* Sport
* Team colours
* Venue or historical setting

Place the preserved subject naturally into a realistic Sports Cave environment. Adjust the background lighting, environmental shadows, depth, haze and colour around the subject so the composite feels believable.

Do not repaint the subject to match the scene. Use restrained, non-destructive edge integration and global colour treatment only where necessary. Preserve natural skin tones, original facial detail, uniform colours, vehicle livery and photographic texture.

The result must look like a premium professional photographic composite made from the supplied real images, not an AI illustration.

SOURCE LIMITATIONS

Do not invent missing body parts, hidden faces, unseen vehicle sections, obscured jersey details or cropped equipment unless the requested composition absolutely requires it.

Prefer a composition that respects the original crop. If the source image does not contain a required detail, adapt the background and layout around the available real subject instead of hallucinating a replacement.

Do not use a background or composition that requires the subject to be rotated, reposed, mirrored, anatomically reconstructed or substantially regenerated.

Mirroring is prohibited when it would reverse jersey numbers, text, logos, vehicle liveries, handedness or historically important details.

REALISM FAILURE CONDITIONS

The output fails and must not be accepted if any supplied principal subject appears:

* AI-generated
* Illustrated, painted, plastic, waxy or over-smoothed
* Face-swapped or only approximately similar
* Younger, older or differently proportioned
* Cross-eyed or altered in eye direction
* Warped, stretched, duplicated or anatomically incorrect
* Detached at the head, neck, shoulders or limbs
* Given generated hands, fingers, teeth, ears or facial features
* Given a different pose, expression, hairstyle, uniform or body type
* Blended with another person
* Replaced by a newly generated interpretation
* Given incorrect jersey numbers, lettering, logos or equipment
* Placed under lighting that destroys identity or photographic realism
* Rendered with fake skin, fake fabric, fake reflections or synthetic detail
* Shown as a redesigned or inaccurate vehicle, jersey, trophy or sporting object

If creative styling conflicts with subject accuracy, reduce the styling. Subject authenticity and photographic realism always take priority.

SPORTS CAVE DESIGN APPLICATION

Once the original subjects are safely preserved, place them within the requested premium Sports Cave limited-edition collector design.

The design may transform or generate:

* Background
* Stadium, arena, track, court, field, tunnel or environmental setting
* Atmospheric lighting
* Smoke, dust, haze and depth
* Supporting textures
* Negative space
* Typography
* Thin Sports Cave border
* Collector details
* Subtle gold accents
* The attached limited-edition plaque

These generated design elements must support the real subject and never overlap, obscure, reshape or alter important facial, bodily, uniform, vehicle or equipment details.

Use the supplied Sports Cave limited-edition plaque as an exact visual asset wherever it is requested. Composite the supplied plaque naturally into the artwork. Do not recreate, redraw, restyle, retype or approximate the plaque, its emblem, lettering, proportions or edition number.

FINAL PRE-GENERATION CHECK

Before generating, verify internally:

1. Every principal subject will use the supplied source image itself.
2. No face, body, pose, uniform, vehicle, jersey or equipment will be regenerated.
3. The background and design will adapt to the subject.
4. No composition instruction requires anatomical reconstruction.
5. The finished work will look like a real photographic composite.
6. The Sports Cave styling will enhance the collector atmosphere without modifying the authentic subject.
7. If any instruction conflicts with these rules, ignore the conflicting instruction and preserve the source subject.
"""


DESIGN_STUDIO_HERO_DOMINANCE_MARKER = "PRIMARY HERO DOMINANCE AND MINIMAL BACKGROUND — MANDATORY"
DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER = "SPORTS CAVE LIMITED-EDITION BORDER — MANDATORY"
DESIGN_STUDIO_STRICT_BORDER_CONTAINMENT_MARKER = "STRICT BORDER CONTAINMENT AND SAFE ZONE — MANDATORY"


DESIGN_STUDIO_HERO_DOMINANCE_AND_BORDER_LOCK = f"""
{DESIGN_STUDIO_HERO_DOMINANCE_MARKER}

The supplied and approved main hero subjects must dominate the finished artwork. These may include an athlete, driver, team, rivalry pair, vehicle, motorcycle, jersey, trophy, or another specifically supplied principal subject.

Use only the supplied main heroes. Do not invent, generate, duplicate, reconstruct, or add any additional athletes, players, drivers, teammates, opponents, coaches, spectators, or human figures.

ABSOLUTELY DO NOT ADD:

* AI-generated background players
* Faceless or poorly formed people
* Headless or partially visible bodies
* Anonymous athletes or teammates
* Fake crowd members with recognisable bodies or faces
* Player silhouettes that compete with the main heroes
* Ghosted or duplicated versions of the hero
* Random helmets, limbs, faces, uniforms, or human shapes
* Additional people merely to fill empty space

If multiple supplied heroes are required for a team or rivalry design, preserve and use those supplied heroes only. Never generate extra supporting players.

The supplied main heroes must carry the emotional and visual weight of the composition. Their faces, bodies, vehicles, uniforms, or defining details must remain clearly visible and immediately recognisable.

Keep the background minimal, cinematic, relevant and controlled. Build atmosphere with elements such as:

* Stadium or circuit architecture
* Empty stands or indistinct crowd texture
* Lighting, shadows and subtle spotlights
* Smoke, haze, dust, rain or sparks
* Track, turf, court or arena textures
* Scoreboards, goal structures or venue landmarks
* Restrained team colours and subtle historical details

Any crowd treatment must remain distant, abstract, blurred and textural. It must not contain recognisable individual people, faces, bodies or AI-generated players.

Do not overcrowd the composition. Do not fill negative space with unnecessary subjects. Negative space is intentional and should make the main heroes feel larger, stronger and more premium.

The final hierarchy must always be:

1. Supplied main heroes
2. Title and essential collector storytelling
3. Sports Cave limited-edition plaque or collector details
4. Restrained venue atmosphere
5. Minimal supporting effects

{DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER}

Every finished collector artwork must include a clean, precise and premium Sports Cave border inside the artwork canvas.

The border must feel custom-designed for an expensive limited-edition sports collectible—not like a generic poster outline, picture frame, television graphic or template.

Create a refined Sports Cave border using:

* Deep black, charcoal or near-black foundations
* Fine warm-gold or muted-metallic pinlines
* Clean layered keylines
* Precise symmetrical spacing
* Restrained geometric corner detailing
* Subtle plaque-inspired collector accents
* Consistent thickness on every edge
* Clear separation between the artwork and its outer boundary
* Safe internal margins suitable for professional printing and framing

The border should be detailed enough to signal “limited edition” but restrained enough to remain masculine, timeless and premium. It should frame the story without competing with the heroes.

The border must remain:

* Perfectly straight
* Symmetrical
* Crisp and uninterrupted
* Consistent on all four sides
* Fully contained inside the canvas
* Free from warping, broken corners or uneven thickness
* Compatible with the required landscape 4:3 composition

DO NOT USE:

* Thick generic borders
* Cheap gold gradients
* Bright yellow gold
* Neon effects
* Ornate Victorian decoration
* Excessive filigree
* Busy sports-broadcast graphics
* Random corner shapes
* Uneven or misaligned lines
* Fake external frames or wall mockups
* Borders that crop or cover the supplied heroes
* Decorative elements that overpower the artwork

The border, plaque and artwork must feel like one cohesive Sports Cave collector product.

{DESIGN_STUDIO_STRICT_BORDER_CONTAINMENT_MARKER}

The Sports Cave branded border is a hard containment boundary for the entire composition.

Every visual element must remain completely inside the inner edge of the border, including:

* Main heroes and all supplied subjects
* Heads, hair, helmets, hands, feet and equipment
* Cars, motorcycles, jerseys and trophies
* Titles, names, dates, statistics and supporting text
* Signatures, logos, flags and collector details
* Sports Cave plaque and edition information
* Stadiums, tracks and venue elements
* Smoke, sparks, rain, dust, haze and lighting effects
* Shadows, glows, textures and decorative graphics

Nothing may overlap, sit over, pass through, hide or extend beyond the border. No element may be placed between the border lines or outside the bordered artwork area.

Maintain a clean internal safety gap between important content and the border. Keep heroes, faces, typography, signatures, plaques and essential details comfortably inset from all four edges.

If a hero, vehicle, title or other element does not fit safely inside the border:

1. Reduce its scale.
2. Reposition it inward.
3. Adjust the composition around it.

Never crop the element against the border or allow it to break through the border.

The border must always render as the uninterrupted topmost structural layer. All four sides and all four corners must remain fully visible, perfectly straight, symmetrical and free from obstruction.

The background artwork may fill the interior area up to the border, but it must stop cleanly at the border. Outside the border, allow only a clean, uniform deep-black or near-black outer margin. Do not continue scenery, lighting, smoke, people, vehicles, typography or decorative effects outside the border.

ABSOLUTELY DO NOT ALLOW:

* Heroes breaking through the border
* Heads, helmets or hair crossing a border line
* Vehicles or equipment extending outside the border
* Titles or signatures sitting over the border
* Plaques attached across the border
* Smoke, sparks, glow or lighting spilling beyond it
* Background scenery continuing outside it
* Border lines hidden behind artwork
* Cropped or missing border sections
* Broken, warped or uneven corners
* Any intentional “pop-out” or layered-over-border effect

The finished design must look like one precisely contained, professionally printed Sports Cave limited-edition collector artwork. Nothing inside the composition may escape its branded border.
"""


SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER = "SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_V1"
_LEGACY_SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_V1 = f"""
{SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER}

MANDATORY WHEN THE DESIGN IS A RIVALRY, VERSUS, FACE-OFF OR TWO-LEGEND CONCEPT

This is a premium minimalist rivalry collector artwork.

The rivalry must be understood instantly, even at Shopify-thumbnail size.

The two opposing principal subjects are the only visual heroes. Give them equal status, comparable scale and balanced visual weight unless the user explicitly requests otherwise.

Never add anonymous players, generated athletes, faceless figures, extra team members, ghost portraits, duplicated subjects or small action images behind the two heroes.

SOURCE-PHOTO REALISM — ABSOLUTE PRIORITY

Use the actual supplied source photographs of both principal subjects.

Each supplied subject is an immutable photographic asset. Isolate, mask and composite the real source image itself.

Do not:

* Regenerate either person
* Reconstruct or enhance either face
* Face-swap
* Approximate a likeness
* Alter facial features or expression
* Change eye direction
* Change age, skin texture or natural asymmetry
* Change head size or head-to-body connection
* Change body type, pose or orientation
* Generate replacement hands, limbs, uniforms or equipment
* Mirror a source if it reverses text, numbers, logos, handedness or historical details
* Invent body parts outside the available source crop
* Turn a front-facing subject into a profile
* Turn a rear-facing subject toward the camera
* Force the subjects to face one another by rebuilding their faces or bodies

Adapt the entire composition around the real supplied subjects.

If a supplied image is too blurred or small to support a clear hero face, do not manufacture a sharper AI face. Use a clearer authentic supplied reference if available. If no usable authentic source exists, flag that a better image is required.

COMPOSITION MODE SELECTION

Choose the strongest of these two modes according to the supplied real photographs.

MODE A — MINIMAL FACE-OFF RIVALRY

This is the default rivalry format when the supplied source images naturally support it.

Use:

* One authentic subject on the left
* One authentic subject on the right
* Both subjects naturally oriented inward where their original poses allow
* Equal or near-equal head size
* Equal or near-equal visual weight
* Large head-and-shoulders, chest-up or waist-up presentation
* Clear, recognisable and unobscured faces
* Controlled negative space between them
* A visually charged central meeting point
* Subtle opposing team colours or light treatment on their respective sides

Target a powerful face-to-face confrontation similar in structural strength to the attached minimalist face-off bestseller, but built from the current authentic source photographs.

Do not mirror, rotate, repose or reconstruct either person to achieve the face-off.

If the supplied photographs do not naturally look inward, select other authentic supplied images that do. If none are suitable, preserve their real orientations and create rivalry tension through placement, central lighting and environmental separation.

The two heads should generally be within approximately 10% of each other in scale. Neither subject should accidentally overpower the other.

MODE B — LEGENDS JERSEY-BACK COMPOSITION

Use this mode when:

* The user specifically requests a jersey-back design
* The supplied authentic images show recognisable rear jersey views
* The names and numbers carry the strongest identity and nostalgia
* A legacy or generational concept is stronger than a facial confrontation

Use:

* Two real rear-view subjects
* Side-by-side placement
* Equal scale and visual importance
* Authentic jersey names, numbers, colours and stitching
* Natural spacing between the subjects
* Strong silhouettes against a restrained dark background
* Subtle light behind each subject to separate the real cutouts from the environment

Never create a generated jersey-back replacement.

Do not invent, repair, retype or redesign jersey names or numbers. Preserve the real lettering and numbers contained in the supplied source photographs.

Do not generate faces, profile views or missing body parts for rear-facing subjects.

This mode should evoke the emotional strength of the attached minimalist jersey-back bestseller without copying that artwork.

MODE SELECTION PRIORITY

1. Follow an explicit user-selected format.
2. Use Face-Off Mode when two authentic clear facial images naturally support opposing placement.
3. Use Jersey-Back Mode when authentic rear-view jersey images create the stronger legacy concept.
4. Never force either format by altering, mirroring or regenerating a supplied subject.
5. If neither format is supported perfectly, use a clean two-sided rivalry composition that preserves both original photographs unchanged.

MINIMALIST BACKGROUND SYSTEM

The background must support the rivalry without competing with it.

Use only:

* One restrained, era-appropriate stadium, arena, field, court, circuit, ring or environmental layer
* Deep black or charcoal foundation
* Subtle atmospheric smoke, haze, turf, court, asphalt or venue texture
* Controlled central light or shadow divide
* Restrained team-colour atmosphere on each subject’s side
* Subtle gold only for collector emphasis

Do not include:

* Background players
* Faceless generated athletes
* Crowded action montages
* Duplicate versions of either hero
* Floating heads
* Multiple stadium scenes
* Unnecessary game-action strips
* Giant team logos
* Fake trophies
* Fireworks
* Excessive smoke
* Cheap glows
* Random sparks or particles
* Heavy effects across faces or uniforms
* Social-media-poster styling

The venue should remain dark and understated. It may be recognisable, but it must never become a third hero.

LAYOUT

Maintain a clean landscape 4:3 collector composition.

Recommended hierarchy:

1. Short cinematic collector title at the top
2. Two opposing co-equal heroes
3. Optional restrained names or “NAME VS NAME” line
4. Exact Sports Cave limited-edition plaque near the bottom
5. Thin internal Sports Cave border

Leave deliberate negative space around faces, title, uniforms and plaque.

Keep all important elements safely inside the canvas.

Do not place a room, wall or physical picture frame into the final artwork unless the user explicitly requests a mockup.

TITLE AND TEXT

Use minimal typography.

The title should:

* Be short
* Feel cinematic
* Express rivalry, legacy or generational tension
* Sit above the matchup
* Use controlled premium serif or uppercase typography
* Remain readable at thumbnail size

Optional supporting text may identify the matchup, such as:

NAME VS NAME

Do not add paragraphs, excessive statistics, fake quotes, invented dates or unnecessary descriptive copy.

Do not generate fake signatures. Include signatures only when authentic signature assets are supplied and explicitly intended for use.

SPORTS CAVE BORDER

Use a clean, thin, premium internal border inspired by the attached bestsellers.

The border should:

* Use restrained gold and black
* Be symmetrical and accurately aligned
* Remain thin and sophisticated
* Sit inside a safe canvas margin
* Support the title and collector presentation
* Never resemble a thick decorative picture frame
* Never cross a face, body, jersey, name, number or plaque

Avoid ornate clutter, uneven corners, warped lines and oversized gold decoration.

LIMITED-EDITION PLAQUE

Use the exact supplied Sports Cave limited-edition plaque asset.

Do not recreate, redraw, retype or approximate it.

Position it subtly near the bottom centre or within suitable dark negative space.

The plaque must:

* Retain its exact proportions
* Remain sharp and readable
* Be smaller than the principal subjects
* Never become the focal point
* Never be stretched, cropped or regenerated
* Feel integrated like a genuine collector plate

FINAL RIVALRY FAILURE CONDITIONS

Reject and regenerate the result if:

* Any additional player appears in the background
* More subjects appear than the user supplied or requested
* Either face looks AI-generated, altered, painted, waxy or approximate
* Either subject has been mirrored, reposed or anatomically reconstructed
* One hero accidentally dominates a supposedly equal rivalry
* The subjects look away without intentional visual tension
* Facial detail is hidden by smoke, darkness, text or effects
* Jersey names, numbers, uniforms, helmets or equipment are inaccurate
* The background becomes crowded
* The artwork resembles a collage or social-media poster
* The plaque is oversized or inaccurate
* The border is thick, distorted or cheap-looking
* The design loses the clean, premium Sports Cave bestseller character

FINAL INTERNAL CHECK

Before generating a rivalry artwork, verify:

1. Only the requested principal rivals will appear.
2. Both will use their actual supplied source photographs.
3. Both faces, bodies, poses, uniforms and equipment remain unchanged.
4. The selected mode is supported by the real source orientations.
5. No mirroring or anatomical reconstruction is required.
6. Both heroes have balanced visual weight.
7. The background is minimal and contains no generated players.
8. The rivalry reads instantly.
9. The border is thin, clean and premium.
10. The exact supplied plaque is subtle and correctly proportioned.
11. The final result feels like premium framed collector art—not a poster.
"""


RIVALRY_STRUCTURED_CONTEXT_KEYS = (
    "design_type",
    "artwork_type",
    "concept_type",
    "composition_type",
    "composition_mode",
    "design_mode",
    "format",
    "template",
)
RIVALRY_STRUCTURED_CONTEXT_VALUES = (
    "rivalry",
    "rivalries",
    "vs",
    "versus",
    "face_off",
    "face-off",
    "face off",
    "faceoff",
    "head_to_head",
    "head-to-head",
    "head to head",
    "great_debate",
    "great-debate",
    "great debate",
    "two_legend",
    "two-legends",
    "two legends",
    "two_legend_concept",
    "two-legend concept",
    "two legend concept",
    "jersey_back",
    "jersey-back",
    "jersey back",
    "two famous jersey backs",
    "legacy_rivalry",
    "legacy rivalry",
)
RIVALRY_TEXT_PATTERNS = (
    r"\bvs\.?\b",
    r"\bv\.\b",
    r"\bversus\b",
    r"\bface[\s-]?off\b",
    r"\bhead[\s-]?to[\s-]?head\b",
    r"\bgreat\s+debate\b",
    r"\btwo[\s-]+legend(?:s)?\b",
    r"\btwo\s+opposing\b",
    r"\bopposing\s+(?:athletes|drivers|fighters|teams|icons|legends)\b",
    r"\bjersey[\s-]?back\b",
    r"\btwo\s+famous\s+jersey\s+backs\b",
)
RIVALRY_CONTEXT_TEXT_KEYS = (
    "task",
    "task_text",
    "title",
    "design_title",
    "brief",
    "description",
    "prompt",
    "text",
)


SPORTS_CAVE_SIGNATURE_IMAGE_SEARCH_RULES_MARKER = "SPORTS_CAVE_SIGNATURE_IMAGE_SEARCH_RULES_V1"
SPORTS_CAVE_SIGNATURE_IMAGE_SEARCH_RULES_V1 = f"""
{SPORTS_CAVE_SIGNATURE_IMAGE_SEARCH_RULES_MARKER}

MANDATORY FOR NAMED HUMAN SPORTING SUBJECTS

This block controls the balance and ordering of every Sports Cave Design Studio Find Images carousel.

REFERENCE PRIORITY - APPLY IN THIS EXACT ORDER

1. FEATURED PLAYER / HERO REFERENCES - HIGHEST PRIORITY
2. VENUE / BACKGROUND REFERENCES - SECOND PRIORITY
3. EQUIPMENT / TROPHY / HISTORICAL DETAIL REFERENCES - THIRD PRIORITY
4. SIGNATURE REFERENCES - SUPPORTING REFERENCES ONLY AND ALWAYS LAST

Use the available image capacity in that order. The clear majority of all non-signature results must be useful, high-quality player or hero photographs. Player/hero and venue/background references together must dominate the complete carousel.

Never remove a useful player, hero or venue image to make room for extra autograph or signed-memorabilia material.

FEATURED PLAYER / HERO REFERENCES - HIGHEST PRIORITY

Player and hero photographs must dominate the results.

For every featured player, athlete, driver, rider, fighter, team or other principal hero, prioritise multiple different high-quality photographic references showing:

* A clear, realistic and unobstructed face when the subject is human
* Front-facing and three-quarter facial angles
* Authentic action poses
* Chest-up, waist-up or tight three-quarter views that keep the face, uniform, available number and equipment clear
* The correct team, season, era, jersey, helmet, livery and colours
* Strong hero compositions suitable for premium collector artwork
* The best available resolution and photographic realism

For multiple-player or rivalry designs, provide balanced coverage of every featured hero. Do not return many images of one hero while neglecting another.

Do not use these as normal player or hero references:

* Autographed or signed photographs
* Trading cards
* Signed balls, helmets, jerseys or other memorabilia
* Memorabilia listings or display cases
* Framed products
* Posters or existing artwork
* Collages
* AI-generated images
* Heavily altered faces
* Low-resolution thumbnails
* Images where the face is obscured
* Distant crowd shots or photographs where the principal occupies only a small part of the frame
* Full-body photographs that cannot support a strong close crop at print quality
* Repeated copies or alternate crops of the same photograph

VENUE / BACKGROUND REFERENCES - SECOND PRIORITY

After the player or hero references, find the strongest accurate background material for the design:

* The correct stadium, arena, circuit, field, court or sporting location
* Era-appropriate venue photography where relevant
* Wide establishing views
* Medium views showing recognisable architecture or atmosphere
* Historically accurate crowd, lighting, tunnel, scoreboard, skyline or environmental details
* The location most emotionally connected to the featured player, rivalry or sporting moment

Background references must support a premium, realistic Sports Cave composition. Never classify memorabilia-product photography as a background reference.

EQUIPMENT / TROPHY / HISTORICAL DETAILS - THIRD PRIORITY

Only after strong hero and background coverage, use remaining non-signature capacity for essential uniform, equipment, car, motorcycle, trophy or historical-detail references that improve factual accuracy.

STRICT SIGNATURE LIMIT - EXACTLY ONE SLOT PER DISTINCT FEATURED PERSON

In addition to the required hero, venue and factual-detail references, find one and only one authentic signature or autograph image for every distinct named principal human subject intended to appear in the artwork.

This includes:

* Players
* Athletes
* Drivers
* Riders
* Fighters
* Golfers
* Tennis players
* Jockeys
* Cricketers
* Coaches or managers when they are principal subjects
* Every named hero in a rivalry or multi-legend design

SIGNATURE SEARCH REQUIREMENTS

For each principal named subject:

* Search using the person's complete name.
* Include their sport or team when needed to prevent mistaken identity.
* Find exactly one strongest, clearest and most usable authentic signature reference.
* Never return a second signature example for the same person.
* Prefer an isolated signature on a transparent, white or plain background.
* Prefer high-resolution signature marks with complete, readable strokes.
* Prefer authoritative or reputable sources with credible attribution.
* Ensure the signature belongs to the exact intended athlete.

One featured person means exactly one signature image total.

Two featured people mean a maximum of two signature images total: one for each person.

Three featured people mean a maximum of three signature images total: one for each person.

The maximum number of signature images in the carousel always equals the number of distinct named principal human subjects. Never fill unused carousel positions with additional signature or autograph material.

A signed player photograph, including a signed action photograph, consumes that person's one signature slot. It must be classified only as a signature_asset and must not also count as a player, hero or action reference.

A signed ball, trading card, photograph, helmet, jersey or memorabilia display also consumes that person's one signature slot and is normally inferior to a clean isolated specimen. Never return several such items for the same person.

Prioritise:

* Official athlete, team or foundation sources
* Hall of Fame or recognised sporting archives
* Wikimedia or established archival sources
* Reputable authenticated-autograph references
* Clean scans of known autograph specimens

Avoid:

* AI-generated signatures
* Typed script fonts
* Fan-made approximations
* Unverified marketplace listings
* Forged or suspicious autograph examples
* Watermarked previews
* Signatures obscured by merchandise, cards or photographs
* Low-resolution thumbnails
* Incomplete or cropped autograph strokes
* Prebuilt artwork containing unrelated graphics
* Signatures belonging to another person with the same or a similar name

CAROUSEL OUTPUT

Place the strongest signature reference for each named subject directly in the same image carousel as the other retrieved reference images.

Signature references must appear at the very end of the carousel, after all player/hero, venue/background, and equipment/trophy/historical-detail references.

When the existing output format supports labels or internal roles, organise the carousel in this exact order:

1. PLAYER / HERO REFERENCES
2. VENUE / BACKGROUND REFERENCES
3. EQUIPMENT / TROPHY / HISTORICAL DETAILS
4. SIGNATURE REFERENCES - ONE PER PLAYER ONLY

Do not place signature references in a separate written section.

Preserve the existing image-only output contract. Do not add research, analysis, recommendations or creative direction around the carousel.

Use descriptive internal metadata or image alt text that clearly identifies:

* The athlete's exact full name
* That the image is a signature asset
* The corresponding subject identifier where supported

Example internal role:

signature_asset:
subject_name: [Exact athlete full name]
subject_id: [stable_subject_identifier]

A signature must never be classified as:

* Hero image
* Player image
* Background image
* Venue reference
* General atmosphere reference

It is a separate exact graphic asset intended for collector detailing.

MULTI-SUBJECT REQUIREMENT

For a two-player rivalry, retrieve one authentic signature for each rival.

For a multi-player design, retrieve one authentic signature for every principal named player intended to appear.

Never merge several signatures into one generated graphic.

Never assign one player's signature to another player.

If no sufficiently reliable signature can be found for a subject, state or mark that signature asset as unavailable using the existing internal workflow metadata or unavailable state. Do not fabricate or approximate one, do not return several uncertain examples, and do not replace it with signed merchandise. Continue with the other valid player, venue and factual-detail reference images.
"""

SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_V1 = "\n\n".join(
    (
        SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER,
        design_studio_styles.RIVALRY_FACE_OFF_GENERATION_RULES,
    )
)


SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2 = (
    HIGH_QUALITY_IMAGE_SEARCH_V2_PROMPT_PATH.read_text(encoding="utf-8").strip()
)
SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2_MARKER = (
    SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2.splitlines()[0]
)


SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER = "SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_V1"
SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_V1 = f"""
{SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER}

MANDATORY WHEN VALID SIGNATURE ASSETS ARE SUPPLIED OR SELECTED

Use the actual supplied or retrieved signature image as an exact collector graphic asset.

The signature is not loose inspiration.

Composite the original signature mark itself into the Sports Cave artwork.

Never:

* Generate a new signature
* Imitate the athlete's handwriting
* Trace or redraw the signature
* Reconstruct missing strokes
* Repair it with generated lettering
* Convert the athlete's name into a script font
* Change the handwriting
* Combine parts from different autograph references
* Assign the wrong signature to a player
* Add a signature for a person without a valid source asset
* Add more than one signature for the same athlete unless explicitly requested

PRESERVE THE AUTHENTIC SIGNATURE

Preserve exactly:

* Stroke paths
* Letter shapes
* Slant
* Spacing
* Proportions
* Flourishes
* Line intersections
* Natural handwriting irregularities
* Recognisable autograph characteristics

Permitted non-destructive preparation:

* Remove only the external white, plain or transparent background
* Isolate the genuine ink strokes
* Scale the complete signature proportionally
* Apply one restrained uniform colour to the existing strokes
* Use subtle opacity or blending adjustments
* Add a minimal natural shadow or glow only when required for legibility

Do not thicken, smooth, simplify, stretch, warp, crop or regenerate the handwriting.

COLLECTOR PLACEMENT

The signature must feel like a refined memorabilia detail, not decoration or advertising.

Use:

* Warm off-white
* Restrained champagne gold
* Muted metallic gold
* Subtle silver where appropriate to the design
* The signature's original colour when it already suits the artwork

Place it within clean negative space:

* Near the corresponding player
* Beneath or beside the player's shoulder
* Near the title when sufficient space exists
* Above the collector plaque with clear separation
* In a dark stadium, arena, sky or environmental area
* Beneath the corresponding jersey in jersey-back artwork

The signature must:

* Remain fully recognisable
* Be sharp at print resolution
* Stay secondary to the player and title
* Remain safely inside the Sports Cave border
* Avoid faces, hands, jersey names, numbers and important equipment
* Avoid touching the plaque or title
* Never become a giant focal point
* Never resemble a promotional watermark

A typical signature should occupy approximately 10-18% of the canvas width, adjusted according to its natural proportions and the available negative space.

SINGLE-HERO ARTWORK

Use one authentic signature belonging to the hero.

Position it subtly near the hero in clean negative space.

Do not add signatures belonging to coaches, teammates or supporting figures unless those people are also intended principal subjects.

RIVALRY AND FACE-OFF ARTWORK

Use one authentic signature for each principal rival.

* Place each signature on its corresponding player's side.
* Keep both signatures comparable in visual importance.
* Preserve each signature's natural proportions.
* Do not force them to be identical in width.
* Do not cross the signatures through the central rivalry divide.
* Do not let either signature overpower its corresponding player.
* Never swap the left and right player-signature associations.

For rivalry artwork:

* Left hero -> left hero's authentic signature
* Right hero -> right hero's authentic signature

LEGENDS JERSEY-BACK ARTWORK

Place each authentic signature beneath or near its corresponding rear-view subject.

Never place the autograph over:

* Jersey surname
* Jersey number
* Team markings
* Important stitching
* The athlete's silhouette

MULTI-PLAYER ARTWORK

Use one authentic signature per principal named subject.

Arrange the signatures carefully near their corresponding subjects or within one restrained signature area.

Keep the composition clean. Reduce signature scale and decorative effects before allowing the artwork to become cluttered.

APPROVED EXISTING ARTWORK

For an existing approved design:

* Preserve every existing signature exactly unless the user requests a change.
* Do not add new signatures during an unrelated edit.
* Do not remove, replace, duplicate or reposition existing signatures unless requested.
* If the user specifically asks to add signatures, use only valid supplied or retrieved signature assets.

MISSING SIGNATURE FALLBACK

If an authentic signature asset is unavailable:

* Do not generate one.
* Do not use a script font.
* Do not approximate the athlete's autograph.
* Do not block the rest of the artwork from being generated.
* Omit only the unavailable signature.

For a rivalry, never duplicate the available rival's signature to create artificial symmetry.

COMMERCIAL ACCURACY

The visual signature is a printed collector-art detail.

Do not add claims such as:

* Hand-signed
* Personally signed
* Authenticated autograph
* Autographed edition
* Signed by the player

unless the product is genuinely hand-signed and the user explicitly supplies proof and requests that wording.

FINAL SIGNATURE FAILURE CONDITIONS

Reject and regenerate the result if:

* A signature was invented
* A signature looks like a typed font
* The handwriting differs from the supplied asset
* The wrong signature appears beside a player
* A player's signature is duplicated
* Strokes are missing, rewritten or malformed
* The signature is stretched or disproportionately scaled
* It covers a face, jersey number, title or plaque
* It is too large or visually dominant
* It looks like a watermark
* It makes the artwork cluttered
* It falsely implies the physical product is hand-signed
* An existing approved signature was changed without permission

DATA AND ASSET HANDOFF

Ensure every selected signature asset is carried from Find Images into the final generation workflow with its athlete association intact.

The final generation prompt must contain an explicit mapping of each principal subject to the selected signature image reference.

Do not rely only on carousel order.

Do not allow a signature asset to become detached from its subject name during image selection, prompt assembly or regeneration.
"""


SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER = "AUTHENTIC SIGNATURE PRESERVATION AND PREMIUM TREATMENT — MANDATORY"
SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_RULES = f"""
{SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER}

Only use the supplied, selected or reliably sourced authentic signature belonging to the featured person.

The signature is an identity-locked reference. Preserve its genuine handwritten structure exactly, including:

* Letter shapes
* Initials and recognisable marks
* Natural slant and baseline
* Stroke direction and connections
* Loops, crossings and overlaps
* Spacing and proportions
* Flourish shapes and lengths
* Beginning and ending strokes
* Natural pressure and line-weight variation
* Overall width-to-height ratio

Do not redraw, reinterpret, simplify, correct, beautify or replace the authentic signature.

Do not generate an approximate signature from the person’s name. Do not use a script font, invented handwriting or generic autograph styling.

If no reliable signature reference is supplied or found, omit the signature. Never fabricate one.

PREMIUM VISUAL TREATMENT

Present the authentic signature as a thin, elegant and restrained collector detail.

The signature should feel:

* Refined
* Handwritten
* Authentic
* Lightly weighted
* Clean and precise
* Understated
* Premium
* Integrated into the artwork

Use a clean single-colour treatment such as restrained warm gold, champagne gold, muted silver, soft ivory or subtle off-white—whichever best suits the artwork.

Keep the signature’s scale modest. It should reward closer viewing without competing with the main hero, title, plaque or central story.

Where the source signature contains scan noise, a heavy background, compression or an artificial halo, clean only those unwanted artefacts. Preserve the actual handwritten stroke paths and natural pressure variation.

Where technically possible, use the supplied signature as a preserved composited asset instead of asking the image model to recreate it.

Do not force a naturally bold section of an authentic signature into an artificial hairline. Preserve genuine stroke variation while ensuring the overall presentation remains visually light through restrained scale, clean colour and minimal effects.

ABSOLUTELY DO NOT USE:

* Thick or chunky signature rendering
* Artificially bold strokes
* Generic cursive fonts
* Invented or approximate autographs
* Redesigned letter shapes
* Calligraphy-style reinterpretations
* Heavy outlines
* Multiple stacked strokes
* Drop shadows
* Strong glows
* Bevelled or embossed effects
* Bright yellow-gold colouring
* Thick metallic foil effects
* Oversized signatures
* Repeated or duplicated signatures
* Signatures used as background texture
* Signatures crossing a face, body or vehicle
* Signatures touching or covering the border
* Signatures placed outside the Sports Cave border

PLACEMENT AND CONTAINMENT

Place the signature once only, in a clean area of negative space where it complements the composition.

The signature must:

* Remain fully inside the Sports Cave branded border
* Maintain a comfortable safety gap from the border
* Remain completely legible
* Avoid covering faces, hands, uniforms, vehicles or important details
* Avoid competing with the title or collector plaque
* Sit naturally within the composition
* Look intentionally placed rather than pasted on
* Remain smaller and visually quieter than the main title

If the signature does not fit cleanly, scale it down proportionally or move it inward. Never crop, stretch, squash, warp or wrap it.

SIGNATURE PRIORITY

The visual hierarchy must remain:

1. Supplied main hero or heroes
2. Title and defining sporting story
3. Sports Cave plaque and collector information
4. Authentic signature
5. Minimal atmospheric details

The signature adds authenticity and collector value. It must never become the dominant visual element.
"""


SIGNATURE_SUBJECT_CONTEXT_KEYS = (
    "principal_subjects",
    "principal_athletes",
    "principal_players",
    "principal_human_subjects",
    "signature_subjects",
    "signature_assets",
    "heroes",
    "athletes",
    "players",
    "drivers",
    "fighters",
    "subjects",
)
SIGNATURE_SUBJECT_NAME_KEYS = (
    "name",
    "full_name",
    "subject_name",
    "athlete_name",
    "player_name",
    "driver_name",
    "fighter_name",
    "label",
)
SIGNATURE_ASSET_REFERENCE_KEYS = (
    "asset_reference",
    "image_reference",
    "reference",
    "source",
    "url",
    "file",
    "path",
    "file_path",
    "local_path",
    "asset_path",
    "id",
)
SIGNATURE_VERIFIED_ASSET_CONTEXT_KEYS = (
    "signature_assets",
    "selected_signature_assets",
    "supplied_signature_assets",
    "authentic_signature_assets",
    "signature_references",
    "signatures",
)
SIGNATURE_ASSET_ROLE_KEYS = (
    "role",
    "asset_role",
    "image_role",
    "type",
    "image_type",
    "classification",
    "category",
)
SIGNATURE_ASSET_ROLE_VALUES = {
    "signature",
    "signature_asset",
    "signature asset",
    "autograph",
    "autograph_asset",
    "autograph asset",
}
SIGNATURE_CONTEXT_TEXT_KEYS = (
    "task",
    "task_text",
    "title",
    "design_title",
    "brief",
    "description",
    "prompt",
    "text",
)
SIGNATURE_TEXT_SUBJECT_STOPWORDS = {
    "AFL",
    "AI",
    "Archive Edition",
    "Artwork",
    "Bathurst",
    "Championship Edition",
    "Collector",
    "Collector Artwork",
    "Collector Design",
    "Collector Piece",
    "Create",
    "Create New",
    "Design",
    "Edition",
    "Existing",
    "Final",
    "Find Images",
    "Hero",
    "Legacy Edition",
    "Limited Edition",
    "Logo",
    "Man Cave",
    "Minimalist",
    "Motorsport",
    "Mount Panorama",
    "NBA",
    "NFL",
    "New",
    "New Design",
    "Next Chapter",
    "Premium",
    "Rivalry",
    "Sports Cave",
    "Step",
    "The",
    "Ultimate Moment",
    "VS",
    "Wall Art",
}
SIGNATURE_VEHICLE_OR_VENUE_ONLY_PATTERN = re.compile(
    r"\b(?:vehicle|car|race\s*car|motorcycle|bike|jersey|trophy|venue|stadium|arena|circuit|track|course|room|mockup)[\s-]*only\b",
    re.IGNORECASE,
)

FINAL_ARTWORK_SELECTED_IMAGE_CONTEXT_KEYS = (
    "selected_images",
    "selected_image_assets",
    "selected_assets",
    "supplied_images",
    "supplied_image_assets",
    "reference_images",
    "image_assets",
)
FINAL_ARTWORK_PRINCIPAL_HUMAN_CONTEXT_KEYS = (
    "principal_subjects",
    "principal_athletes",
    "principal_players",
    "principal_human_subjects",
    "heroes",
    "athletes",
    "players",
    "drivers",
    "fighters",
)
FINAL_ARTWORK_HUMAN_ASSET_ROLES = {
    "action",
    "action_image",
    "athlete",
    "body_uniform",
    "driver",
    "fighter",
    "full_body",
    "hero",
    "hero_image",
    "player",
    "player_image",
    "principal_subject",
    "subject",
    "subject_image",
}
FINAL_ARTWORK_NON_NAME_WORDS = {
    "artwork",
    "border",
    "cave",
    "cinematic",
    "collector",
    "composition",
    "design",
    "edition",
    "final",
    "gold",
    "limited",
    "minimal",
    "minimalist",
    "premium",
    "realistic",
    "sports",
    "style",
    "styled",
    "thin",
}


UPGRADE_EXISTING_DESIGN_VIDEO_URL = (
    "https://cdn.shopify.com/videos/c/o/v/67bad26ad6f24cca9527772f226b5320.mp4"
)


UPGRADE_EXISTING_DESIGN_PROMPT = """
turn this Sports Cave piece into a premium Sports Cave collector-style limited-edition artwork.

Use the uploaded Sports Cave design as the core idea and starting point, but do not feel locked into the old layout, old typography, old title treatment, or old border treatment if they are not premium enough.

Important:
Inside this Sports Cave Designs project/folder, there are project source files called Sports Cave limited edition plaque, including files such as:
- limited-edition-plaque.psd
- limited-edition-plaque.png

When designing, look in the project sources of this project and use the Sports Cave limited edition plaque as the badge/plaque element inside the final design.

Place that plaque in the best possible spot so the final artwork feels genuinely limited edition, collectible, premium, and framed-first.

Do not simply clean up the design.
Do not make it look like a normal poster.
Do not make it look like a social media graphic.

Transform it into a premium limited-edition framed sports collectible built around nostalgia, identity, legacy, rivalry, emotion, and ownership.

The final artwork must feel like something a fan proudly hangs in a man cave, home bar, office, games room, living room, bedroom, or sports room.

MANDATORY OUTPUT FORMAT

Create the artwork in landscape 4:3 ratio.

The design must feel:

Premium
Cinematic
Emotional
Nostalgic
Collector-focused
Masculine
Limited edition
Framed-first
Wall-worthy
Timeless
Realistic
Print-ready

The final reaction should be:

"I need that on my wall."

Not:

"That's a nice poster."

STEP 1 - UNDERSTAND THE CURRENT DESIGN

First, study the uploaded design carefully.

Identify:

The athlete, team, car, rivalry, moment, quote, championship, or emotional idea
The main subject or subjects
The sport and era
The existing title and text
The strongest emotional hook
What the design is trying to make fans feel
What is weak, cheap, cluttered, unrealistic, or not collector-worthy

Keep the core idea, but upgrade the execution to Sports Cave premium collector standard.

STEP 2 - RESEARCH BETTER REALISTIC REFERENCES

Use web/image search to identify the real athlete, team, car, moment, rivalry, or event shown in the current design.

Search for better, more realistic visual references of:

The athlete or athletes
The exact sporting moment
The celebration or pose
The car, race, jersey, kit, uniform, gloves, trophy, stadium, arena, track, or scene
The correct era and visual details
Any authentic signature references if appropriate

Use the searched images as factual realism and accuracy references for the surrounding design, background, era, venue, lighting and details.
If a real subject image has been supplied, do not use references to replace, redraw, re-pose, face-swap or reinterpret that subject.

Do not blindly copy a random photo.
Use the best references to improve background believability, lighting integration, jersey or vehicle factual accuracy, era detail, venue accuracy, and emotional authenticity without changing any supplied principal subject.

If the uploaded design already has a strong supplied real subject pose, preserve that subject, pose and emotion, then rebuild only the generated Sports Cave environment and collector design elements around it.

STEP 3 - FIND THE EMOTIONAL HOOK

Before designing, choose the strongest selling emotion.

The design must trigger at least one of these:

Legend
Rivalry
Championship memory
Career-defining moment
National pride
Club/team identity
Era nostalgia
Childhood memory
Greatness
Legacy
Tribute
Ownership
Man cave pride

Ask:

Why does this moment matter?
What memory does it unlock?
Why would a fan proudly display this?
Why would someone fear missing out once the edition sells out?

Build the artwork around that answer.

STEP 4 - SPORTS CAVE VISUAL STYLE

Use a dark cinematic foundation:

Deep black
Charcoal
Smoke
Stadium darkness
Arena shadows
Garage shadows
Track grit
Historic textures
Vintage atmosphere
Warm cinematic light
Subtle dust particles
Soft light rays
Strong shadow depth

The artwork should feel expensive before it is even framed.

Use gold sparingly as a premium accent only.

Good gold use:

Title accents
Thin dividers
Small border details
Edition plaque
Collector details
Subtle highlights
Signature glow
Small typography accents

Do not flood the artwork with gold.
Gold should feel rare, premium, and intentional.

Avoid bright random colours unless they are part of the team, jersey, car, nation, or moment.

STEP 5 - COMPOSITION RULES

The subject must always be the hero.

Use strong negative space.
Keep the layout clean.
Make it readable as a Shopify thumbnail.
Make it powerful as a framed wall artwork.
Make it premium in a black frame.

Do not overcrowd the design with too many athletes, trophies, logos, badges, quotes, stats, or effects.

The composition should feel cinematic, not busy.

Use depth:

Foreground subject
Atmospheric background
Soft stadium/arena/track glow
Subtle texture
Premium title placement
Integrated collector plaque

Every element must earn its place.

STEP 6 - SPORT-SPECIFIC BACKGROUND DIRECTION

Choose the background based on the sport.

NBA:
Dark arena atmosphere, tunnel lighting, court reflections, crowd glow, smoke, legacy portrait mood, championship spotlight.

Football/Soccer:
Stadium lights, trophy atmosphere, pitch glow, national pride, crowd energy, dramatic night-match lighting.

AFL/NRL:
Floodlights, turf texture, club identity, rivalry tension, old-school stadium emotion.

Cricket:
MCG-style atmosphere, pitch texture, sunset, test-match nostalgia, crowd lights, historic cricket mood.

Motorsport:
Track environment, Bathurst-style mountain roads, pit lane, garage shadows, smoke, vintage grit, golden-hour racing atmosphere.

Boxing/UFC:
Ring lighting, harsh shadows, sweat, black-and-white grit, dramatic spotlights, intensity, legacy quote energy.

Horse Racing:
Track dust, grandstand atmosphere, racing silks, golden prestige, championship heritage.

Tennis/Golf:
Premium club atmosphere, clean luxury, championship heritage, controlled lighting, elegant composition.

The background must support the story without distracting from the subject.

STEP 7 - TITLE SYSTEM

Do not keep the existing title just because it is already in the design.

The title should be upgraded according to the stronger concept, stronger emotional hook, and premium collector direction of the new design.

If the old title is weak, generic, poorly worded, too basic, or not collector-worthy, replace it.

Use the title that best fits the upgraded design direction, not the original design by default.

The title must be short, emotional, memorable, and powerful.

Good title style examples:

The King of Spin
The Rivals
The Mentality
The Last Shot
The Final Crown
Legends Never Die
Built For Greatness
One-Two Finish
Six Laps Ahead
The Champion's Walk
The King Of The Mountain
The Moment That Made Him
For Brock
The City Waited

Avoid generic titles like:

Sports Poster
Player Wall Art
Premium Print
Motivational Artwork
Greatest Ever
Legend Design

The title must create the story.

Use elegant serif or cinematic typography.
Use uppercase tracking where appropriate.
Keep text minimal.
Do not make the artwork look like an advertisement.

STEP 8 - LIMITED EDITION PLAQUE SYSTEM

Use the Sports Cave limited edition plaque from the project sources in the Sports Cave Designs folder.

This is not optional.
Use it as the badge/plaque element in the final design.

Possible source files include:
- limited-edition-plaque.psd
- limited-edition-plaque.png

Place the plaque in the best natural location for this specific composition.

The plaque must blend naturally into the artwork and never overpower the design.

It should feel like a real memorabilia plate, gallery stamp, or collector edition marker.

The plaque should enhance collectibility without becoming the focal point.

Make it sharp, realistic, readable, premium, and properly lit.

Strong placement options:

Bottom left
Bottom centre
Bottom right
Near the title
Integrated into a collector plate zone
Subtle plaque area in darker negative space

Do not place the plaque randomly.
Do not make it look pasted on.
Do not make it too large.
Do not hide it so much that it loses collector value.

STEP 9 - BORDER SYSTEM

Upgrade the border treatment so it feels more elegant and more Sports Cave.

Important border direction:
Make the border longer horizontally and slightly less tall vertically so it feels more rectangular and refined.

The border must feel:

Elegant
Premium
Collector-style
Sports Cave branded in feel
Balanced
Subtle
Clean
Not bulky
Not cheap
Not overly decorative

Use a refined Sports Cave style border with controlled gold detailing if needed.

The border should help frame the artwork and elevate the premium collector look, not distract from the subject.

Avoid:
Thick clunky borders
Cheap poster-style frames
Overly ornate decorative borders
Square-looking heavy border shapes
Anything that feels generic or templated

The border should feel sleek, tasteful, and purpose-built for a premium limited-edition Sports Cave artwork.

STEP 10 - SIGNATURE SYSTEM

Where appropriate, include only a valid authentic signature asset supplied by the user or retrieved through the Find Images workflow.

Only use an authentic supplied or selected signature asset if it improves the memorabilia feeling.

Place it naturally in:

Dark sky
Background shadows
Near the title
Near the subject
Near the collector plaque
Empty negative space

The authentic signature asset should feel subtle and premium.

Do not make it oversized.
Do not put it in a box unless it looks like part of a premium memorabilia plate.
Do not invent, imitate, redraw, trace, font-set or regenerate a signature.
If no valid authentic signature asset is available, omit signatures entirely.

STEP 11 - REALISM RULES

Prioritise realism above everything.

Avoid:

AI faces
Warped hands
Distorted bodies
Floating feet
Fake shadows
Random logos
Unreadable text
Messy typography
Cartoon rendering
Plastic skin
Overdone glow
Pasted-on cutout subjects
Incorrect jerseys, kits, cars, trophies, or eras

Requirements:

Natural blending
Correct lighting
Proper contact shadows
Realistic textures
Accurate facial likeness
Realistic body proportions
Sharp print-ready details
No messy text
No fake-looking elements
No awkward cropping
No stretched or distorted subjects

The subject must feel physically present in the scene.

STEP 12 - UPGRADE THE EXISTING DESIGN

Keep the strongest parts of the uploaded design:

The core subject
The emotional idea
The sport and era
The key fan memory
The collector direction

Only keep the existing title if it is already genuinely strong enough for the upgraded premium concept.
Otherwise replace it with a stronger, more collector-worthy title.

Upgrade the weak parts:

Improve realism
Improve lighting
Improve depth
Improve typography
Improve background atmosphere
Improve composition
Improve plaque integration
Improve border elegance
Make the border longer horizontally and slightly shorter vertically so it feels more rectangular and premium
Improve premium black-and-gold collector feeling
Remove clutter
Remove cheap poster-shop elements
Remove social-media-style layout
Remove anything that does not increase emotion, collectibility, or wall appeal

The final should feel like a Sports Cave premium limited-edition drop, not just a redesigned poster.

STEP 13 - FINAL BESTSELLER CHECKLIST

Before finalising, make sure the artwork passes this checklist:

Does it trigger nostalgia?
Does it celebrate a legend, rivalry, team, championship, or iconic moment?
Does it feel emotional?
Does it feel premium?
Does it feel collectible?
Does it work in black and gold?
Is the title powerful and upgraded where needed?
Is the Sports Cave limited-edition plaque properly used?
Is the border elegant, longer horizontally, and slightly less tall vertically?
Is the subject realistic?
Is the lighting cinematic?
Does it look print-ready?
Would it look incredible framed?
Would it stand out as a Shopify thumbnail?
Would a fan proudly display it?
Does it feel Sports Cave?
Does it make the fan think, "I need that on my wall"?

FINAL OUTPUT STANDARD

Create a premium 4:3 landscape Sports Cave collector artwork.

Use the uploaded design as the core reference, preserve every supplied principal subject unchanged, and rebuild the surrounding Sports Cave collector environment into a darker, more cinematic, more realistic, more emotional, more premium limited-edition piece.

Use factual reference images from web/image search only for background adaptation, lighting, era detail, venue accuracy and collector atmosphere where needed.

Make the subject heroic.
Make the background atmospheric.
Make the title stronger where needed.
Use the Sports Cave limited edition plaque from the project sources as the badge/plaque element.
Make the border more elegant, more Sports Cave styled, longer horizontally, and slightly less tall vertically.
Make the whole design feel framed-first and wall-worthy.

This must look like:

A premium framed collector piece
A tribute to sporting greatness
A limited-edition drop
A man cave centrepiece
A piece of sporting history

The final artwork must feel like Sports Cave:

Premium limited-edition sports wall art for fans who collect moments, not posters.
"""


DESIGN_RESEARCH_PROMPT_TEMPLATE = """
TASK TO RESEARCH

[PASTED TASK]

You are the dedicated Sports Cave sports-product researcher and premium collector-art creative director.

Use current web research to choose one strongest commercial concept and guide the next image-search stage. Do not find or display images yet. Do not generate artwork. Do not return a long list of equal options.

Return this concise handoff:
1. Recommended defining moment, season, rivalry or identity
2. Why fans would buy that moment
3. Final photo brief for each principal: chest-up, waist-up or three-quarter crop; expression and emotional tone; required uniform, number, equipment and era; viewing angle; primary or secondary asset role; minimum useful resolution after cropping; details that must remain visible; and distant or unsuitable full-body treatments to reject
4. Exact era, uniform, equipment, vehicle and venue requirements
5. Recommended hero image type and pose
6. One optional supporting image or background reference
7. Minimal background direction
8. Exact full principal names requiring signatures
9. Three focused image-search phrases per principal
10. One fallback moment if preferred photography is unavailable

For rivalry or group designs, choose photographs that can coexist naturally in one restrained Sports Cave composition. The direction must feel premium, realistic, minimal, dark, framed-first and collector-driven.
"""


DESIGN_IMAGE_CAROUSEL_PROMPT_TEMPLATE = """
Use the immediately preceding Research response. Do not repeat or redo research. Find and display the images only.
"""


DESIGN_GENERATION_PROMPT_TEMPLATE = """
From the research and images above, create a premium Sports Cave limited-edition collector artwork for this task:

TASK:
[PASTED TASK]

Reference roles:
- Hero image: immutable principal subject asset to isolate and composite unchanged. Composite the original supplied subject unchanged into the generated Sports Cave environment.
- Additional subject images: immutable subject assets only when they are meant to appear in the final artwork.
- Background/support image: atmosphere, venue and story reference that may be adapted or regenerated around the preserved subject.
- Detail references: factual accuracy references only unless specifically selected as visible subjects.
- Limited-edition plaque: exact supplied graphic asset to composite, not regenerate.

Use the Sports Cave limited-edition plaque attached to this project and integrate it naturally.

Create the artwork in landscape 4:3 ratio.

This must feel like premium limited-edition sports wall art for fans who collect moments, not posters.

The artwork must feel:
Premium
Cinematic
Realistic
Nostalgic
Emotional
Collector-focused
Masculine
Limited edition
Framed-first
Wall-worthy
Timeless
Print-ready

The final reaction should be:
"I need that on my wall."

Core emotional hook:
Build the design around legend + moment + nostalgia + darkness + subtle gold + framed collector energy.
The design must instantly answer:
Why does this moment matter?
What memory does it unlock?
Why would a real fan proudly hang this?

Realism and reference accuracy lock:
Use the selected images as strict source assets and factual references according to their roles above.
Preserve supplied principal subjects exactly: facial features, age, expression, body shape, pose, kit, jersey, car body, livery, colours, trophy shape, equipment, stadium, track, era, and lighting direction.
Do not redesign the athlete, driver, car, uniform, trophy, venue, or moment.
Do not make the subject look AI-generated, plastic, cartoon, generic, over-smoothed, or fake.
Do not warp faces, hands, limbs, bodies, wheels, cars, numbers, text, plaques, logos, or uniforms.
Do not mirror images if it reverses numbers, logos, sponsor text, or kit details.
Do not mix different eras, teams, cars, trophies, uniforms, liveries, or venues.
Subjects must feel physically present with correct shadows, contact, perspective, texture, and depth.

Sports Cave collector style:
Use a dark cinematic foundation:
deep black, charcoal, smoke, stadium shadows, arena darkness, garage shadows, vintage grit, track dust, or warm spotlight atmosphere.

Use gold sparingly only for premium emphasis:
title accents, thin dividers, plaque detail, edition number, small collector details, subtle highlights.

Do not flood the design with gold.

Composition:
The subject must be the hero.
Use strong negative space.
Keep the layout clean and intentional.
Make it readable as a Shopify thumbnail.
Make it look powerful inside a black frame.
Avoid clutter, giant logos, excessive text, fake badges, random effects, fireworks, cheap glows, or social media graphic energy.

Title:
Use a short, powerful, cinematic collector title based on the research.
The title should feel like a movie title or legendary chapter, not a product name.
Use elegant serif or cinematic uppercase typography.
Keep text minimal and premium.
Do not make it look like an ad.

Limited-edition plaque:
Use the attached Sports Cave plaque as a real collector plate.
Place it where it improves the artwork most: bottom left, bottom centre, bottom right, near the title, or in darker negative space.
It must be readable, sharp, subtle, premium, properly lit, and integrated naturally.
It must never overpower the subject.

Sport-specific atmosphere:
If NBA: dark arena, court glow, crowd energy, championship spotlight.
If football/soccer: stadium lights, pitch glow, trophy atmosphere, national or club pride.
If AFL/NRL: floodlights, turf texture, rivalry tension, old-school stadium emotion.
If cricket: MCG-style atmosphere, pitch texture, sunset, test-match nostalgia.
If motorsport: realistic race cars, track banking, pit lane, garage shadows, sparks, smoke, asphalt texture, golden-hour or night-race pressure.
If boxing/UFC: ring lighting, harsh shadows, sweat, black-and-white grit, dramatic spotlights.
If horse racing: track dust, grandstand atmosphere, prestige, championship heritage.
If tennis/golf: clean luxury, championship heritage, controlled lighting, premium club atmosphere.

Final output standard:
A premium 4:3 landscape Sports Cave limited-edition collector artwork.
It should feel like:
A framed collector piece
A tribute to sporting greatness
A limited-edition drop
A man cave centrepiece
A piece of sporting history

Do not stop at "good enough."
Refine toward realism, emotion, collectibility, and wall-worthy bestseller potential.
"""


SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER = "SPORTS CAVE FINAL ARTWORK MASTER PROMPT V2"
SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT = f"""
{SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT_MARKER}

Create a premium Sports Cave limited-edition collector artwork using the task variables and all supplied reference images.

TASK:
[PASTED TASK]

Use every image according to its correct role. Composite each selected final-use photograph as the immutable source asset. Never redraw, regenerate, face-swap, re-pose, rebuild, extend with invented limbs, or approximate a person, vehicle, uniform, trophy or historical moment. Preserve faces, expressions, bodies, uniforms, jersey numbers, equipment, vehicle liveries, perspective and photographic texture.

Every named principal in the asset/name mapping below must have the correctly spelled full name visibly designed into the finished artwork. Do not rely on a jersey name, title word or background text as the only identification.

Use each verified authentic signature asset exactly as provided and place it subtly beside the correct person or nearby clean negative space. Never type, generate, rewrite, redraw or imitate a signature. If no verified signature exists for a named human principal, make the missing signature explicit and do not pretend the artwork is final.

Use the exact Sports Cave limited-edition plaque asset from the mapping below whenever available. Never invent, redraw, retype or approximate the plaque, seal, wording or edition number.

Build around one clear hero or a controlled rivalry/group composition. Use a minimal deep black/charcoal foundation, restrained team colours, small warm-gold collector details, premium typography, subtle relevant venue or era texture, strong negative space and a thin border fully inside the 4:3 landscape canvas.

Do not add generated players, recognisable crowd figures, random logos, oversized text, excessive smoke or generic clutter. Keep every subject, name, signature, plaque, title, effect and border detail fully inside the safe area.

The finished artwork must feel like premium Sports Cave limited-edition wall art from the same commercial family as the best sellers: realistic, nostalgic, disciplined, framed-first, print-ready and sellable.
"""


SPORTS_CAVE_MASTER_DESIGN_SYSTEM_PROMPT = """
Your best sellers are not your cleanest designs.

They are your most emotionally loaded designs.

The common thread is not "perfect graphic design." It is:

legend + moment + nostalgia + darkness + gold + framed collector energy.

That is what works.

The winners all feel like something a fan would buy because it reminds them who they are.

Not because the design is technically perfect.

Common theme across your best sellers
1. They are mostly legends, rivals, or identity pieces

Warne. Brock. Jordan. Kobe. Messi. Ronaldo. Ali.

These are not random athletes. They carry memory.

The best sellers trigger one of these emotions:

"I remember that era."
"That was my hero."
"That belongs in my man cave."
"That's greatness."
"That's part of my childhood."

That is the Sports Cave money zone.

2. Dark cinematic background

Most winners use:

black
charcoal
shadow
smoke
stadium lighting
garage lighting
vintage grit

This makes them feel more like collectibles and less like posters.

3. Gold typography and gold detail

The gold works because it signals:

limited edition
premium
legacy
collector value

But it works best when used lightly. The best designs are not flooded with gold. They use gold as the "premium stamp."

4. Strong title line

The best ones have a title that feels like a movie poster:

The King of Spin
The Rivals
The Mentality
Legends Never Die
The Final Crown
Six Laps Ahead
One-Two Finish

This is massive. The title does more selling than the design sometimes.

5. Limited edition plaque/stamp

The plaque gives the artwork a reason to feel collectible. It turns "sports poster" into "edition."

This is important for where Sports Cave is heading.

6. The artwork feels framed-first

The designs work because they look like they were made to sit inside a black frame. They are not social media graphics. They are wall pieces.

That is the key distinction.

Direction Sports Cave should move toward

Sports Cave should become:

Premium limited-edition sports wall art for fans who collect moments, not posters.

Not cheap posters.
Not random player edits.
Not overdesigned AI art.

The brand should own:

legendary moments
rivalries
career-defining quotes
stadium nostalgia
black-and-gold collector styling
numbered limited runs
man cave identity

That is your lane.

Sports Cave Master Design System Prompt

You are the dedicated Sports Cave premium sports artwork designer.

Sports Cave creates premium limited-edition sports wall art for passionate fans, collectors, man caves, offices, home bars, and gifting. Every design must feel like a framed collector piece, not a social media graphic.

The goal of every artwork is to have bestseller potential.

You are not just creating a poster.
You are creating nostalgia, identity, legacy, rivalry, and ownership.

Core Sports Cave Design Direction

Every Sports Cave design must feel:

premium
cinematic
collector-driven
nostalgic
emotional
masculine
wall-worthy
framed-first
limited edition

The artwork should feel like something a real fan would proudly hang in their home, not something they would scroll past online.

Proven Bestseller Formula

Every design should be built around at least one of these emotional triggers:

Legendary athlete tribute
Iconic sporting moment
Famous rivalry
Career-defining quote
National pride
Club/team identity
Era nostalgia
Championship memory
Man cave status piece
"I remember watching this" emotion

The design must instantly answer:

Why does this matter to a fan?
What memory does it unlock?
Why would someone want this on their wall?

Visual Style Rules

Use a dark, premium foundation:

deep black
charcoal
smoke
stadium shadows
garage shadows
vintage sports atmosphere
warm cinematic lighting

Use Sports Cave gold only as a premium accent:

title detail
thin borders
small dividers
plaque
edition number
signature detail
subtle badge

Gold must feel rare and intentional. Do not overuse it.

Avoid bright, cheap, poster-shop colour unless the athlete, car, team, or moment requires it.

The artwork should look expensive even before it is placed in a frame.

Composition Rules

Design in landscape format by default.

The subject should be the hero.

Use strong negative space where possible.

Keep the layout clean and cinematic.

Do not overcrowd with too many athletes, stats, badges, logos, or text.

The design must still be readable and powerful as a Shopify product thumbnail.

The artwork should work inside a black frame.

Always think:

Would this look premium on a wall?
Would this stop a fan and make them feel something?
Would this still look good in a framed mockup?

Title System

Every artwork needs a strong collector-style title.

The title should feel like a movie title or legendary chapter, not a product name.

Examples of the right direction:

The King of Spin
The Rivals
The Mentality
Legends Never Die
The Final Crown
Six Laps Ahead
One-Two Finish
The Last Shot
The Champion's Walk
Built for Greatness
The Moment That Made Him
The King of the Mountain

Keep titles short, emotional, and memorable.

Avoid generic titles like:

Player Wall Art
Sports Poster
Premium Print
Motivational Artwork
Greatest Ever Design

The title should create story.

Typography Rules

Use elegant serif or strong cinematic fonts for main titles.

Use small uppercase tracking for collector details.

Use gold for title accents, not huge blocks of text.

Text must feel premium, controlled, and minimal.

Never add too much copy inside the artwork.

The design should not feel like an ad.

Limited Edition Plaque System

Use the Sports Cave limited edition plaque or badge as a consistent collector element.

The plaque should be subtle, premium, and integrated into the artwork.

It can appear:

bottom left
bottom centre
bottom right
inside a small title plate
near the signature area

The plaque should include:

LIMITED EDITION
No. 001 / 100
Sports Cave Collector Series mark where appropriate

The plaque must never overpower the artwork.

It should feel like a gallery stamp or memorabilia detail.

Authentic Signature and Memorabilia Feel

Where suitable, include only a valid authentic signature asset supplied by the user or retrieved through the Find Images workflow.

The authentic signature asset should feel like memorabilia, not decoration.

Place it in a natural empty area:

sky
dark background
near the subject
near the title

Do not make it too large or distracting.
Do not invent, imitate, redraw, trace, font-set or regenerate a signature.
If no valid authentic signature asset is available, omit signatures entirely.

Background Rules

Use backgrounds that add emotion and context:

stadiums
arenas
race tracks
garages
boxing rings
locker rooms
crowd lights
dust
smoke
sunset
spotlights
historic textures
vintage sports scenery

The background should support the story, not compete with the subject.

For cricket, use stadium or pitch atmosphere.
For motorsport, use track, garage, road, smoke, or vintage race setting.
For NBA, use arena darkness, court lights, tunnel energy, or legacy portrait mood.
For football, use stadium atmosphere, national pride, trophy moments, or dramatic pitch lighting.
For combat sports, use ring lighting, black-and-white grit, sweat, quote energy, and shadow.

Realism Rules

Prioritise realism.

Subjects must look grounded, naturally blended, and believable.

Avoid obvious AI errors:

floating feet
warped hands
fake faces
distorted bodies
random logos
messy text
unreadable plaques
overdone glow
cartoonish rendering

Lighting must match the scene.

Feet, cars, bodies, and objects must have proper contact shadows.

The artwork must feel print-ready and professional.

Bestseller Design Checklist

Before finalising any design, check:

Does it trigger nostalgia?
Does it celebrate a legend, rivalry, or moment?
Does it look premium in black and gold?
Does it feel like a limited edition collector piece?
Is the title strong enough to sell the story?
Is the plaque subtle but visible?
Would it look good framed on a wall?
Would a fan feel proud owning it?
Is it readable as a Shopify thumbnail?
Is there too much text?
Is the subject grounded and realistic?
Does it feel Sports Cave, not generic poster shop?

What To Avoid

Do not make designs look like social media banners.

Do not use excessive text.

Do not make the artwork too clean, flat, or corporate.

Do not use cheap discount-style design elements.

Do not add random bright colours unless they support the sport or story.

Do not overuse logos or badges.

Do not make the limited edition plaque huge.

Do not make the artwork look like a certificate.

Do not sacrifice emotion for polish.

Do not over-modernise designs that already have nostalgia power.

Sports Cave Bestseller Creative Formula

Use this structure when creating a new design:

Choose the emotional hook
Legend, rivalry, quote, moment, championship, national pride, or nostalgia.
Choose the hero subject
One powerful athlete, car, rivalry pair, or moment.
Build the environment
Stadium, track, arena, ring, garage, court, or historic atmosphere.
Add cinematic lighting
Gold light, spotlight, smoke, shadow, sunset, or dramatic contrast.
Add collector identity
Title, limited edition plaque, subtle signature, small Sports Cave mark.
Keep it clean
Remove anything that does not increase emotion, collectibility, or wall appeal.
Final Output Standard

Every final Sports Cave design should feel like:

a premium framed collector piece
a tribute to a sporting memory
a man cave centrepiece
a limited edition drop
a product fans fear missing out on

The design should make the fan think:

"I need that on my wall."

Not:

"That looks like a poster."

Default Style Summary

Dark cinematic sports tribute artwork.
Premium black and gold collector style.
Strong title.
Subtle limited edition plaque.
Realistic subject.
Emotional nostalgia.
Framed-first composition.
Built for Sports Cave best seller potential.
"""


EXPIRED_EDITION_NEXT_CHAPTER_DESIGN_PROMPT = (
    EXPIRED_EDITION_NEXT_CHAPTER_PROMPT_PATH.read_text(encoding="utf-8").strip()
    if EXPIRED_EDITION_NEXT_CHAPTER_PROMPT_PATH.exists()
    else "SPORTS CAVE EXPIRED EDITION / NEXT CHAPTER DESIGN PROMPT"
)


FIND_THE_MOMENT_PROMPT = """
I am creating a premium limited-edition Sports Cave collector artwork for [PLAYER / TEAM / RIVALRY / MOMENT].

Your job is to research and identify the strongest possible iconic moment or image direction to use for this design.

Do not give generic suggestions.
Do not choose the most famous moment only because it is famous.
Choose the moment with the strongest emotional pull, nostalgia, fan recognition, wall-art potential, and commercial chance of selling as a premium framed collector piece.

Think like:

A sports fan
A collector
A buyer
A brand strategist
A premium sports art director

Please give me:

1. The top 5 most iconic moments or image directions for [PLAYER / TEAM / RIVALRY / MOMENT]

2. Which ONE moment is strongest for a premium Sports Cave collector design

3. Why that moment is strongest emotionally and commercially

4. The best hero image direction:
   - celebration
   - action shot
   - portrait
   - trophy lift
   - signature pose
   - rivalry image
   - race/car shot
   - team celebration
   - championship moment

5. The best supporting background image direction:
   - stadium
   - arena
   - crowd
   - trophy
   - scoreboard
   - track
   - pit lane
   - court
   - pitch
   - historic venue
   - team colours
   - race car
   - iconic setting

6. Specific search terms I should use in Google Images, Getty Images, or ChatGPT image search to find:
   - the best hero image
   - the best background/support image
   - accurate jersey, kit, car, trophy, venue, or era details
   - authentic signature reference if appropriate

7. Any details fans would instantly recognise:
   - stadium
   - crowd
   - trophy
   - scoreboard
   - jersey
   - kit
   - car
   - race number
   - rival
   - team colours
   - year
   - venue
   - historic context

8. A premium Sports Cave title direction.
Give me 5 short title options that feel emotional, cinematic, collector-worthy, and sellable.

9. A short recommendation on how this should be positioned as a Sports Cave limited-edition collector piece.

10. A final creative brief I can use to create the artwork.

Important:
The design must feel premium, dark, cinematic, nostalgic, collector-focused, realistic, limited-edition, and framed-first.

Golden rule:
Do not design first and think later.
The winning design starts with the right moment.
"""


CREATE_SPORTS_CAVE_STYLE_ARTWORK_PROMPT = """
Use the images above found and uploaded to create a premium Sports Cave style limited-edition collector artwork.

Use the selected hero image as the immutable principal subject asset. Composite the original supplied subject unchanged into the generated Sports Cave environment.
Use additional subject images as immutable subject assets only when they are meant to appear in the final artwork.
Use the selected background/support image as the atmosphere and story reference that may be adapted or regenerated around the preserved subject.
Use detail references only as factual accuracy references unless specifically selected as visible subjects.
Use the Sports Cave limited-edition plaque attached to this project and place it in the best possible location in the design.

Create the artwork in landscape 4:3 ratio.

The artwork must feel like a premium framed collector piece, not a normal sports poster.

It must feel:

Premium
Cinematic
Realistic
Nostalgic
Emotional
Collector-focused
Masculine
Limited edition
Framed-first
Wall-worthy
Timeless
Print-ready

The final reaction should be:

"I need that on my wall."

Use the creative direction from the previous research:

Moment:
[PASTE SELECTED MOMENT]

Hero subject:
[PASTE HERO IMAGE DIRECTION]

Background/support:
[PASTE BACKGROUND IMAGE DIRECTION]

Title:
[PASTE SELECTED TITLE]

Emotional hook:
[PASTE WHY THIS MOMENT MATTERS]

Design the piece in true Sports Cave collector style:

Dark cinematic foundation
Deep black and charcoal atmosphere
Premium warm lighting
Subtle gold accents only
Realistic hero subject
Atmospheric background depth
Strong negative space
Clean premium typography
Limited-edition plaque integrated naturally
No clutter
No cheap effects
No social media graphic energy
No random logos
No messy text
No fake-looking AI faces
No warped hands or distorted bodies
No incorrect jerseys, kits, cars, trophies, or eras

The subject must be the hero.

The background should support the story without distracting.

The limited-edition plaque must feel like a real collector plate or memorabilia marker.
It should be readable, premium, sharp, subtle, and properly lit.
Place it where it improves the design most:
bottom left, bottom centre, bottom right, near the title, or in darker negative space.

Use gold sparingly for premium emphasis only:
title accents, thin dividers, plaque detail, small collector details, subtle highlights.

Do not flood the artwork with gold.

Typography:
Use a short, powerful, cinematic title.
Make the title feel like a collector piece or film title.
Use elegant serif or cinematic uppercase typography.
Keep text minimal.
Do not make it look like an ad.

Realism:
Prioritise accurate likeness, natural lighting, correct kit/car/venue details, realistic shadows, believable depth, and print-ready sharpness.

Sport-specific mood:
If NBA: dark arena, court glow, crowd energy, championship spotlight.
If football/soccer: stadium lights, pitch glow, trophy atmosphere, national or club pride.
If AFL/NRL: floodlights, turf texture, rivalry tension, old-school stadium emotion.
If cricket: MCG-style atmosphere, pitch texture, sunset, test-match nostalgia.
If motorsport: Bathurst-style mountain roads, pit lane, garage shadows, smoke, vintage grit, golden-hour racing atmosphere.
If boxing/UFC: ring lighting, harsh shadows, sweat, black-and-white grit, dramatic spotlights.
If horse racing: track dust, grandstand atmosphere, prestige, championship heritage.
If tennis/golf: clean luxury, championship heritage, controlled lighting, premium club atmosphere.

Final output standard:
A premium 4:3 landscape Sports Cave limited-edition collector artwork.

It should look like:

A premium framed collector piece
A tribute to sporting greatness
A limited-edition drop
A man cave centrepiece
A piece of sporting history

Make it feel like Sports Cave:

Premium limited-edition sports wall art for fans who collect moments, not posters.
"""


HARSH_REVIEW_PROMPT = f"""
Give me a harsh truth review of this Sports Cave design.

Rate it out of 10 as a premium limited-edition collector artwork.

I want brutal honesty.

Tell me:

1. Every named principal appears with the correct full name
2. Every human principal has the correct verified authentic signature
3. Signatures are correctly mapped, elegant, subtle and not oversized
4. The exact Sports Cave plaque is present, subtle, unchanged and correctly positioned
5. The title and names remain readable at Shopify-thumbnail size
6. Principal subjects remain original photographic assets with no AI reconstruction
7. The background is relevant, restrained and not generic clutter
8. No extra players, generated people or recognisable crowd figures appear
9. The composition feels premium, intentional, framed-first and wall-worthy
10. The smallest exact correction needed to make it sellable

Do not be polite.
Be commercially honest.
Judge it like it needs to become a bestseller.

Rule:
Hard-cap the score at 6/10 if a required principal is too small to recognise at thumbnail size; a distant or full-body source materially weakens the hero treatment; one of two principals is reduced to a minor background element; an unsuitable crop makes the face, jersey or sporting identity unclear; the Find Images response contains only links instead of visible candidates; or any required name, verified signature or exact plaque is missing, fabricated, incorrectly mapped or unreadable.

A premium result that satisfies the full contract and needs only minimal changes may score 10/10. Do not invent trivial faults simply to avoid a high score.

Preserve the existing artwork and recommend the smallest exact crop, proportional scale or positioning edit that makes it premium, emotional, collector-worthy and ready to sell. If the source itself is unsuitable, require replacing only that source photograph through Find Images.

{design_studio_styles.HERO_PHOTOGRAPHIC_DOMINANCE_CONTRACT}
"""


PROMPT_BOXES = {
    "Upgrade Existing Design Prompt": (
        UPGRADE_EXISTING_DESIGN_PROMPT,
        "upgrade-existing-design",
    ),
    "Expired Edition / Next Chapter Design Prompt": (
        EXPIRED_EDITION_NEXT_CHAPTER_DESIGN_PROMPT,
        "expired-edition-next-chapter",
    ),
    "Find The Moment Prompt": (
        FIND_THE_MOMENT_PROMPT,
        "find-the-moment",
    ),
    "Create Sports Cave Style Artwork Prompt": (
        CREATE_SPORTS_CAVE_STYLE_ARTWORK_PROMPT,
        "create-sports-cave-style-artwork",
    ),
    "Harsh Truth Sports Cave Design Review": (
        HARSH_REVIEW_PROMPT,
        "harsh-review",
    ),
}

DESIGN_STUDIO_IMAGE_GENERATION_PROMPT_KEYS = {
    "upgrade-existing-design",
    "expired-edition-next-chapter",
    "create-sports-cave-style-artwork",
}
ORIGINAL_ARTWORK_REALISM_PROMPT_KEYS = DESIGN_STUDIO_IMAGE_GENERATION_PROMPT_KEYS


def _clean_prompt(prompt):
    return textwrap.dedent(prompt).strip()


def design_studio_prompt_has_subject_preservation_lock(prompt_text: str) -> bool:
    return DESIGN_STUDIO_SUBJECT_PRESERVATION_MARKER.casefold() in str(prompt_text or "").casefold()


def design_studio_prompt_has_hero_dominance_and_border_lock(prompt_text: str) -> bool:
    prompt = str(prompt_text or "").casefold()
    return (
        DESIGN_STUDIO_HERO_DOMINANCE_MARKER.casefold() in prompt
        and DESIGN_STUDIO_LIMITED_EDITION_BORDER_MARKER.casefold() in prompt
    )


def design_studio_prompt_has_rivalry_composition_rules(prompt_text: str) -> bool:
    return SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_MARKER.casefold() in str(prompt_text or "").casefold()


def design_studio_prompt_has_signature_image_search_rules(prompt_text: str) -> bool:
    return SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2_MARKER.casefold() in str(
        prompt_text or ""
    ).casefold()


def design_studio_prompt_has_signature_application_rules(prompt_text: str) -> bool:
    return SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_MARKER.casefold() in str(prompt_text or "").casefold()


def design_studio_prompt_has_signature_premium_treatment_rules(prompt_text: str) -> bool:
    return SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_MARKER.casefold() in str(prompt_text or "").casefold()


def _normalise_rivalry_detection_text(value) -> str:
    text = str(value or "").casefold()
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\ufffd", " ")
    return " ".join(text.split())


def _rivalry_structured_value_matches(value) -> bool:
    normalised = _normalise_rivalry_detection_text(value).replace("_", " ")
    structured_values = {
        _normalise_rivalry_detection_text(item).replace("_", " ")
        for item in RIVALRY_STRUCTURED_CONTEXT_VALUES
    }
    return normalised in structured_values


def _rivalry_structured_context_status(value) -> tuple[bool, bool]:
    if isinstance(value, dict):
        has_structured_context = False
        for key, nested_value in value.items():
            if str(key or "") in RIVALRY_STRUCTURED_CONTEXT_KEYS:
                has_structured_context = True
                if _rivalry_structured_value_matches(nested_value):
                    return True, True
            if isinstance(nested_value, (dict, list, tuple, set)):
                nested_has_context, nested_matches = _rivalry_structured_context_status(nested_value)
                has_structured_context = has_structured_context or nested_has_context
                if nested_matches:
                    return True, True
        return has_structured_context, False
    if isinstance(value, (list, tuple, set)):
        has_structured_context = False
        for item in value:
            nested_has_context, nested_matches = _rivalry_structured_context_status(item)
            has_structured_context = has_structured_context or nested_has_context
            if nested_matches:
                return True, True
        return has_structured_context, False
    return False, False


def _iter_rivalry_context_text_values(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            key_text = str(key or "")
            if key_text in RIVALRY_CONTEXT_TEXT_KEYS:
                yield nested_value
            elif isinstance(nested_value, (dict, list, tuple, set)):
                yield from _iter_rivalry_context_text_values(nested_value)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_rivalry_context_text_values(item)
    elif value is not None:
        yield value


def _rivalry_text_matches(value, *, allow_generic_rivalry_word: bool = False) -> bool:
    text = _normalise_rivalry_detection_text(value)
    if not text:
        return False
    if any(re.search(pattern, text) for pattern in RIVALRY_TEXT_PATTERNS):
        return True
    if not allow_generic_rivalry_word:
        return False
    return bool(
        re.search(r"\brivalr(?:y|ies)\b", text)
        or
        re.search(
            r"\brivalr(?:y|ies)\b.{0,64}\b(?:design|artwork|collector|piece|concept|matchup|between|pair)\b",
            text,
        )
        or re.search(
            r"\b(?:design|artwork|collector|piece|concept|matchup|between|pair)\b.{0,64}\brivalr(?:y|ies)\b",
            text,
        )
    )


def design_studio_context_is_rivalry(design_context=None, *, fallback_text: str = "") -> bool:
    if isinstance(design_context, dict):
        has_structured_context, structured_matches = _rivalry_structured_context_status(
            design_context
        )
        if structured_matches:
            return True
        if has_structured_context:
            return False
        context_text = "\n".join(
            str(value) for value in _iter_rivalry_context_text_values(design_context)
        )
        return _rivalry_text_matches(context_text, allow_generic_rivalry_word=True)

    if design_context is not None:
        return _rivalry_text_matches(design_context, allow_generic_rivalry_word=True)

    return _rivalry_text_matches(fallback_text, allow_generic_rivalry_word=False)


def _normalise_signature_subject_name(value) -> str:
    text = " ".join(str(value or "").replace("\u2013", "-").replace("\u2014", "-").split())
    text = text.strip(" \t\r\n-–—:;,.()[]{}")
    text = re.sub(
        r"^(?:create|make|design|build|find|generate|new|premium|minimalist|collector|sports cave)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(
        r"\s+(?:collector|artwork|design|piece|poster|wall art|tribute|edition|signature|asset|reference|prompt|task)$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    if not text:
        return ""
    if text.casefold() in {item.casefold() for item in SIGNATURE_TEXT_SUBJECT_STOPWORDS}:
        return ""
    return text


def _signature_subject_record(name, *, reference: str = "") -> dict:
    clean_name = _normalise_signature_subject_name(name)
    if not clean_name:
        return {}
    return {
        "name": clean_name,
        "reference": str(reference or "").strip(),
    }


def _signature_asset_reference_from_context(value) -> str:
    if not isinstance(value, dict):
        return ""
    for key in SIGNATURE_ASSET_REFERENCE_KEYS:
        candidate = value.get(key)
        if candidate:
            return str(candidate).strip()
    return ""


def _signature_subject_name_from_context(value) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    for key in SIGNATURE_SUBJECT_NAME_KEYS:
        candidate = value.get(key)
        if candidate:
            return str(candidate).strip()
    return ""


def _collect_signature_subject_records_from_context(value) -> list[dict]:
    records = []
    if isinstance(value, dict):
        for key, nested_value in value.items():
            key_text = str(key or "")
            if key_text in SIGNATURE_SUBJECT_CONTEXT_KEYS:
                if isinstance(nested_value, dict):
                    name = _signature_subject_name_from_context(nested_value)
                    record = _signature_subject_record(
                        name,
                        reference=_signature_asset_reference_from_context(nested_value),
                    )
                    if record:
                        records.append(record)
                    else:
                        records.extend(
                            _collect_signature_subject_records_from_context(
                                list(nested_value.values())
                            )
                        )
                elif isinstance(nested_value, (list, tuple, set)):
                    for item in nested_value:
                        if isinstance(item, dict):
                            records.append(
                                _signature_subject_record(
                                    _signature_subject_name_from_context(item),
                                    reference=_signature_asset_reference_from_context(item),
                                )
                            )
                        else:
                            records.append(_signature_subject_record(item))
                else:
                    records.append(_signature_subject_record(nested_value))
            elif isinstance(nested_value, (dict, list, tuple, set)):
                records.extend(_collect_signature_subject_records_from_context(nested_value))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            records.extend(_collect_signature_subject_records_from_context(item))
    return [record for record in records if record]


def _iter_signature_context_text_values(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            key_text = str(key or "")
            if key_text in SIGNATURE_CONTEXT_TEXT_KEYS:
                yield nested_value
            elif isinstance(nested_value, (dict, list, tuple, set)):
                yield from _iter_signature_context_text_values(nested_value)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_signature_context_text_values(item)
    elif value is not None:
        yield value


def _signature_text_is_vehicle_or_venue_only(text: str) -> bool:
    return bool(SIGNATURE_VEHICLE_OR_VENUE_ONLY_PATTERN.search(str(text or "")))


def _signature_subject_records_from_text(text: str) -> list[dict]:
    raw_text = str(text or "")
    if not raw_text.strip() or _signature_text_is_vehicle_or_venue_only(raw_text):
        return []
    candidates = []
    name_pattern = r"[A-Z][A-Za-z'’.-]*(?:\s+[A-Z][A-Za-z'’.-]*){0,3}"
    for match in re.finditer(
        rf"({name_pattern})\s+(?:vs\.?|versus)\s+({name_pattern})",
        raw_text,
    ):
        candidates.extend(match.groups())
    for match in re.finditer(
        rf"\bbetween\s+({name_pattern})\s+and\s+({name_pattern})",
        raw_text,
        flags=re.IGNORECASE,
    ):
        candidates.extend(match.groups())
    if not candidates:
        candidates.extend(
            match.group(1)
            for match in re.finditer(
                r"\b([A-Z][a-z'’.-]+(?:\s+[A-Z][a-z'’.-]+){1,2})\b",
                raw_text,
            )
        )
    return [_signature_subject_record(candidate) for candidate in candidates]


def signature_subject_records_from_context(design_context=None, *, fallback_text: str = "") -> list[dict]:
    records = _collect_signature_subject_records_from_context(design_context)
    if not records and isinstance(design_context, dict):
        records = _signature_subject_records_from_text(
            "\n".join(str(value) for value in _iter_signature_context_text_values(design_context))
        )
    if not records and design_context is not None and not isinstance(design_context, dict):
        records = _signature_subject_records_from_text(str(design_context))
    if not records:
        records = _signature_subject_records_from_text(fallback_text)

    deduped = []
    seen = {}
    for record in records:
        name = _normalise_signature_subject_name(record.get("name"))
        if not name:
            continue
        key = name.casefold()
        reference = str(record.get("reference") or "").strip()
        if key in seen:
            existing = deduped[seen[key]]
            if reference and not existing.get("reference"):
                existing["reference"] = reference
            continue
        seen[key] = len(deduped)
        deduped.append({"name": name, "reference": reference})
    return deduped


def _signature_asset_role_matches(value) -> bool:
    normalised = " ".join(str(value or "").replace("_", " ").replace("-", " ").casefold().split())
    return normalised in {
        " ".join(item.replace("_", " ").replace("-", " ").casefold().split())
        for item in SIGNATURE_ASSET_ROLE_VALUES
    }


def _context_item_is_signature_asset(value) -> bool:
    if not isinstance(value, dict):
        return False
    return any(
        _signature_asset_role_matches(value.get(key))
        for key in SIGNATURE_ASSET_ROLE_KEYS
        if key in value
    )


def _collect_signature_asset_records(value) -> list[dict]:
    records = []
    if isinstance(value, dict):
        record = _signature_subject_record(
            _signature_subject_name_from_context(value),
            reference=_signature_asset_reference_from_context(value),
        )
        if record and record.get("reference"):
            records.append(record)
        for nested_value in value.values():
            if isinstance(nested_value, (dict, list, tuple, set)):
                records.extend(_collect_signature_asset_records(nested_value))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            records.extend(_collect_signature_asset_records(item))
    return records


def verified_signature_asset_records_from_context(design_context=None) -> list[dict]:
    records = []
    if isinstance(design_context, dict):
        if _context_item_is_signature_asset(design_context):
            records.extend(_collect_signature_asset_records(design_context))
        for key, nested_value in design_context.items():
            key_text = str(key or "")
            if key_text in SIGNATURE_VERIFIED_ASSET_CONTEXT_KEYS:
                records.extend(_collect_signature_asset_records(nested_value))
            elif isinstance(nested_value, (dict, list, tuple, set)):
                records.extend(verified_signature_asset_records_from_context(nested_value))
    elif isinstance(design_context, (list, tuple, set)):
        for item in design_context:
            records.extend(verified_signature_asset_records_from_context(item))

    deduped = []
    seen = {}
    for record in records:
        name = _normalise_signature_subject_name(record.get("name"))
        reference = str(record.get("reference") or "").strip()
        if not name or not reference:
            continue
        key = name.casefold()
        if key in seen:
            deduped[seen[key]]["reference"] = reference
            continue
        seen[key] = len(deduped)
        deduped.append({"name": name, "reference": reference})
    return deduped


def _normalise_asset_role(value) -> str:
    return "_".join(
        str(value or "").strip().casefold().replace("-", " ").replace("_", " ").split()
    )


def _selected_image_asset_record(value) -> dict:
    if not isinstance(value, dict):
        return {}
    role = next(
        (
            str(value.get(key) or "").strip()
            for key in SIGNATURE_ASSET_ROLE_KEYS
            if str(value.get(key) or "").strip()
        ),
        "",
    )
    reference = _signature_asset_reference_from_context(value)
    if not role or not reference:
        return {}
    return {
        "reference": reference,
        "role": role,
        "subject_name": _normalise_signature_subject_name(
            _signature_subject_name_from_context(value)
        ),
    }


def selected_image_asset_records_from_context(design_context=None) -> list[dict]:
    records = []

    def collect(value, *, selected_container=False):
        if isinstance(value, dict):
            if selected_container:
                record = _selected_image_asset_record(value)
                if record:
                    records.append(record)
            for key, nested_value in value.items():
                collect(
                    nested_value,
                    selected_container=(
                        selected_container
                        or str(key or "") in FINAL_ARTWORK_SELECTED_IMAGE_CONTEXT_KEYS
                    ),
                )
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                collect(item, selected_container=selected_container)

    collect(design_context)
    deduped = []
    seen = set()
    for record in records:
        key = (
            record["reference"].casefold(),
            _normalise_asset_role(record["role"]),
            record["subject_name"].casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _is_plausible_named_human_subject(value, *, allow_single_name=False) -> bool:
    name = _normalise_signature_subject_name(value)
    if not name or any(character.isdigit() for character in name):
        return False
    words = [word.strip(".'-") for word in name.split() if word.strip(".'-")]
    if not words or (len(words) < 2 and not allow_single_name) or len(words) > 4:
        return False
    if any(word.casefold() in FINAL_ARTWORK_NON_NAME_WORDS for word in words):
        return False
    return all(any(character.isalpha() for character in word) for word in words)


def _collect_principal_human_names_from_context(design_context=None) -> list[str]:
    names = []

    def collect(value):
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if str(key or "") in FINAL_ARTWORK_PRINCIPAL_HUMAN_CONTEXT_KEYS:
                    items = (
                        nested_value
                        if isinstance(nested_value, (list, tuple, set))
                        else [nested_value]
                    )
                    for item in items:
                        candidate = _signature_subject_name_from_context(item)
                        if _is_plausible_named_human_subject(
                            candidate,
                            allow_single_name=True,
                        ):
                            names.append(_normalise_signature_subject_name(candidate))
                elif isinstance(nested_value, (dict, list, tuple, set)):
                    collect(nested_value)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                collect(item)

    collect(design_context)
    for asset in selected_image_asset_records_from_context(design_context):
        if (
            _normalise_asset_role(asset.get("role")) in FINAL_ARTWORK_HUMAN_ASSET_ROLES
            and _is_plausible_named_human_subject(
                asset.get("subject_name"),
                allow_single_name=True,
            )
        ):
            names.append(_normalise_signature_subject_name(asset.get("subject_name")))
    return list(dict.fromkeys(name for name in names if name))


def verified_final_signature_asset_records(task_text: str, *, design_context=None) -> list[dict]:
    verified_records = verified_signature_asset_records_from_context(design_context)
    if not verified_records:
        return []
    principal_names = _collect_principal_human_names_from_context(design_context)
    if not principal_names:
        principal_names = [
            record["name"]
            for record in _signature_subject_records_from_text(task_text)
            if _is_plausible_named_human_subject(record.get("name"))
        ]
    principal_keys = {name.casefold() for name in principal_names}
    return [
        record
        for record in verified_records
        if record["name"].casefold() in principal_keys
        and _is_plausible_named_human_subject(
            record.get("name"),
            allow_single_name=True,
        )
    ]


def build_final_artwork_asset_context(task_text: str, *, design_context=None) -> str:
    assets = selected_image_asset_records_from_context(design_context)
    signatures = verified_final_signature_asset_records(
        task_text,
        design_context=design_context,
    )
    approved_signature_references = {
        record["reference"].casefold() for record in signatures
    }
    assets = [
        asset
        for asset in assets
        if not _signature_asset_role_matches(asset.get("role"))
        or asset["reference"].casefold() in approved_signature_references
    ]
    sections = []
    if assets:
        lines = [
            "SELECTED IMAGE ASSETS AND ROLE METADATA",
            "",
            "Pass and use these actual selected image files as image inputs. Keep each role and subject association unchanged:",
        ]
        for asset in assets:
            subject = (
                f"; subject: {asset['subject_name']}"
                if asset.get("subject_name")
                else ""
            )
            lines.append(
                f"* {asset['reference']} | role: {asset['role']}{subject}"
            )
        sections.append("\n".join(lines))
    if signatures:
        lines = [
            "VERIFIED SIGNATURE ASSET MAPPING",
            "",
            "Only these verified named human subjects may receive signatures:",
        ]
        lines.extend(
            f"* {record['name']} -> {record['reference']}"
            for record in signatures
        )
        sections.append("\n".join(lines))
    principal_names = _collect_principal_human_names_from_context(design_context)
    if not principal_names:
        principal_names = [
            record["name"]
            for record in _signature_subject_records_from_text(task_text)
            if _is_plausible_named_human_subject(record.get("name"))
        ]
    if principal_names:
        lines = [
            "EXACT REQUIRED PRINCIPAL NAMES",
            "",
            "Every listed full name must be visibly designed into the artwork:",
        ]
        lines.extend(f"* {name}" for name in principal_names)
        lines.extend(
            [
                "",
                "For multiple principals, show every full name separately and map each name clearly to the correct person.",
            ]
        )
        sections.append("\n".join(lines))
    else:
        sections.append(
            "EXACT REQUIRED PRINCIPAL NAMES\n\n* No named human principal is supplied. Do not invent player names or signatures."
        )
    plaque_assets = [
        asset
        for asset in assets
        if _normalise_asset_role(asset.get("role")) == "plaque_asset"
    ]
    lines = ["EXACT PLAQUE ASSET MAPPING", ""]
    if plaque_assets:
        lines.extend(
            f"* Sports Cave limited-edition plaque -> {asset['reference']} | role=plaque_asset | use exact asset unchanged"
            for asset in plaque_assets
        )
    else:
        lines.append(
            "* Sports Cave limited-edition plaque -> project source asset limited-edition-plaque.png or limited-edition-plaque.psd when available; if no exact plaque asset is available, do not invent the seal, wording or edition number."
        )
    lines.append(
        "Keep the plaque unchanged, correctly proportioned, inside the safe area and quieter than the title, names and hero photography."
    )
    sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _find_design_context_value(value, keys: tuple[str, ...]):
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if candidate not in (None, "", [], (), {}):
                return candidate
        for nested_value in value.values():
            if isinstance(nested_value, (dict, list, tuple)):
                candidate = _find_design_context_value(nested_value, keys)
                if candidate not in (None, "", [], (), {}):
                    return candidate
    elif isinstance(value, (list, tuple)):
        for item in value:
            candidate = _find_design_context_value(item, keys)
            if candidate not in (None, "", [], (), {}):
                return candidate
    return ""


def _format_find_images_context_value(value, fallback: str) -> str:
    if isinstance(value, dict):
        values = [str(item).strip() for item in value.values() if str(item).strip()]
        return "; ".join(values) if values else fallback
    if isinstance(value, (list, tuple, set)):
        values = []
        for item in value:
            if isinstance(item, dict):
                item = _signature_subject_name_from_context(item) or _find_design_context_value(
                    item,
                    ("title", "name", "label", "value"),
                )
            text = str(item or "").strip()
            if text:
                values.append(text)
        return "; ".join(values) if values else fallback
    text = str(value or "").strip()
    return text if text else fallback


def build_high_quality_image_search_context(
    task_text: str,
    research_answer: str,
    *,
    design_context=None,
) -> str:
    subject_detection_text = "\n".join(
        value
        for value in (str(task_text or "").strip(), str(research_answer or "").strip())
        if value
    )
    records = signature_subject_records_from_context(
        design_context,
        fallback_text=subject_detection_text,
    )
    task = _task_or_placeholder(task_text)
    unavailable = "Use the verified task, research brief and visible chat context."
    variable_specs = (
        ("SPORT", ("sport", "sport_name")),
        ("TEAM / COUNTRY", ("team_country", "team", "club", "country", "nation")),
        ("SEASON / ERA", ("season_era", "season", "era", "year")),
        ("EVENT / MOMENT", ("event_moment", "event", "moment", "match", "race")),
        ("VENUE / LOCATION", ("venue_location", "venue", "location", "stadium", "circuit")),
        (
            "CORRECT UNIFORM / EQUIPMENT DETAILS",
            ("uniform_equipment_details", "uniform", "kit", "equipment", "livery"),
        ),
    )
    title = _find_design_context_value(
        design_context,
        ("design_title", "title", "task", "task_text"),
    ) or task
    research = str(research_answer or "").strip() or (
        "Use the verified research brief already present above in this chat."
    )
    subject_names = [record["name"] for record in records]
    principal_subjects = "; ".join(subject_names) if subject_names else (
        "No named principal human subject detected. Use the verified non-human principal subject from the task and research."
    )

    lines = [
        "TASK-SPECIFIC VARIABLES AND RESEARCH CONTEXT",
        "",
        f"DESIGN TITLE: {_format_find_images_context_value(title, task)}",
        f"RESEARCH BRIEF: {research}",
        f"PRINCIPAL SUBJECTS: {principal_subjects}",
    ]
    for label, keys in variable_specs:
        lines.append(
            f"{label}: {_format_find_images_context_value(_find_design_context_value(design_context, keys), unavailable)}"
        )
    lines.append(
        "OUTPUT IMAGE CAPACITY OR INTERFACE LIMITS: Follow the compact V2 limit: three final-use photographs per principal, no more than one shared reference, and one verified signature candidate per human principal."
    )

    lines.extend(["", "REQUIRED SEARCH AND CAROUSEL EXECUTION PLAN", ""])
    if subject_names:
        for index, name in enumerate(subject_names, start=1):
            lines.append(
                f"{index}. PLAYER - {name}: return only the three strongest final-use photographs for this principal."
            )
        lines.append(
            f"{len(subject_names) + 1}. DESIGN REFERENCES: return no more than one shared moment, venue, background, trophy, equipment or historical-detail reference."
        )
        lines.append(
            f"{len(subject_names) + 2}. SIGNATURES: return exactly {len(subject_names)} signature asset(s), one for each distinct principal person, as the final carousel."
        )
        lines.extend(["", "EXACT SIGNATURE ASSET MAPPING"])
        for name in subject_names:
            lines.append(
                f"* {name} -> authentic signature image; role: signature_asset; "
                f"subject_name: {name}; signature_slot_limit: 1"
            )
    else:
        lines.extend(
            [
                "1. DESIGN REFERENCES: return only the relevant subject, venue, vehicle, equipment and historical-reference carousel(s).",
                "2. Omit PLAYER and SIGNATURES carousels unless the verified research or visible chat context establishes a named principal human subject.",
                "Do not request an irrelevant signature for a vehicle-only, venue-only, trophy-only, jersey-only or team-only design.",
            ]
        )
    return "\n".join(lines)


def build_signature_image_search_context(task_text: str, *, design_context=None) -> str:
    return build_high_quality_image_search_context(
        task_text,
        "",
        design_context=design_context,
    )


def build_signature_asset_mapping_context(prompt_text: str, *, design_context=None) -> str:
    records = signature_subject_records_from_context(
        design_context,
        fallback_text=prompt_text,
    )
    verified_records = verified_signature_asset_records_from_context(design_context)
    verified_reference_by_name = {
        str(record.get("name") or "").casefold(): str(record.get("reference") or "").strip()
        for record in verified_records
        if str(record.get("name") or "").strip() and str(record.get("reference") or "").strip()
    }
    for record in records:
        key = str(record.get("name") or "").casefold()
        record["reference"] = verified_reference_by_name.get(key, "")
    if verified_records:
        record_by_name = {
            str(record.get("name") or "").casefold(): record
            for record in records
            if str(record.get("name") or "").strip()
        }
        for verified_record in verified_records:
            key = str(verified_record.get("name") or "").casefold()
            if key in record_by_name:
                record_by_name[key]["reference"] = verified_reference_by_name.get(key, "")
            else:
                records.append(verified_record)
                record_by_name[key] = verified_record
    lines = [
        "AUTHENTIC SIGNATURE ASSETS",
        "",
        "Use only signature images selected from the Find Images carousel or explicitly supplied by the user.",
        "Map signature_asset images by subject_name to the matching principal subject. Do not rely only on carousel order.",
    ]
    if records:
        lines.extend(["", "Required subject-to-signature mapping:"])
        for record in records:
            name = record["name"]
            reference = record.get("reference") or f"selected signature image reference for {name}"
            lines.append(f"* {name} -> {reference}")
    else:
        lines.extend(
            [
                "",
                "Required subject-to-signature mapping:",
                "* [Principal athlete full name] -> selected signature image reference from the Find Images carousel when a valid authentic signature asset is available",
            ]
        )
    lines.extend(
        [
            "",
            "If a listed subject has no valid authentic signature asset, omit only that signature.",
            "Never invent, approximate, font-set, trace or regenerate a missing signature.",
        ]
    )
    return "\n".join(lines)


def signature_context_has_verified_signature_assets(design_context=None, *, prompt_text: str = "") -> bool:
    if design_studio_prompt_has_signature_premium_treatment_rules(prompt_text):
        return True
    records = verified_signature_asset_records_from_context(design_context)
    return any(str(record.get("reference") or "").strip() for record in records)


def insert_signature_premium_treatment_rules(signature_rules: str) -> str:
    rules = _clean_prompt(signature_rules)
    if design_studio_prompt_has_signature_premium_treatment_rules(rules):
        return rules
    premium_rules = _clean_prompt(SPORTS_CAVE_SIGNATURE_PREMIUM_TREATMENT_RULES)
    placement_heading = "\n\nCOLLECTOR PLACEMENT"
    if placement_heading in rules:
        return rules.replace(placement_heading, f"\n\n{premium_rules}{placement_heading}", 1)
    return f"{rules}\n\n{premium_rules}" if rules else premium_rules


def build_authentic_signature_application_rules(prompt_text: str, *, design_context=None) -> str:
    signature_rules = _clean_prompt(SPORTS_CAVE_AUTHENTIC_SIGNATURE_APPLICATION_RULES_V1)
    if signature_context_has_verified_signature_assets(
        design_context,
        prompt_text=prompt_text,
    ):
        signature_rules = insert_signature_premium_treatment_rules(signature_rules)
    return "\n\n".join(
        section
        for section in (
            signature_rules,
            build_signature_asset_mapping_context(prompt_text, design_context=design_context),
        )
        if str(section or "").strip()
    )


def prepend_design_studio_subject_preservation_lock(prompt_text: str) -> str:
    prompt = _clean_prompt(prompt_text)
    if design_studio_prompt_has_subject_preservation_lock(prompt):
        return prompt
    lock = _clean_prompt(DESIGN_STUDIO_SUBJECT_PRESERVATION_LOCK)
    return f"{lock}\n\n{prompt}" if prompt else lock


def insert_design_studio_rule_after_subject_lock(prompt_text: str, rule_text: str) -> str:
    prompt = prepend_design_studio_subject_preservation_lock(prompt_text)
    rule = _clean_prompt(rule_text)
    subject_lock = _clean_prompt(DESIGN_STUDIO_SUBJECT_PRESERVATION_LOCK)
    if prompt.startswith(subject_lock):
        remaining_prompt = prompt[len(subject_lock) :].lstrip()
        return (
            f"{subject_lock}\n\n{rule}\n\n{remaining_prompt}"
            if remaining_prompt
            else f"{subject_lock}\n\n{rule}"
        )
    return f"{rule}\n\n{prompt}" if prompt else rule


def insert_design_studio_rule_after_rivalry_rules(prompt_text: str, rule_text: str) -> str:
    prompt = prepend_design_studio_subject_preservation_lock(prompt_text)
    rule = _clean_prompt(rule_text)
    rivalry_rules = _clean_prompt(SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_V1)
    if rivalry_rules in prompt:
        before, after = prompt.split(rivalry_rules, 1)
        remaining_prompt = after.lstrip()
        return (
            f"{before}{rivalry_rules}\n\n{rule}\n\n{remaining_prompt}"
            if remaining_prompt
            else f"{before}{rivalry_rules}\n\n{rule}"
        )
    return insert_design_studio_rule_after_subject_lock(prompt, rule)


def adapt_design_studio_prompt_for_rivalry(prompt_text: str) -> str:
    prompt = _clean_prompt(prompt_text)
    replacements = {
        "The subject must always be the hero.": "The two opposing principal subjects must always be co-equal heroes.",
        "The subject must be the hero.": "The two opposing principal subjects must be co-equal heroes.",
        "The subject should be the hero.": "The two opposing principal subjects should be co-equal heroes.",
        "Realistic hero subject": "Realistic co-equal rivalry subjects",
    }
    for original, replacement in replacements.items():
        prompt = prompt.replace(original, replacement)
    return prompt


def adapt_design_studio_prompt_for_authentic_signature_rules(prompt_text: str) -> str:
    prompt = _clean_prompt(prompt_text)
    legacy_signature_style = "signature-" + "style graphic"
    replacements = {
        f"Where appropriate, include a subtle {legacy_signature_style}.": "If valid authentic signature assets are supplied or selected, composite those exact signature assets subtly. If no valid authentic signature asset is available, omit signatures entirely.",
        f"Where suitable, include a subtle {legacy_signature_style}.": "Where suitable, use only a valid authentic supplied or selected signature asset. If no valid authentic signature asset is available, omit signatures entirely.",
        "Only use a signature if it improves the memorabilia feeling.": "Only use an authentic supplied or selected signature asset if it improves the memorabilia feeling.",
        "The signature should feel authentic, subtle, and premium.": "The authentic signature asset should feel subtle and premium.",
        "The signature should feel like memorabilia, not decoration.": "The authentic signature asset should feel like memorabilia, not decoration.",
        "Subtle signature glow": "Subtle glow on an authentic supplied signature asset",
        "signature detail": "authentic supplied signature detail",
    }
    for original, replacement in replacements.items():
        prompt = prompt.replace(original, replacement)
    return prompt


def insert_design_studio_rule_after_existing_block(prompt_text: str, existing_block: str, rule_text: str) -> str:
    prompt = prepend_design_studio_subject_preservation_lock(prompt_text)
    existing = _clean_prompt(existing_block)
    rule = _clean_prompt(rule_text)
    if existing and existing in prompt:
        before, after = prompt.split(existing, 1)
        remaining_prompt = after.lstrip()
        return (
            f"{before}{existing}\n\n{rule}\n\n{remaining_prompt}"
            if remaining_prompt
            else f"{before}{existing}\n\n{rule}"
        )
    return insert_design_studio_rule_after_subject_lock(prompt, rule)


def prepend_design_studio_mandatory_artwork_rules(
    prompt_text: str,
    *,
    include_rivalry_rules: bool = False,
    design_context=None,
) -> str:
    prompt = prepend_design_studio_subject_preservation_lock(prompt_text)

    if include_rivalry_rules and not design_studio_prompt_has_rivalry_composition_rules(prompt):
        prompt = insert_design_studio_rule_after_subject_lock(
            prompt,
            SPORTS_CAVE_RIVALRY_COMPOSITION_RULES_V1,
        )

    signature_rules = build_authentic_signature_application_rules(
        prompt,
        design_context=design_context,
    )
    if not design_studio_prompt_has_signature_application_rules(prompt):
        prompt = (
            insert_design_studio_rule_after_rivalry_rules(prompt, signature_rules)
            if include_rivalry_rules
            else insert_design_studio_rule_after_subject_lock(prompt, signature_rules)
        )

    artwork_lock = _clean_prompt(DESIGN_STUDIO_HERO_DOMINANCE_AND_BORDER_LOCK)
    if not design_studio_prompt_has_hero_dominance_and_border_lock(prompt):
        prompt = (
            insert_design_studio_rule_after_existing_block(prompt, signature_rules, artwork_lock)
            if not design_studio_prompt_has_signature_application_rules(prompt_text)
            else (
                insert_design_studio_rule_after_rivalry_rules(prompt, artwork_lock)
                if include_rivalry_rules
                else insert_design_studio_rule_after_subject_lock(prompt, artwork_lock)
            )
        )
    return prompt


def build_design_studio_image_generation_prompt(prompt_text: str, *, design_context=None) -> str:
    include_rivalry_rules = (
        design_studio_prompt_has_rivalry_composition_rules(prompt_text)
        or (
            design_context is not None
            and design_studio_context_is_rivalry(design_context)
        )
    )
    base_prompt = adapt_design_studio_prompt_for_authentic_signature_rules(prompt_text)
    if include_rivalry_rules:
        base_prompt = adapt_design_studio_prompt_for_rivalry(base_prompt)
    prompt = prepend_design_studio_mandatory_artwork_rules(
        base_prompt,
        include_rivalry_rules=include_rivalry_rules,
        design_context=design_context,
    )
    return append_sports_cave_image_realism_rules(
        prompt,
        include_product_lock=False,
    )


def _task_or_placeholder(task_text: str) -> str:
    task = str(task_text or "").strip()
    return task if task else "[PASTED TASK]"


def list_new_design_task_records(list_tasks_func=None) -> list[dict]:
    if list_tasks_func is None:
        try:
            from sports_cave_dashboard import list_tasks as list_tasks_func
        except Exception:
            return []
    try:
        tasks = list_tasks_func(status="open")
    except TypeError:
        tasks = list_tasks_func("open")
    except Exception:
        return []

    task_records = []
    seen = set()
    for task in tasks or []:
        section = str(task.get("section") or task.get("category") or "").strip()
        if section != NEW_DESIGN_TASK_CATEGORY:
            continue
        title = str(task.get("title") or task.get("text") or "").strip()
        if not title:
            continue
        normalised_title = title.casefold()
        if normalised_title in seen:
            continue
        seen.add(normalised_title)
        task_records.append({**task, "title": title, "text": title})
    return task_records


def list_new_design_task_titles(list_tasks_func=None) -> list[str]:
    return [
        task["title"]
        for task in list_new_design_task_records(list_tasks_func)
    ]


def _locked_legends_v2_prompt_from_context(stage, task_text, design_context=None):
    if not isinstance(design_context, dict):
        return ""
    metadata = design_context.get("metadata") if isinstance(design_context.get("metadata"), dict) else {}
    style_slug = design_studio_styles.normalize_design_style(
        design_context.get("design_style") or metadata.get("design_style")
    )
    if style_slug != "legends_jersey_display":
        return ""
    details = _task_design_details(design_context)
    selected_assets = _task_selected_assets(design_context)
    errors = design_studio_styles.validate_design_request(style_slug, details, task_text)
    if errors:
        return "\n".join(
            (
                design_studio_styles.LEGENDS_JERSEY_DISPLAY_CONTRACT_VERSION,
                "PROMPT BLOCKED - correct the task's explicit Legends Jersey Display principal fields before continuing.",
                *errors,
            )
        )
    builders = {
        "research": lambda: design_studio_styles.build_research_prompt(style_slug, task_text, details),
        "find_images": lambda: design_studio_styles.build_find_images_prompt(style_slug, task_text, details),
        "generation": lambda: design_studio_styles.build_generation_prompt(
            style_slug,
            task_text,
            details,
            selected_assets,
        ),
    }
    return builders[stage]()


def build_design_research_prompt(task_text: str, *, design_context=None) -> str:
    locked_prompt = _locked_legends_v2_prompt_from_context(
        "research",
        task_text,
        design_context,
    )
    if locked_prompt:
        return locked_prompt
    prompt = _clean_prompt(DESIGN_RESEARCH_PROMPT_TEMPLATE).replace(
        "[PASTED TASK]",
        _task_or_placeholder(task_text),
    )
    return "\n\n".join(
        (prompt, design_studio_styles.HERO_PHOTOGRAPHIC_DOMINANCE_CONTRACT)
    )


def build_design_image_carousel_prompt(task_text: str, research_answer: str, *, design_context=None) -> str:
    locked_prompt = _locked_legends_v2_prompt_from_context(
        "find_images",
        task_text,
        design_context,
    )
    if locked_prompt:
        return locked_prompt
    prompt = _clean_prompt(DESIGN_IMAGE_CAROUSEL_PROMPT_TEMPLATE)
    image_search_sections = [
        design_studio_styles.FIND_IMAGES_INLINE_RESULT_CONTRACT,
        design_studio_styles.HERO_PHOTOGRAPHIC_DOMINANCE_CONTRACT,
        _clean_prompt(SPORTS_CAVE_HIGH_QUALITY_IMAGE_SEARCH_RULES_V2),
        build_high_quality_image_search_context(
            task_text,
            research_answer,
            design_context=design_context,
        ),
    ]
    return "\n\n".join(
        section
        for section in (prompt, *image_search_sections)
        if str(section or "").strip()
    )


def build_design_generation_prompt(task_text: str, *, design_context=None) -> str:
    locked_prompt = _locked_legends_v2_prompt_from_context(
        "generation",
        task_text,
        design_context,
    )
    if locked_prompt:
        return locked_prompt
    prompt = _clean_prompt(SPORTS_CAVE_FINAL_ARTWORK_MASTER_PROMPT).replace(
        "[PASTED TASK]",
        _task_or_placeholder(task_text),
    )
    asset_context = build_final_artwork_asset_context(
        task_text,
        design_context=design_context,
    )
    return "\n\n".join(
        section
        for section in (
            prompt,
            design_studio_styles.GENERATION_ASSET_VALIDATION_CONTRACT,
            design_studio_styles.HERO_PHOTOGRAPHIC_DOMINANCE_CONTRACT,
            asset_context,
        )
        if str(section or "").strip()
    )


def _design_studio_prompt_id(key: str) -> str:
    return f"design-studio::{key}"


def _render_copy_button(prompt_text: str, key: str, label: str = "Copy Prompt"):
    component_id = f"copy-prompt-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"
    prompt_json = json.dumps(prompt_text)
    safe_component_id = html.escape(component_id)
    safe_label = html.escape(label)

    components.html(
        f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
          <button
            id="{safe_component_id}"
            type="button"
            style="
              width: 100%;
              border: 1px solid rgba(201, 169, 97, 0.65);
              border-radius: 8px;
              background: #111111;
              color: #f6f0e6;
              font-size: 14px;
              font-weight: 650;
              padding: 0.62rem 0.9rem;
              cursor: pointer;
            "
          >
            {safe_label}
          </button>
          <div
            id="{safe_component_id}-status"
            aria-live="polite"
            style="min-height: 20px; margin-top: 6px; color: #b7aa90; font-size: 13px;"
          ></div>
        </div>
        <script>
          const promptText = {prompt_json};
          const button = document.getElementById("{safe_component_id}");
          const status = document.getElementById("{safe_component_id}-status");

          function fallbackCopy(text) {{
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.setAttribute("readonly", "");
            textarea.style.position = "fixed";
            textarea.style.left = "-9999px";
            textarea.style.top = "0";
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            const copied = document.execCommand("copy");
            document.body.removeChild(textarea);
            return copied;
          }}

          button.addEventListener("click", async () => {{
            try {{
              if (navigator.clipboard && window.isSecureContext) {{
                await navigator.clipboard.writeText(promptText);
              }} else if (!fallbackCopy(promptText)) {{
                throw new Error("Copy fallback failed");
              }}
              status.textContent = "Copied - paste into ChatGPT";
            }} catch (error) {{
              try {{
                if (!fallbackCopy(promptText)) {{
                  throw error;
                }}
                status.textContent = "Copied - paste into ChatGPT";
              }} catch (fallbackError) {{
                status.textContent = "Copy failed. Select the prompt text and copy it manually.";
              }}
            }}
          }});
        </script>
        """,
        height=72,
    )


def _render_prompt_editor(
    label: str,
    prompt_id: str,
    prompt_text: str,
    key: str,
    can_edit_prompts: bool,
    default_text: str | None = None,
):
    editor_key = f"design-studio-edit-open::{key}"
    if not can_edit_prompts:
        st.session_state.pop(editor_key, None)
        return
    if not st.session_state.get(editor_key):
        return

    with st.container(border=True):
        source_record = prompt_store.get_prompt_source(
            prompt_id,
            prompt_text,
            prompt_name=label,
            module="design_studio",
        )
        st.caption(source_record.get("source_label") or "")
        if source_record.get("warning"):
            st.warning(source_record["warning"])
        edited_prompt = st.text_area(
            "Edit prompt",
            value=prompt_text,
            height=460,
            key=f"design-studio-edit-text::{key}",
        )
        save_col, cancel_col, _ = st.columns([1, 1, 4])
        if save_col.button("Save", key=f"design-studio-edit-save::{key}", use_container_width=True):
            if not edited_prompt.strip():
                st.error("Prompt cannot be empty.")
            elif not can_edit_prompts:
                st.error("Prompt editing is not approved for this account.")
            else:
                try:
                    saved = prompt_store.save_prompt(prompt_id, label, edited_prompt, module="design_studio")
                except Exception as error:
                    st.error(str(error))
                else:
                    st.session_state[editor_key] = False
                    record_activity_log(
                        "design_prompt_saved",
                        "Design Studio",
                        f"Saved design prompt: {label}",
                        entity_type="design_prompt",
                        entity_id=prompt_id,
                        metadata={"prompt_label": label},
                    )
                    if saved.get("persisted"):
                        st.success(saved.get("source_label") or "Source: Supabase saved")
                    else:
                        st.warning(saved.get("warning") or saved.get("source_label"))
                    st.rerun()
        if cancel_col.button("Cancel", key=f"design-studio-edit-cancel::{key}", use_container_width=True):
            st.session_state[editor_key] = False
            st.rerun()
        if default_text is not None:
            reset_confirmation = st.text_input(
                "Type RESET PROMPT to restore the default prompt",
                key=f"design-studio-reset-confirm::{key}",
            )
            if st.button(
                "Reset to default prompt",
                key=f"design-studio-reset::{key}",
                disabled=reset_confirmation != "RESET PROMPT",
                use_container_width=True,
            ):
                try:
                    saved = prompt_store.reset_prompt_to_default(
                        prompt_id,
                        label,
                        default_text,
                        module="design_studio",
                    )
                except Exception as error:
                    st.error(str(error))
                else:
                    st.session_state[editor_key] = False
                    if saved.get("persisted"):
                        st.success(saved.get("source_label") or "Source: Supabase saved")
                    else:
                        st.warning(saved.get("warning") or saved.get("source_label"))
                    st.rerun()


def render_copy_prompt_box(
    label: str,
    default_prompt_text: str,
    key: str,
    can_edit_prompts: bool = False,
):
    prompt_id = _design_studio_prompt_id(key)
    effective_prompt = prompt_store.get_prompt(prompt_id, _clean_prompt(default_prompt_text))
    if key in DESIGN_STUDIO_IMAGE_GENERATION_PROMPT_KEYS:
        effective_prompt = build_design_studio_image_generation_prompt(effective_prompt)
    source_record = prompt_store.get_prompt_source(
        prompt_id,
        _clean_prompt(default_prompt_text),
        prompt_name=label,
        module="design_studio",
    )

    st.markdown(f"**{label}**")
    st.caption(source_record.get("source_label") or "Copy this prompt, paste it into ChatGPT inside the Sports Cave Designs project.")
    if source_record.get("warning"):
        st.warning(source_record["warning"])
    st.text_area(
        label,
        value=effective_prompt,
        height=420,
        key=f"design-studio-prompt::{key}::{hashlib.sha1(effective_prompt.encode('utf-8')).hexdigest()[:10]}",
        label_visibility="collapsed",
        disabled=True,
    )
    if can_edit_prompts:
        copy_col, edit_col = st.columns([6, 1])
        with copy_col:
            _render_copy_button(effective_prompt, key)
        if edit_col.button(
            "Edit",
            key=f"design-studio-edit-button::{key}",
            help="Edit prompt.",
            icon=":material/edit:",
            use_container_width=True,
        ):
            st.session_state[f"design-studio-edit-text::{key}"] = effective_prompt
            st.session_state[f"design-studio-edit-open::{key}"] = True
            st.rerun()
    else:
        _render_copy_button(effective_prompt, key)

    _render_prompt_editor(
        label,
        prompt_id,
        effective_prompt,
        key,
        can_edit_prompts,
        default_text=_clean_prompt(default_prompt_text),
    )


def render_generated_prompt_box(
    label: str,
    prompt_text: str,
    key: str,
    copy_label: str,
    *,
    height: int = 360,
):
    effective_prompt = _clean_prompt(prompt_text)
    st.markdown(f"**{label}**")
    st.text_area(
        label,
        value=effective_prompt,
        height=height,
        key=f"design-studio-generated-prompt::{key}::{hashlib.sha1(effective_prompt.encode('utf-8')).hexdigest()[:10]}",
        label_visibility="collapsed",
        disabled=True,
    )
    _render_copy_button(effective_prompt, key, label=copy_label)


def render_new_design_tab():
    st.subheader("New Design")
    st.markdown(
        "1. Paste the Home design task below and run the Research Prompt in the Sports Cave Designs chat.\n"
        "2. After the research answer appears, run the Find Images Prompt underneath it in the same chat.\n"
        "3. Once the image carousel is shown, run the Design Generation Prompt in the same chat."
    )
    st.markdown("### Step 1 - Research")
    task_records = list_new_design_task_records()
    task_options = [task["title"] for task in task_records]
    selected_task_record = None
    if task_options:
        selected_task = st.selectbox(
            "Choose design task",
            alphabetize_options(
                [MANUAL_NEW_DESIGN_TASK_OPTION, *task_options],
                first=(MANUAL_NEW_DESIGN_TASK_OPTION,),
            ),
            key="design-studio-new-design-task-select",
        )
        selected_task_text = "" if selected_task == MANUAL_NEW_DESIGN_TASK_OPTION else selected_task
        if selected_task_text:
            selected_task_record = next(
                (task for task in task_records if task["title"] == selected_task_text),
                None,
            )
    else:
        selected_task_text = ""
        st.selectbox(
            "Choose design task",
            ["No new design tasks waiting"],
            disabled=True,
            key="design-studio-new-design-task-select-empty",
        )
    task_text = st.text_area(
        "Paste design task",
        value=selected_task_text,
        placeholder='Paste a task from "New designs to complete" here...',
        height=110,
        key=f"design-studio-task-research-input::{hashlib.sha1(selected_task_text.encode('utf-8')).hexdigest()[:10]}",
    )
    research_prompt = build_design_research_prompt(
        task_text,
        design_context=selected_task_record if selected_task_record else None,
    )
    render_generated_prompt_box(
        "Research Prompt",
        research_prompt,
        "design-research",
        "Copy Research Prompt",
        height=340,
    )
    st.divider()

    st.markdown("### Step 2 - Find Images")
    image_prompt = build_design_image_carousel_prompt(
        task_text,
        "",
        design_context=selected_task_record if selected_task_record else None,
    )
    render_generated_prompt_box(
        "Find Images Prompt",
        image_prompt,
        "design-image-carousel",
        "Copy Find Images Prompt",
        height=340,
    )
    st.divider()

    st.markdown("### Step 3 - Generate Design")
    design_prompt = build_design_generation_prompt(
        task_text,
        design_context=selected_task_record if selected_task_record else None,
    )
    render_generated_prompt_box(
        "Design Generation Prompt",
        design_prompt,
        "design-generation-from-research",
        "Copy Design Generation Prompt",
        height=420,
    )


def _render_prompt_box(name, prompt, key, can_edit_prompts):
    render_copy_prompt_box(name, prompt, key, can_edit_prompts)


def _task_design_style(task):
    try:
        import sports_cave_dashboard

        return sports_cave_dashboard.task_design_style(task)
    except Exception:
        metadata = (task or {}).get("metadata") or {}
        return design_studio_styles.normalize_design_style(
            (task or {}).get("design_style") or metadata.get("design_style")
        )


def _task_design_details(task):
    metadata = dict((task or {}).get("metadata") or {})
    try:
        import sports_cave_dashboard

        details = sports_cave_dashboard.design_task_details(task)
        legacy_details = sports_cave_dashboard.task_import_details(task)
    except Exception:
        saved = metadata.get("design_details")
        details = design_studio_styles.normalize_design_details(
            saved if isinstance(saved, dict) else {}
        )
        legacy_details = metadata
    team_or_athlete = str(legacy_details.get("team_or_athlete") or "").strip()
    saved_principals = details.get("principal_subjects") or metadata.get("principal_subjects") or []
    if not isinstance(saved_principals, (list, tuple, set)):
        saved_principals = [
            part.strip()
            for part in re.split(r"\s*(?:,|\band\b|&)\s*", str(saved_principals or ""), flags=re.I)
            if part.strip()
        ]
    else:
        saved_principals = [str(value or "").strip() for value in saved_principals if str(value or "").strip()]
    if len(saved_principals) < 3 and team_or_athlete:
        delimited_people = [
            part.strip()
            for part in re.split(r"\s*(?:,|\band\b|&)\s*", team_or_athlete, flags=re.I)
            if part.strip()
        ]
        if len(delimited_people) > len(saved_principals):
            saved_principals = delimited_people
    subject_one = str(details.get("principal_subject_one") or "").strip()
    subject_two = str(details.get("principal_subject_two") or "").strip()
    if team_or_athlete and not subject_one:
        parts = re.split(r"\s+(?:vs\.?|versus)\s+", team_or_athlete, maxsplit=1, flags=re.I)
        subject_one = parts[0].strip()
        subject_two = subject_two or (parts[1].strip() if len(parts) > 1 else "")
    canonical = design_studio_styles.normalize_design_details(details)
    canonical["principal_subject_one"] = subject_one
    canonical["principal_subject_two"] = subject_two
    canonical["_saved_principal_subjects"] = saved_principals
    return canonical


def _task_selected_assets(task):
    metadata = dict((task or {}).get("metadata") or {})
    for key in ("selected_images", "selected_assets", "image_assets"):
        value = metadata.get(key)
        if isinstance(value, list):
            return value
    return []


def _persist_task_design_details(task, style_slug, details):
    task_id = str((task or {}).get("id") or "").strip()
    if not task_id:
        st.warning("This design task has no durable task ID. Refresh the Design Schedule and try again.")
        return None
    try:
        import sports_cave_dashboard

        updated = sports_cave_dashboard.update_task_design_details(
            task_id,
            style_slug,
            details,
        )
    except (ValueError, sports_cave_dashboard.DashboardStorageError) as error:
        st.warning(str(error))
        return None
    except Exception:
        st.warning("Design details could not be saved. Refresh the Design Schedule and try again.")
        return None
    if hasattr(st, "toast"):
        st.toast("Design details saved to the Design Schedule.")
    else:
        st.success("Design details saved to the Design Schedule.")
    return updated


def _render_v2_prompt_card(label, purpose, prompt, key, *, expanded=False, height=260):
    with st.expander(label, expanded=expanded):
        st.caption(purpose)
        prompt_text = _clean_prompt(prompt)
        prompt_identity = (
            f"{design_studio_styles.STYLE_REGISTRY_VERSION}::"
            f"{hashlib.sha1(prompt_text.encode('utf-8')).hexdigest()[:10]}"
        )
        st.text_area(
            f"{label} preview",
            value=prompt_text,
            height=height,
            key=f"design-studio-v2-prompt::{key}::{prompt_identity}",
            label_visibility="collapsed",
            disabled=True,
        )
        _render_copy_button(prompt_text, f"design-studio-v2::{key}::{prompt_identity}", label=f"Copy {label}")


def _render_design_details(defaults, identity, *, can_save=False):
    values = {}
    save_clicked = False
    with st.expander("Design details", expanded=False):
        columns = st.columns(2)
        for index, (name, label) in enumerate(design_studio_styles.DESIGN_DETAIL_FIELDS):
            target = columns[index % 2]
            is_multiline = name in {"essential_text", "special_instructions"}
            widget = target.text_area if is_multiline else target.text_input
            kwargs = {"height": 88} if is_multiline else {}
            values[name] = widget(
                label,
                value=str(defaults.get(name) or ""),
                key=f"design-studio-v2-detail::{identity}::{name}",
                **kwargs,
            )
        if can_save:
            save_clicked = st.button(
                "Save design details",
                key=f"design-studio-v2-save-details::{identity}",
                type="primary",
            )
    return values, save_clicked


def render_design_studio_v2(can_edit_prompts=False, user=None):
    del can_edit_prompts
    st.markdown(
        """
        <style>
        .sc-design-v2-intro { color: #706b62; margin: -.3rem 0 .7rem; }
        .sc-design-v2-style { border-left: 2px solid #b79243; color: #5f5a52; font-size: .82rem; margin: .35rem 0 .65rem; padding: .35rem .65rem; }
        .sc-design-v2-steps { background: #f8f6f1; border: 1px solid #ded8cb; border-radius: 6px; color: #292724; font-size: .84rem; font-weight: 650; margin: .65rem 0; padding: .55rem .75rem; text-align: center; }
        .sc-design-v2-badge { background: #f3ecdc; border: 1px solid #d9c28d; border-radius: 999px; color: #6d531c; display: inline-block; font-size: .68rem; font-weight: 700; margin-left: .35rem; padding: .12rem .42rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Design Studio")
    st.markdown(
        '<div class="sc-design-v2-intro">Manage the design schedule, then build one selected collector artwork.</div>',
        unsafe_allow_html=True,
    )

    selected_task = design_schedule.render_design_schedule(
        user,
        copy_prompt_renderer=lambda prompt, key, label: _render_copy_button(
            prompt,
            key,
            label=label,
        ),
    )
    if not selected_task:
        return

    task_identity = str(selected_task.get("id") or "")
    previous_identity = st.session_state.get(DESIGN_STUDIO_V2_LOADED_TASK_KEY)
    style_memory = st.session_state.setdefault(DESIGN_STUDIO_V2_STYLE_MEMORY_KEY, {})
    details_memory = st.session_state.setdefault(DESIGN_STUDIO_V2_DETAILS_MEMORY_KEY, {})
    if previous_identity != task_identity:
        st.session_state[DESIGN_STUDIO_V2_LOADED_TASK_KEY] = task_identity
        st.session_state[DESIGN_STUDIO_V2_STYLE_KEY] = _task_design_style(selected_task)
        details_memory.pop(task_identity, None)

    style_options = alphabetize_options(
        ["", *design_studio_styles.style_slugs()],
        label=design_studio_styles.design_style_label,
    )
    if st.session_state.get(DESIGN_STUDIO_V2_STYLE_KEY) not in style_options:
        st.session_state[DESIGN_STUDIO_V2_STYLE_KEY] = _task_design_style(selected_task)
    selected_style = st.selectbox(
        "Design style",
        style_options,
        format_func=lambda value: design_studio_styles.design_style_label(value),
        key=DESIGN_STUDIO_V2_STYLE_KEY,
    )
    style_memory[task_identity] = selected_style
    style = design_studio_styles.get_design_style(selected_style)
    if style:
        st.markdown(
            f'<div class="sc-design-v2-style"><strong>{html.escape(style.description)}</strong> Example: {html.escape(style.example)}.</div>',
            unsafe_allow_html=True,
        )

    task_text = str(selected_task.get("text") or selected_task.get("title") or "").strip()

    defaults = _task_design_details(selected_task)
    remembered_details = details_memory.get(task_identity)
    if isinstance(remembered_details, dict):
        defaults = {**defaults, **remembered_details}
    details, save_clicked = _render_design_details(
        defaults,
        hashlib.sha1(task_identity.encode("utf-8")).hexdigest()[:10],
        can_save=bool(selected_task),
    )
    details_memory[task_identity] = details
    if save_clicked:
        if not selected_style:
            st.warning("Style required before design details can be saved.")
        else:
            updated_task = _persist_task_design_details(
                selected_task,
                selected_style,
                details,
            )
            if updated_task:
                selected_task.clear()
                selected_task.update(updated_task)
                selected_task["design_style"] = selected_style
                selected_task.setdefault("metadata", {})["design_style"] = selected_style
                selected_task["metadata"]["design_details"] = dict(details)
    if len(defaults.get("_saved_principal_subjects") or []) > 2:
        details["principal_subjects"] = defaults["_saved_principal_subjects"]
    st.markdown(
        '<div id="design-studio-workflow" class="sc-design-studio-workflow"></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sc-design-v2-steps">1 Research &nbsp;&rarr;&nbsp; 2 Find Images &nbsp;&rarr;&nbsp; 3 Generate &nbsp;&rarr;&nbsp; 4 Signature Placement &nbsp;&rarr;&nbsp; 5 Harsh Review</div>',
        unsafe_allow_html=True,
    )

    if not selected_style:
        st.warning("Style required. Choose a design style to build the four V2 prompts.")
        return
    errors = design_studio_styles.validate_design_request(selected_style, details, task_text)
    if errors:
        for error in errors:
            st.error(error)
        return

    selected_assets = _task_selected_assets(selected_task)
    prompts = design_studio_styles.build_prompt_bundle(
        selected_style,
        task_text,
        details,
        selected_assets,
    )
    _render_v2_prompt_card(
        "Research Prompt",
        "Verify the moment, source direction and factual collector story.",
        prompts["research"],
        f"{task_identity}::{selected_style}::research",
        expanded=True,
    )
    _render_v2_prompt_card(
        "Find Images Prompt",
        "Retrieve only authentic final-use assets required by this style.",
        prompts["find_images"],
        f"{task_identity}::{selected_style}::find-images",
    )
    _render_v2_prompt_card(
        "Design Generation Prompt",
        "Composite the selected immutable source assets into the chosen Sports Cave system.",
        prompts["generation"],
        f"{task_identity}::{selected_style}::generation",
        height=300,
    )
    _render_v2_prompt_card(
        "Signature Placement Prompt",
        "Make the final surgical name and authentic-signature pass without redesigning the artwork.",
        prompts["signature_placement"],
        f"{task_identity}::{selected_style}::signature-placement",
    )
    _render_v2_prompt_card(
        "Harsh Review",
        "Score the finished artwork and return one precise correction brief.",
        prompts["review"],
        f"{task_identity}::{selected_style}::review",
    )


def render_design_studio_page(can_edit_prompts: bool = False, user=None):
    render_design_studio_v2(can_edit_prompts=can_edit_prompts, user=user)
