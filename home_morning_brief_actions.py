"""Compact recommendation rows and their ChatGPT project handoff."""

from functools import lru_cache
from html import escape
from pathlib import Path
import re
from urllib.parse import urlencode

from home_brief_calendar import MARKETS, PRODUCT_QUERY, calendar_rows, product_handle
from psd_directory import REVIEW_FOLDER, REVIEW_METADATA_FOLDER

PROJECT_URL = "https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project"
TEMPLATE = Path(__file__).parent / "components" / "morning_brief_actions.html"


META_AD_HEADING = re.compile(r"^(?:recommended|suggested)\b.*\bmeta\b.*\bad\b", re.I)
META_AD_COPY = re.compile(r"^(?:headline|primary text|description|cta|call to action)\s*:", re.I)

_BORDER_STYLE_GUIDANCE = (
    "Choose a border that suits the artwork. Restrained antique gold, fine double lines or "
    "subtle heritage corners can work where they add to the design. A simple, elegant border "
    "is equally suitable. Avoid heavy ornament and vary the treatment across designs."
)

_CREATE_DESIGN_BORDER_RULES = (
    "**Border and print safety for both artwork passes and the final layout**\n\n"
    "Leave an even framing-safe margin equal to 3% of the canvas’s shorter dimension on all "
    "four sides. Measure from the canvas edge to the outermost decorative border detail, "
    "including corner ornaments. On the 2835 × 2004 master, use 60 px.\n\n"
    f"{_BORDER_STYLE_GUIDANCE}\n\n"
    "Extend the background to every canvas edge. Adjust only the border and its corner details "
    "to achieve the margin. Preserve the existing artwork scale and layout. Verify the margin "
    "after generation and correct it during final assembly.\n\n"
    "This is a framing-safe margin. Apply any printer-required bleed separately.\n\n"
)

_EDIT_DESIGN_BORDER_RULES = (
    "**Border and print safety for both artwork passes and the final layout**\n\n"
    "Target an even border inset of 2% of the canvas’s shorter dimension. Calculate it once "
    "and use the same pixel distance on all four sides. Keep the margin modest so the subject "
    "stays large and impactful. Extend the background fully to the canvas edges. Keep the "
    "decorative border and all important subject details, text, signatures and the official "
    "badge inside the framing-safe area. Use only expendable background in the outer margin.\n\n"
    f"{_BORDER_STYLE_GUIDANCE} "
    "Preserve the existing composition and subject scale wherever possible. Make only the "
    "minimum adjustments needed for safe spacing.\n\n"
    "Treat the inset as a framing safety margin. Determine print bleed separately. Follow "
    "the printer’s actual bleed, trim and frame-overlap requirements when available. Those "
    "requirements override the default inset. If they cannot be checked, use the default, "
    "record print safety as unverified in REVIEW NOTES and continue the workflow. Claim "
    "verified print safety only after checking the artwork against those requirements.\n\n"
)

_CREATE_DESIGN_COLLECTOR_FINISH = (
    "**COLLECTOR FINISH — APPLY WITHIN THE EXISTING REVIEW**\n\n"
    "Use these criteria within the existing image selection, generation and correction steps. "
    "Follow the same execution order, retry limits, save requirements and continuation rules.\n\n"
    "Judge the actual artwork. Identify its three most visible weaknesses and address them "
    "within the existing correction allowance. Preserve successful elements and apply only "
    "improvements relevant to this design.\n\n"
    "- **Photographic consistency.** Match sharpness, texture, lighting and colour across the "
    "face, body, uniform and equipment. Blend a restored face naturally into the surrounding "
    "helmet, neck and body. Check for visible patches even when using original pixels.\n"
    "- **Complete, believable action.** Prefer sources that show the important limbs and "
    "equipment. Compose deliberately around any source crop. Do not disguise missing anatomy "
    "with smoke, darkness or excessive spray. Never invent missing parts.\n"
    "- **Subject-first hierarchy.** Make the athlete, vehicle or meaningful interaction read "
    "first at thumbnail size. Adjust title scale, line breaks and spacing if text competes "
    "with the subject. Avoid oversized filler words. Choose a layout that suits this design.\n"
    "- **Purposeful placement.** Arrange the title, signature and official badge deliberately. "
    "Place signatures against quiet, contrasting space and preserve their actual strokes. "
    "Keep collector details subordinate and readable.\n"
    "- **Believable environment.** Match the sport’s real surface, perspective and lighting. "
    "Reduce reflections, artificial glow and decorative effects that weaken realism or compete "
    "with the subject.\n\n"
    "Compare each correction with the strongest previous version at full size and thumbnail "
    "size. Keep it only when the whole artwork improves. Complete the existing workflow within "
    "its retry limits and report any unresolved defects honestly.\n\n"
)

_CREATE_DESIGN_COLLECTOR_BACKGROUND = (
    "**SPORTS CAVE COLLECTOR BACKGROUND — BOTH GENERATIONS**\n\n"
    "Transform the photographic environment into a distinctive, dark Sports Cave collector "
    "backdrop. Keep the source setting’s recognisable structure, perspective and sporting "
    "context visible. Reduce its brightness, saturation and distracting detail so it reads as "
    "subtle atmosphere with believable depth.\n\n"
    "Build a restrained charcoal-and-black treatment with soft tonal gradients, fine material "
    "texture and low-contrast abstract patterns informed by the team, sport or era. Choose "
    "only treatments that suit this artwork. Keep meaningful team-colour accents controlled. "
    "Subdue bright turf, crowds, signage and advertising while keeping the original setting "
    "quietly visible beneath the treatment. Avoid repeating logos, obvious wallpaper patterns, "
    "heavy grunge, smoke, sparks and decorative clutter.\n\n"
    "Apply the treatment only to the background. Preserve the athlete’s authentic photographic "
    "details, natural skin, uniform colours and equipment. Match the background lighting to "
    "the subject and blend edges subtly. Keep the treatment’s darkening and texture off the "
    "athlete.\n\n"
    "When applying or refining the backdrop, preserve the successful composition, subject "
    "scale, title, signature, official plaque and safe border placement. Judge the treatment "
    "at thumbnail size. The subject reads first, the title second, and the background "
    "supports both.\n\n"
)


def _story_without_meta_ad(text):
    lines = []
    ad = False
    for line in text.splitlines():
        label = line.strip().lstrip("#*- ").replace("*", "").replace("\\:", ":")
        if META_AD_HEADING.match(label):
            ad = True
            continue
        if ad and (not label or META_AD_COPY.match(label) or label.startswith(("“", '"', "‘"))):
            continue
        ad = False
        lines.append(line)
    return "\n".join(lines).strip()


def _prompt(title, story, *, edit=None):
    context = _story_without_meta_ad(story)
    if edit is None:
        background_guide = _CREATE_DESIGN_COLLECTOR_BACKGROUND
        first_background = "Use the collector background treatment above. "
        second_background = (
            "Carry forward the collector background treatment from Step 5. Refine it only where the "
            "artwork benefits. Use the same guidance if the first pass was unavailable.\n\n"
        )
        background_effects = "and keep supporting effects within the collector background guidance above. "
    else:
        background_guide = second_background = ""
        first_background = (
            "Build a cohesive vintage background with subtle textures and details from the sport "
            "or venue and restrained team colours. "
        )
        background_effects = "and keep glow, sparks, smoke and haze restrained. "
    workflow = (
        f"Sports Cave event: {title}\n\n"
        "**EXECUTION AUTHORITY — START NOW**\n"
        "\n"
        "When I submit this prompt for artwork creation, that submission authorises immediate "
        "execution of the complete workflow, including the specified Dropbox saves, verification "
        "and trial cleanup.\n"
        "\n"
        "The attached sports brief or design details are research context. Their “Decision,” “Timing,” "
        "“Recommendation,” “Monitor,” “Wait,” or similar wording describes earlier planning "
        "advice and does not override this instruction to create the artwork now.\n"
        "\n"
        "Do not ask whether to start, wait for another match, approve the trial, or proceed to "
        "the second generation. Make ordinary creative decisions yourself and continue through "
        "every executable checkpoint.\n"
        "\n"
        "Still verify factual claims and source photographs. Do not invent results, imagery, "
        "signatures or successful operations. If an operation genuinely fails, attempt reasonable "
        "authorised recovery, preserve completed work, continue independent steps, and report "
        "the exact remaining blocker.\n"
        "\n"
        "Displaying photographs or artwork is a progress checkpoint, not a request for approval. "
        "Continue immediately after displaying them.\n"
        "\n"
        "**MANDATORY EXECUTION ORDER**\n"
        "\n"
        "This task requires **two separate full-artwork image-generation calls and two confirmed Dropbox "
        "saves**:\n"
        "\n"
        "**Normal order:** **Generate and inspect first complete artwork → confirm trial PSD save → regenerate and "
        "inspect complete artwork → select the strongest inspected version → confirm and verify new final PSD → confirm trial deletion → "
        "display final artwork.**\n"
        "\n"
        "Complete every checkpoint. If master PSD retrieval or a Dropbox save fails after reasonable "
        "recovery attempts, preserve completed work and finish every independent step without waiting "
        "for access or approval. This includes both full artwork generations, verified signature "
        "extraction and placement, photographic corrections, final inspection, and display in chat. "
        "Defer only steps that require the original PSD layers or the unavailable Dropbox operation. "
        "Follow this recovery order if the project guide suggests requesting the master earlier. "
        "Report the specific missing master file or access dependency only after exhausting authorised "
        "recovery methods and finishing all independent work. Resume deferred steps if access returns "
        "during the run. Otherwise deliver the available work and report what remains pending.\n"
        "\n"
        "Never invent or replace the master badge or editable edition-number layer. Never claim a save "
        "or verification succeeded without confirmation. Delete only this run’s trial, and only after "
        "the final PSD is saved and verified.\n"
        "\n"
        "Generating only a background and manually placing the athlete over it does "
        "not satisfy the second full-artwork generation.\n"
        "\n"
        "**MANDATORY CONTINUATION AND RECOVERY**\n"
        "\n"
        "Execute the entire workflow autonomously. Do not stop for ordinary design imperfections, "
        "low-resolution search results, unsuccessful generations, missing signatures or a failed "
        "first attempt.\n"
        "Perform every design review and correction yourself. Continue through every executable step "
        "without waiting for approval "
        "or a manual review. REVIEW NOTES inform your corrections and final report.\n"
        "\n"
        "**Quality concerns require corrective action.** Search for higher-resolution originals, "
        "inspect the source pages, choose a stronger verified photograph that fits the chosen story, "
        "adapt the composition to the available crop, or regenerate. Preserve the verified event "
        "when the design commemorates one. Do not invent missing anatomy.\n"
        "\n"
        f"{_CREATE_DESIGN_COLLECTOR_FINISH if edit is None else ''}"
        "**The first Dropbox save is a review checkpoint, not final production approval.** After "
        "generating and inspecting the first complete artwork, save it on a copy of the master PSD "
        "in the specified review folder. Document remaining concerns in a hidden `REVIEW NOTES` "
        "layer. If the trial cannot be saved, keep those notes with the first artwork until the PSD "
        "can be prepared. Use them to guide the mandatory second full-artwork generation in either case.\n"
        "\n"
        "Do not demand perfection before the first save. Do not describe a review draft as approved "
        "or print-ready.\n"
        "\n"
        "**After confirming the trial save or marking it pending after reasonable recovery attempts, "
        "continue immediately to Step 8 without asking permission.** "
        "Generate the complete artwork again using the first artwork and original photographs, "
        "inspect and compare both, and save the strongest inspected version in a separate final PSD. Preserve the "
        "first artwork in the final PSD's hidden `ORIGINAL EDITABLE ARTWORK` group.\n"
        "\n"
        "**Recover from tool failures.** Prefer available authorised connectors, APIs, built-in web "
        "search and local files. Use Edge or Chrome only if it is already authorised and available. "
        "If a browser route would require permission, sign-in, or user interaction, skip it without "
        "prompting and use an authorised alternative. If none works, defer only the affected "
        "operation and continue the run. For technical failures other than image generation, retry "
        "a transient failure at most once per authorised method, then move on. Revisit a deferred "
        "operation only if its prerequisite becomes available during the run. "
        "If a save response is uncertain, reconcile it against the intended Dropbox path and "
        "saved file identity and contents before retrying. Keep the trial until the final PSD "
        "is verified.\n"
        "\n"
        "**Missing signatures must not stop the artwork.** Follow the source search and bounded "
        "extraction checks in Step 4 before omitting a signature. "
        "Never generate or redraw a signature.\n"
        "\n"
        "A blocker in a later step must not stop earlier executable steps. Generate and inspect the "
        "first full artwork and attempt the trial PSD save before addressing final-stage verification "
        "limitations. After trying reasonable alternatives, pause only the genuinely blocked "
        "operation and any work that depends on it. Preserve completed progress and continue "
        "independent work. A design concern calls for "
        "correction or a source-based fallback and is not a reason to stop. Identify the exact failed "
        "operation, attempts made, saved progress and smallest action needed to resume. Never claim "
        "an unperformed generation, save, verification or deletion succeeded.\n"
        "\n"
        "**Finish within the retry limits.** Complete both required full-artwork generations. Allow "
        "at most two additional image-generation attempts total across both passes, including retries "
        "after tool failures. Both full-artwork generations are mandatory creative passes. After "
        "each pass, use source-photo compositing where needed to restore authentic subject details. "
        "This restoration is authorised finishing work and preserves the full-artwork generation "
        "requirement. If a pass remains unavailable, record it as incomplete and carry on with "
        "available inputs. At the retry limit deliver the strongest faithful result and record "
        "unresolved limitations. Never label failed or unverified quality or production checks as passed.\n"
        "\n"
        f"{context}\n\n"
        "**CHOOSE THE COLLECTOR TITLE AND DESIGN DIRECTION**\n\n"
        "Before settling on the title or layout, use the authorised Shopify connection in read-only mode. "
        "Check product sales reports for bestselling Sports Cave prints in the same sport or collection. "
        "Use the closest comparable sport or collector collection if the matching category is sparse. "
        "Open the actual storefront product pages and inspect the artwork. Compare what works in their "
        "titles, subject placement, typography, hierarchy and negative space. Where sales evidence "
        "allows, contrast with a comparable lower-selling print to spot weaknesses without assuming "
        "the design caused the sales difference. Use relevant cues to inform an original design. "
        "If reports are unavailable, use a verifiable storefront bestseller listing or approved project "
        "references. Treat unranked products as style references only. Record the evidence or gap in "
        "REVIEW NOTES and continue immediately with the available references and rules below.\n\n"
        "Use the brief and recent events to decide who to feature and when to promote them. Treat its "
        "event label and any suggested title as research context. Default to timeless player, team, "
        "rivalry or sporting identity artwork. Ask whether fans would still want to display it in "
        "five years. A strong match, a single century, a weekly stat line or a narrowly defined record "
        "can justify featuring the subject. Use an enduring story for the print and omit match statistics, "
        "scores and dates. If in doubt, use the athlete’s or team’s name and omit match statistics and dates.\n\n"
        "Build an edition around an event only when the verified achievement has lasting collector "
        "significance, such as a championship, league or season MVP, player of the year, player of a "
        "completed landmark series such as the Ashes, an established all-time achievement, or an iconic "
        "moment or farewell fans will remember. Apply the same test to recent and historic events. "
        "Use a single concise verified statistic or accolade only if it tells that lasting story. Use a "
        "year only if it identifies the achievement or era, and a full date only when the day itself "
        "matters. Avoid live rankings, ongoing averages, changing totals and unsupported GOAT claims.\n\n"
        "Consider a few short, cinematic headline options and pick the most distinctive one the photo "
        "and sporting story can support. Think ‘The King of Spin’ for Shane Warne or ‘Six Laps Ahead’ "
        "where the racing story earns it. Keep the subject recognisable, the headline readable in one "
        "glance, and the layout focused on why a fan would display the print. Let the title and photo "
        "reinforce each other, with quiet space for the title and only essential supporting text. "
        "Carry the chosen title and direction into photo selection and both generations.\n\n"
        "List the best possible images. Show the photos in this chat first. Use web image search to "
        "aim for 4–8 images that fit the chosen subject and story. If fewer are usable after checking the original source "
        "pages, show the candidates that meet the Step 1 standard. Focus on photo authenticity, image "
        "quality, and how each photo supports the artwork. I will handle photo licensing "
        "separately. Do not research, assess, or mention photo licensing, commercial-use "
        "permissions, or usage rights.\n\n"
        "**STORY-FIRST IMAGE SELECTION**\n"
        "\n"
        "Use these cues within the existing image search. Start with the title and the exact "
        "sporting moment or emotional reason to own the artwork. Search the named achievement, "
        "gesture, event or era alongside the subject. Where available, compare distinct authentic "
        "action, celebration, achievement and identity photos. For timeless artwork, consider the "
        "strongest verified images from the relevant career, team or era. For an event edition, focus "
        "on authentic images of that event. "
        "Rank story fit first, then emotional impact, recognisability, readable pose, composition "
        "potential and original source quality at print size. A sharp neutral portrait earns "
        "the hero spot when it best serves the story.\n"
        "\n"
        "Use the visual review of recent Sports Cave best sellers as a reference, choosing the "
        "family that fits the photograph and title. Defining action needs a readable movement "
        "and room in its direction. For achievement, look for visible evidence such as a belt, trophy, "
        "decisive action or unmistakable reaction. A paired legends or rivalry title can give "
        "both named subjects comparable weight within one coherent composition. For heritage "
        "racing, consider the correct period machine in the lower foreground with its driver "
        "or historical context above or beside it. For farewell or legacy, look for a real bow, "
        "wave, walk away or embrace and give the gesture breathing room. When a genuine photo "
        "captures the relationship, preserve the interaction. These are optional directions.\n"
        "\n"
        "Collection cues for the same search:\n"
        "- UFC / boxing: belt celebration, iconic victory gesture or decisive exchange.\n"
        "- V8 Supercars / historic racing: correct period car and livery, circuit action, "
        "finish or meaningful driver interaction.\n"
        "- Formula One: defining corner, chequered flag, podium or celebration. For a specific "
        "victory, keep supporting car imagery from that event.\n"
        "- NASCAR: close finish, numbered car on the banking or victory-lane emotion with "
        "readable livery.\n"
        "- MotoGP / motorcycles: committed lean, wheelie or victory gesture with a clear "
        "rider-and-bike silhouette and space into the corner.\n"
        "- Cricket: wicket celebration, batting stroke, century salute, trophy lift or farewell.\n"
        "- Baseball: swing, pitching delivery, home-run reaction or defining fielding play "
        "with the bat or glove visible.\n"
        "- NBA: iconic shot, dunk, championship emotion or meaningful jersey pairing.\n"
        "- Football / Matildas: decisive strike, goal celebration, trophy embrace or "
        "recognisable national-team moment.\n"
        "- Rugby league: line break, fend, try, full-time reaction or trophy celebration.\n"
        "- AFL: spectacular mark, kick, goal celebration or premiership moment.\n"
        "- NFL: readable catch, run, quarterback delivery, championship reaction or legacy pairing.\n"
        "- Ice hockey: save, shot, goal celebration, Stanley Cup lift or defining rivalry.\n"
        "- Tennis: fist pump, championship collapse, trophy, distinctive stroke or genuine "
        "rivalry interaction.\n"
        "- Horse racing: full horse in stride, finish, jockey salute or historic winner, "
        "with accurate silks and saddlecloth. Keep any tribute pairing distinct from an actual shared race.\n"
        "- Darts: focused throw, winning roar or trophy celebration, with the throwing hand "
        "and dart visible when relevant.\n"
        "- WWE: iconic confrontation, entrance, signature pose or championship moment.\n"
        "- Olympics: specific finish-line emotion, medal, flag or signature performance "
        "with the correct event and era details.\n"
        "- Motivational quotes: effort, exhaustion, concentration or a defining moment "
        "whose body language supports the verified quote.\n"
        "\n"
        "Let the photo drive the arrangement within the established Sports Cave style. Keep one "
        "clear visual priority, which can be the relationship itself in a paired design. Use "
        "supporting imagery only for a different part of the story, with quieter contrast, "
        "colour and placement. Preserve faces, anatomy, uniforms, lettering, equipment and decisive "
        "details such as the belt, ball, wheels or relevant opposition. Leave room for movement or "
        "gaze and reframe without mirroring. Keep event context accurate and avoid inventing action "
        "or presenting unrelated events as one moment. Check that the story reads at thumbnail "
        "size and that the image still communicates it with the title hidden.\n"
        "\n"
        "Step 1. **Hero photo selection — title first.** Compare candidates for subject prominence, "
        "emotional relevance, clarity and compositional potential. Choose the photo that best tells "
        "the named subject's collector story. In an individual-player edition, the named athlete "
        "must dominate immediately at thumbnail size. Reject photos where teammates, opponents, "
        "back views or obstructions dominate or conceal the athlete. If no candidate meets the "
        "standard, make a focused follow-up search of original galleries and alternate sources. "
        "If no suitable original is accessible, keep the composition provisional, use only verified "
        "subject details, and record the missing source without waiting. "
        "Keep an individual tribute centred on that athlete. Use one strong hero photograph when "
        "it tells the story on its own. If a second photo adds distinct value, use it as subordinate "
        "background imagery. Place the selected hero in the artwork. Preserve "
        "recognisable faces, uniforms, and event details. Follow the project’s Collector Series "
        "references for typography, colour, depth, and visual hierarchy. Refer to the project "
        "instructions in Sports Cave Designs for how Sports Cave designs are structured.\n\n"
        "Step 2. Inspect designs-canvas.psd in Dropbox for the exact pixel dimensions, orientation, "
        "safe margins, and limited-edition badge. Preserve the "
        "original limited-edition badge and edition-number layer. If retrieval remains blocked after "
        "reasonable recovery attempts, keep the master-dependent PSD work pending. Use verified "
        "master dimensions if available. Otherwise keep the layout provisional and reserve space "
        "for the original badge and editable number to be restored from the master.\n\n"
        "Step 3. Define the composition for a realistic Sports Cave Collector Series design with "
        "a strong focal point and clear visual hierarchy.\n\n"
        f"{_CREATE_DESIGN_BORDER_RULES if edit is None else _EDIT_DESIGN_BORDER_RULES}"
        "Step 4. For each featured person, search both web and image results. Check at least "
        "three distinct credible sources when accessible before skipping a signature. Use a clear, "
        "verified example and place it on a separate layer where it fits naturally with the artwork "
        "and typography. Keep the original letterforms and strokes. Refine the placement, "
        "scale, and ink finish for a premium collector look. A textured background alone is no "
        "reason to omit an autograph. Search for clearer flat references, scans or photographs of "
        "verified signed items, download and inspect the strongest authentic candidates, and attempt "
        "faithful extraction once each on up to the three strongest accessible references per "
        "featured person. A page without a signature image counts as a search result only. If "
        "fewer references are accessible after that search, use what is available and continue. "
        "If the best verified source is low resolution but the strokes "
        "can be faithfully extracted, use it on a separate layer in the final collector design. "
        "Improve legibility with precise masking, contrast, and a suitable display size and ink "
        "finish. Keep all original stroke shapes and gaps. Never generate, redraw, or reconstruct "
        "the signature or fill in missing strokes. Omit it if the search and extraction checks "
        "produce no faithful result. Record the sources checked, extraction attempted, and exact "
        "reason it failed in REVIEW NOTES, and continue.\n\n"
        f"{background_guide}"
        "Step 5. Use the image generation tool to generate the first complete Sports Cave "
        "Collector Series artwork. "
        f"{first_background}"
        "Keep vintage texture, "
        "grain, distressing and sharpening effects off the athlete. Integrate the original "
        "hero photo through matching light, colour, and depth while preserving the athlete’s face, "
        "anatomy, pose, and uniform. Keep any verified signature as a separate asset and show the "
        "first complete artwork in the chat before placing it on the PSD.\n\n"
        "Step 6. Inspect the generated artwork against the original photo. Check that the person "
        "looks realistic and that their face, body, and uniform are free of unintended cropping, "
        "blending, or AI distortion. Apply the mandatory subject authenticity check in Step 8C "
        "at 100% magnification to this first generation, restoring altered subject regions where "
        "needed. Make practical corrections and record remaining concerns for "
        "Step 8. Once you have inspected a complete first artwork, proceed to the review save.\n\n"
        "Step 7. Place the first complete artwork on a copy of designs-canvas.psd as a review draft. "
        "Include any verified signatures on separate layers and document remaining concerns in a "
        "hidden REVIEW NOTES layer. Save a new file named **`[Product Title] - TRIAL.psd`** "
        "using the intended online product title. The final name is **`[Product Title].psd`**. "
        f"Save both PSDs directly in the same Dropbox review folder at {REVIEW_FOLDER}/. "
        "Check both names before saving. If either exists, choose an unused matching version "
        "suffix for both, such as `[Product Title] - v2 - TRIAL.psd` and "
        "`[Product Title] - v2.psd`. Create files without replacing existing files. "
        "Confirm the save when possible. If master retrieval or the trial save remains blocked after "
        "reasonable recovery attempts, mark the trial PSD work pending and retain the first artwork "
        "and review notes. Continue immediately to Step 8 in either case.\n\n"
        "**STEP 8 — REQUIRED SECOND FULL-ARTWORK GENERATION**\n"
        "\n"
        "When Dropbox confirms the trial save, record its file ID, path and revision for exact "
        "cleanup after final verification. If the trial save is pending, use the retained first "
        "artwork and review notes to complete the second generation and inspection.\n"
        "If the first generation is unavailable after recovery, use the verified photos and the "
        "planned composition to attempt the second pass independently.\n"
        "\n"
        "**8A. Re-read and review**\n"
        "\n"
        "Re-read `SPORTS-CAVE-LIMITED-EDITION-COLLECTOR-DESIGNS.txt`. Inspect the first complete "
        "artwork as a complete composition and against the original photographs. Use REVIEW NOTES "
        "to identify what makes it effective and explicitly lock those strengths before generating "
        "again: emotional impact, subject dominance, composition, title placement, lighting, depth, "
        "typography, colour, background and how the elements connect. Preserve subtle lines, colour "
        "accents, shadows, textures or fades that help the subject and title work together. "
        "Choose targeted improvements from visible weaknesses in this artwork. If the first version "
        "is strong, keep its visual foundation and make subtle corrections. Reserve larger changes "
        "for specific weaknesses that make the first composition ineffective. If the guide "
        "is inaccessible, record the gap and use the Sports Cave design rules below.\n"
        "Revisit the earlier bestseller evidence alongside the trial before the second generation. "
        "Use reference images as style inputs where supported and only when they solve an identified "
        "weakness. Recheck whether the chosen headline and its position still read well at thumbnail "
        "size and fit the collector story. Preserve what works and apply any needed correction.\n"
        "\n"
        "**8B. Second full generation — preserve what works**\n"
        "\n"
        "**Sports Cave design rules for every final generation**\n"
        "\n"
        "Use the visual guidance below to solve specific weaknesses while keeping the strengths locked in 8A.\n"
        "\n"
        f"{second_background}"
        "Give fans a specific reason to display the artwork. Make the sporting moment, rivalry, "
        "era, team identity or personal legacy immediately recognisable. Use the strongest original "
        "photograph to establish the subject and story. Add supporting imagery only when it adds "
        "meaning. Verify any factual text before including it. For a deliberately event-specific "
        "preview, reserve victory imagery for verified outcomes.\n"
        "\n"
        "Keep a successful primary composition. If a structural weakness warrants a change, choose "
        "one that suits the story and source photographs:\n"
        "- Paired legends or defining rivalry: balance both subjects in one setting, with enough "
        "separation to recognise each figure, jersey and number.\n"
        "- Heritage or historic achievement: use a strong portrait or action photo with relevant "
        "period details, warm shadows, restrained background grain and aged gold typography.\n"
        "- Defining moment or victory: lead with the athlete or vehicle in action. Use authentic "
        "sporting colours and a short title. Keep modern moments crisp.\n"
        "- National or club identity: let one strong image carry the design through a source flag, "
        "crest, jersey or gesture. Keep supporting imagery minimal.\n"
        "- Farewell or personal legacy: let the authentic expression or gesture carry the emotion. "
        "Use quiet negative space and restrained typography.\n"
        "- Authentic interaction or rivalry memory: build around the interaction already captured "
        "in the photo and keep the setting and period details recognisable.\n"
        "\n"
        "Use deep black, charcoal and warm white as the foundation, with restrained gold for "
        "titles, fine borders and small dividers. Preserve meaningful colours in uniforms, flags, "
        "vehicle liveries and equipment. Match the background to the subject's lighting and "
        "perspective. Use natural contact shadows "
        f"{background_effects}"
        "Choose backgrounds that convey setting, era or emotion. Keep working gold lines, colour accents "
        "and other effects when they serve this composition. Add them only when they improve the artwork.\n"
        "\n"
        "Work to the master PSD's aspect ratio and safe area when verified. Otherwise use the "
        "provisional layout from Step 2. Give the subject or sporting moment "
        "visual priority, followed by the collector title and essential context. Use a short, "
        "story-specific title in elegant serif or restrained cinematic type, with smaller tracked "
        "uppercase text where appropriate. Follow the collector title, date and statistics rules above. Use a "
        "fine, controlled collector border where it suits the composition. Keep important details "
        "clear of the border and reserve quiet space along the bottom for the original badge. "
        "Keep the artwork free of mockup framing, walls and rooms.\n"
        "\n"
        "Keep original camera angles, legible lettering and numbers, and accurate vehicle, trophy "
        "and equipment details. Plan around the visible source crop and avoid mirrored details. "
        "When restoring the exact badge and edition-number layers, place the badge once in the "
        "reserved bottom space, within the border and safe area. Preserve its proportions and "
        "relationship to the edition number. Place a verified signature near its subject or title "
        "with a restrained ink finish and readable original strokes. Check the hierarchy, text "
        "and badge placement at full size and as a thumbnail.\n"
        "\n"
        "Make a **new image-generation call** using both:\n"
        "\n"
        "- The first complete artwork as the visual foundation, including the strengths locked in 8A "
        "and the intended title, factual wording, story and subject. If it is unavailable, use the "
        "verified details from the planned composition. For any retry, use the strongest inspected version.\n"
        "- The original photographs as the authority for identity, expression, anatomy, pose, uniform "
        "and equipment. Use category references only to support targeted corrections.\n"
        "\n"
        "Generate a **complete Sports Cave collector artwork** with the subject, setting, lighting, "
        "typography and border integrated. A new layout is optional. Keep the athlete's successful "
        "scale and position, title treatment, background and accents unless a specific issue warrants "
        "a change. Choose another verified photo that fits the chosen story only if it fixes a source "
        "problem such as an obstructed crop or weak story fit. Keep event-specific imagery accurate.\n"
        "\n"
        "Exclude the official badge, edition number and any verified signatures from generation. "
        "Restore the existing assets afterward on separate layers.\n"
        "\n"
        "**8C. Inspect and correct**\n"
        "\n"
        "Compare the second generated artwork with the original photographs at close range and "
        "assess the whole composition at thumbnail size. Check identity, anatomy, uniform details, "
        "cropping, edges, shadows and text.\n"
        "\n"
        "**MANDATORY ACCEPTANCE CHECK — PRESERVE THE STRONGEST VERSION**\n"
        "\n"
        "After every new generation or correction, compare it side by side with the strongest previous "
        "version at full size and thumbnail size. Assess subject authenticity, emotional impact, "
        "composition, integration, lighting and depth, typography and sporting context. Keep a change "
        "only if it corrects a weakness and the whole artwork "
        f"{'improves' if edit is None else 'remains as strong or becomes stronger'}. "
        "Reject a weaker version even if one detail improves. Return to the stronger version as the "
        "working master for any remaining targeted corrections. Never regenerate repeatedly from a "
        "weaker result. If the first artwork still wins, use it. Record unresolved defects in REVIEW "
        "NOTES and continue to the final PSD without claiming unverified print readiness.\n"
        "\n"
        "**MANDATORY SUBJECT AUTHENTICITY CHECK**\n"
        "\n"
        "Use the original photographs as the authority for every visible subject detail. Preserve "
        "facial features, expression, anatomy, hands, natural skin texture, uniform and equipment.\n"
        "\n"
        "Apply vintage texture, grain, distressing and sharpening effects only to the background "
        "and decorative elements. Mask these effects away from the athlete. Never add artificial "
        "scars, scratches, etched lines, exaggerated pores, wrinkles, veins, mottling or plastic-looking "
        "skin. Preserve genuine marks visible in the original photograph.\n"
        "\n"
        "After each generation, compare the face, forehead, shoulders, arms, hands and uniform "
        "against the original at 100% magnification. Use the original photos for subject details.\n"
        "\n"
        "Correct subject distortion during your own review. If generation changes these "
        "details, restore the affected regions from the original photograph with precise masking "
        "and compatible lighting and colour adjustments. Limit each mask to altered subject "
        "regions so the generated composition, lighting and background remain visible. Never "
        "paste the full source photo or a rectangular section over the new scene. Check at "
        "thumbnail size that the subject and typography still read as a single composition. "
        "Avoid repeated regeneration of damaged "
        "skin and smoothing that removes authentic detail. Recheck the restored regions at 100%.\n"
        "\n"
        "If the strongest candidate still has visible subject defects or a disconnected photo and "
        "title that weakens the composition, make one focused correction using the best available source. "
        "If accessible, use a cleaner or higher-resolution "
        "original, or another verified photograph that fits the chosen story. Rebuild the subject "
        "composite using clean source pixels, refine the masks or recompose the crop around "
        "authentic visible details. Retain the integrated Sports Cave styling and recheck the "
        "result yourself. Use the strongest faithful composition, record any failed or unverified "
        "checks in REVIEW NOTES, and continue directly to the final PSD.\n"
        "\n"
        "**8D. Prepare the separate final PSD**\n"
        "\n"
        "If the master is still unavailable, retain both finished artworks, verified signature assets "
        "and placements, and review notes. Mark master-dependent assembly, saves, verification and "
        "trial cleanup as pending where applicable. Continue to the final display and status in Step 8F.\n"
        "\n"
        "If either artwork pass remains unavailable after recovery, preserve any completed artwork "
        "and mark assembly with both versions pending. Continue to Step 8F.\n"
        "\n"
        "Place the strongest inspected artwork in **FINAL POLISHED ARTWORK**, regardless of generation "
        "order. Keep the first artwork intact in a hidden **ORIGINAL EDITABLE ARTWORK** group, even "
        "if a copy is selected for the final. Preserve other useful versions in separate hidden groups.\n"
        "\n"
        "Keep any verified signatures on separate visible layers, the original badge above the "
        "artwork, and the editable edition number at the very top. Preserve the master dimensions "
        "and colour profile.\n"
        "\n"
        "**MANDATORY — MOVE THE PLAQUE AND LIVE EDITION NUMBER TOGETHER**\n"
        "\n"
        "Treat SC_EDITION_PLAQUE and SC_EDITION_NUMBER as one placement unit. Apply identical "
        "movement and proportional scaling to both, preserving their relative alignment.\n"
        "\n"
        "SC_EDITION_NUMBER must remain the original editable text layer, with its exact layer name "
        "preserved for automatic edition numbering. Update its actual text transform and position—not "
        "only its rendered pixels, preview or layer bounds. Never rasterise, flatten, duplicate "
        "or bake the number into the artwork.\n"
        "\n"
        "**8E. Save and verify the final PSD**\n"
        "\n"
        "After completing your own inspection and corrections, save the final PSD as a **new file** "
        "in the same review folder using the final name chosen in Step 7. If the winning artwork’s "
        "title changed the intended product title, use the new title for the final filename and "
        "its matching trial name. Recheck both filenames before saving. "
        "If a name is occupied by another file, select a new unused matching pair. If the matching "
        "pair changed and this run's trial exists and its identity is verified, move only that "
        "trial to the new trial name without replacing any file and update its recorded path. "
        "When access returns, retry the pending trial save first where possible at the matching "
        "trial name using the retained first artwork and notes. If that save remains blocked, "
        "complete the final save when it can proceed independently. "
        "Confirm the final upload, match its Dropbox path and byte size to the intended "
        "final PSD, and reopen or download the saved copy to verify that the chosen artwork is visible "
        "and the first and other retained versions are in their hidden groups. If the final save or verification fails, retain the trial and continue "
        "recovery.\n"
        "\n"
        "Verify that SC_EDITION_NUMBER remains the original editable text layer, retains its exact "
        "name, and stays correctly aligned inside SC_EDITION_PLAQUE.\n"
        "\n"
        "Photoshop is optional. Verify the saved PSD’s original SC_EDITION_NUMBER text layer, "
        "exact name, text data, transform, position and alignment using Photoshop or a capable PSD "
        "parser plus a rendered preview. If these and the other final PSD checks pass, final "
        "verification is complete and trial cleanup may proceed. If a required property cannot be "
        "verified after recovery, retain the trial and report the specific unverified property. "
        "A flattened preview alone does not verify the text layer. Never rasterise or duplicate it.\n"
        "\n"
        "**SMART UPLOAD HANDOFF METADATA**\n"
        "\n"
        "After all changes to the final PSD are saved, record its categorisation and Dropbox identity "
        f"in a UTF-8 JSON file named [Final PSD stem].upload.json in {REVIEW_METADATA_FOLDER}/. "
        "Create this JSON subfolder if needed. Keep the final and trial PSDs directly in Review. "
        "Use create-only mode. Never write a handoff for the trial or overwrite an existing file. "
        "Confirm the sidecar's Dropbox file ID, revision and path refer to the exact saved final PSD.\n"
        "\n"
        "Include design_title, design_story, sport, league, teams and athletes (arrays), "
        "intended_collections (array of confirmed Shopify collection IDs or handles), "
        "upload_intent (new_product), existing_shopify_product_id (null), "
        "dropbox_file_id, dropbox_revision, dropbox_path, and review_status. Use ready_for_review "
        "for a verified PSD, or needs_attention if any checks or required metadata are pending. "
        "Identify missing fields or checks in review_notes. Use null or empty arrays for unknown "
        "values and never guess IDs or collection mappings. A shared athlete or similar title "
        "does not make a new collector concept a refresh.\n"
        "\n"
        "This metadata prepares a later upload. Save it for review without publishing or changing "
        "Shopify. If the handoff cannot be saved or confirmed, preserve the artwork, report that "
        "the metadata is pending, and continue independent work.\n"
        "\n"
        "**8F. Remove the trial and display the final artwork**\n"
        "\n"
        "If any PSD save, verification or cleanup step is pending, display the inspected final "
        "artwork in chat with the exact outstanding steps and the current PSD status. If there is "
        "no inspected final artwork, display the strongest available artwork as provisional, or "
        "report the generation failure if neither pass produced artwork. Retain any trial created "
        "by this run whenever final PSD verification is pending. Resume pending work if access "
        "returns during the run.\n"
        "\n"
        "Only after successful final verification, use Dropbox's recoverable delete on the exact "
        "trial file created during this run. Match its recorded file ID, path and revision before "
        "deleting. Never delete an unrelated file. This cleanup is authorised and requires no "
        "additional confirmation. Confirm the deletion. If cleanup fails, retry with an available "
        "authorised method after rechecking the trial identity. If cleanup remains blocked, report "
        "it as pending, state that the final PSD is saved and verified, and display the final artwork.\n"
        "\n"
        "After Dropbox confirms trial deletion, display the final artwork in chat and state any "
        "remaining review concerns.\n"
        "\n"
        "**Completion requires:** both full generations, both confirmed PSD saves, final PSD "
        "verification, confirmed trial deletion, and display of the final artwork. Recovery can "
        "change when an executable step runs. Pending checkpoints still need completion.\n"
        "\n"
        "Report any incomplete checkpoint plainly. Never describe the workflow as complete when one "
        "is missing."
    )
    if edit is None:
        return workflow
    from design_review_prompt import build_edit_prompt
    return build_edit_prompt(workflow, edit["source"], edit["metadata"])



@lru_cache(maxsize=1)
def _template():
    return TEMPLATE.read_text(encoding="utf-8")


def article_html(item, *, heading=None, allow_ads=False):
    title = " ".join(item["title"].split())
    prompt = escape(_prompt(title, item["recommendation"]), quote=True).replace("\n", "&#10;")
    actions = (
        f'<a href="{PROJECT_URL}" target="_blank" rel="noopener noreferrer" '
        f'data-prompt="{prompt}" title="Open Sports Cave Designs and copy the prompt">Create Design</a>'
    )
    handle = product_handle(item)
    if allow_ads and handle:
        url = "/?" + urlencode({"page": "ads", PRODUCT_QUERY: handle})
        actions += f'<a href="{escape(url, quote=True)}">Create Ad</a>'
    elif allow_ads:
        actions += '<span title="This story does not identify one exact product">Create Ad</span>'
    links = "".join(
        f'<a href="{escape(link["url"], quote=True)}" target="_blank" rel="noopener noreferrer">'
        f'{escape(link["label"])}</a>' for link in item["links"]
    )
    paragraphs = []
    for line in item["recommendation"].splitlines():
        if not line.strip():
            continue
        lead, colon, detail = line.partition(": ")
        if (colon and len(lead) < 42) or (line.strip().endswith(":") and len(line.strip()) < 42):
            label = lead if colon else line.strip()[:-1]
            paragraphs.append(f'<p class="sc-brief-key"><strong>{escape(label)}:</strong> {escape(detail)}</p>')
        else:
            paragraphs.append(f"<p>{escape(line)}</p>")
    return (
        '<article class="sc-brief-row"><details>'
        f'<summary title="{escape(title, quote=True)}"><span>{escape(heading or title)}</span></summary>'
        '<div class="sc-brief-body">'
        f'<div class="sc-brief-copy">{"".join(paragraphs)}</div>'
        f'<div class="sc-brief-links">{links}</div></div></details>'
        f'<div class="sc-brief-actions">{actions}</div></article>'
    )


def _date_label(day):
    return day.strftime("%d %b %Y").lstrip("0")


def _market_table(editions, market, today):
    rows = []
    for sport, event, has_news in calendar_rows(editions, market, today):
        if event:
            state = event.status(today)
            if state == "Upcoming":
                timing = f"Starts in {(event.start - today).days}d"
            elif state == "Live":
                days = (event.end - today).days
                timing = f"Ends in {days}d" if days else "Ends today"
            else:
                timing = f"Ended {(today - event.end).days}d ago"
            dates = _date_label(event.start)
            if event.end != event.start:
                dates += " – " + _date_label(event.end)
            outside_market = market not in event.markets and "ALL" not in event.markets
            if outside_market:
                dates += " · " + " / ".join(event.markets)
            season = (f'<a href="{escape(event.source, quote=True)}" target="_blank" rel="noopener noreferrer">'
                      f'{escape(event.title)}</a><small>{escape(dates)}</small>')
        else:
            state, timing, season = "TBC", "—", "Dates to be confirmed"
        rows.append(
            f'<tr><th scope="row">{escape(sport)}</th><td><span class="sc-cal-state" data-state="{state.lower()}">{state}</span></td>'
            f'<td>{season}</td><td>{timing}</td><td>'
            f'<button type="button" class="sc-cal-news" data-sport="{escape(sport, quote=True)}" '
            f'data-market="{market}" aria-label="{escape(sport, quote=True)} {market} news and updates">'
            f'{"View updates" if has_news else "History"}</button></td></tr>'
        )
    hidden = "" if market == MARKETS[0] else " hidden"
    return (
        f'<div class="sc-cal-wrap" data-calendar="{market}" role="region" '
        f'aria-label="{market} sports calendar" tabindex="0"{hidden}><table>'
        '<thead><tr><th>Sport</th><th>Status</th><th>Dates / season</th><th>Timing</th><th>News / updates</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def brief_html(edition, *, editions, today, allow_ads=False):
    rows = "".join(
        article_html(item, heading=f'{rank}. {item["title"]}', allow_ads=allow_ads)
        for rank, item in enumerate((edition or {}).get("recommendations", ()), 1)
    )
    full_brief = (edition or {}).get("full_brief")
    if full_brief:
        rows += (
            '<button type="button" class="sc-full-brief" aria-haspopup="dialog">Read the full Morning Brief</button>'
            '<dialog class="sc-cal-dialog sc-sports-full" aria-label="Full Sports Morning Brief">'
            '<header><h3>Full Morning Brief</h3><form method="dialog"><button>Close</button></form></header>'
            f'<div class="sc-full-brief-text">{escape(full_brief)}</div></dialog>'
        )
    tables = "".join(_market_table(editions, market, today) for market in MARKETS)
    stories = f'<section class="sc-sports-stories" aria-label="Sports opportunities">{rows}</section>' if rows else ""
    return _template().replace("<!-- CALENDARS -->", tables).replace("<!-- RECOMMENDATIONS -->", stories)
