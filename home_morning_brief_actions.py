"""Compact recommendation rows and their ChatGPT project handoff."""

from functools import lru_cache
from html import escape
from pathlib import Path
import re
from urllib.parse import urlencode

from home_brief_calendar import MARKETS, PRODUCT_QUERY, calendar_rows, product_handle

PROJECT_URL = "https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project"
TEMPLATE = Path(__file__).parent / "components" / "morning_brief_actions.html"


META_AD_HEADING = re.compile(r"^(?:recommended|suggested)\b.*\bmeta\b.*\bad\b", re.I)
META_AD_COPY = re.compile(r"^(?:headline|primary text|description|cta|call to action)\s*:", re.I)


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


def _prompt(title, story):
    context = _story_without_meta_ad(story)
    return (
        f"Sports Cave event: {title}\n\n"
        "**MANDATORY EXECUTION ORDER**\n"
        "\n"
        "This task requires **two distinct full-artwork image generations and two confirmed Dropbox "
        "saves**:\n"
        "\n"
        "**Generate and inspect first complete artwork → confirm trial PSD save → regenerate and "
        "inspect complete artwork → confirm and verify new final PSD → confirm trial deletion → "
        "display final artwork.**\n"
        "\n"
        "Do not combine, skip or reorder these checkpoints. Saving once at the end does not satisfy "
        "this workflow. Generating only a background and manually placing the athlete over it does "
        "not satisfy the second full-artwork generation.\n"
        "\n"
        "**MANDATORY CONTINUATION AND RECOVERY**\n"
        "\n"
        "Execute the entire workflow autonomously. Do not stop for ordinary design imperfections, "
        "low-resolution search results, unsuccessful generations, missing signatures or a failed "
        "first attempt.\n"
        "Perform every design review and correction yourself. Continue from the trial save "
        "through the final save, verification, cleanup and display without waiting for approval "
        "or a manual review. REVIEW NOTES inform your corrections and final report.\n"
        "\n"
        "**Quality concerns require corrective action.** Search for higher-resolution originals, "
        "inspect the source pages, choose a stronger photograph from the same event, adapt the "
        "composition to the available crop, or regenerate. Do not invent missing anatomy or "
        "quietly substitute another event.\n"
        "\n"
        "**The first Dropbox save is a review checkpoint, not final production approval.** After "
        "generating and inspecting the first complete artwork, save it on a copy of the master PSD "
        "in the specified review folder. Document remaining concerns in a hidden `REVIEW NOTES` "
        "layer. Those concerns must guide the mandatory second full-artwork generation after "
        "Dropbox confirms the first save.\n"
        "\n"
        "Do not demand perfection before the first save. Do not describe a review draft as approved "
        "or print-ready.\n"
        "\n"
        "**After Dropbox confirms the trial save, continue immediately to Step 8 without asking permission.** "
        "Generate the complete artwork again using the first artwork and original photographs, "
        "inspect it, make necessary corrections, and save it as a separate final PSD. Preserve the "
        "first artwork in the final PSD's hidden `ORIGINAL EDITABLE ARTWORK` group.\n"
        "\n"
        "**Recover from tool failures.** Retry recoverable failures appropriately and use another "
        "available, authorised method when necessary, including the connected Dropbox browser. "
        "If a save response is uncertain, reconcile it against the intended Dropbox path and "
        "saved file identity and contents before retrying. Keep the trial until the final PSD "
        "is verified.\n"
        "\n"
        "**Missing signatures must not stop the artwork.** Complete the minimum three-source "
        "search and the reference and extraction checks in Step 4 before omitting a signature. "
        "Never generate or redraw a signature.\n"
        "\n"
        "A blocker in a later step must not stop earlier executable steps. Complete the first "
        "full-artwork generation, inspection and trial PSD save before addressing final-stage "
        "verification limitations. Stop at the first genuinely blocked operation after trying "
        "reasonable alternatives, preserve completed progress, and continue any independent work "
        "that remains possible. A design concern calls for "
        "correction or a source-based fallback and is not a reason to stop. Identify the exact failed "
        "operation, attempts made, saved progress and smallest action needed to resume. Never claim "
        "an unperformed generation, save, verification or deletion succeeded.\n"
        "\n"
        f"{context}\n\n"
        "Choose dates, statistics and achievement text according to the edition’s story. Never include "
        "them automatically.\n"
        "\n"
        "Before designing, ask: “Would this detail still help a fan understand and value this artwork "
        "five years from now?”\n"
        "\n"
        "1. **Legacy, GOAT, rivalry and identity editions:** default to a meaningful title and subject "
        "names. Add career years or achievements only when they materially strengthen the story.\n"
        "2. **Championships, iconic memories, farewells and historic events:** include the year when it "
        "identifies the achievement or era. Use a full date only when that exact day is central to the "
        "memory; otherwise place it in the product description or certificate.\n"
        "3. **Records and exceptional performances:** retain the verified statistic or concise group of "
        "statistics that makes the moment significant. Omit routine results and unrelated numbers.\n"
        "4. **Avoid information that becomes outdated:** do not use current age, live rankings, ongoing "
        "season averages or changing career totals as timeless legacy claims. If essential, explicitly "
        "anchor them to the relevant season or completed event. Describe records as achievements at that "
        "event, rather than implying they can never be surpassed.\n"
        "5. **Keep the hierarchy restrained:** subject first, collector title second, name and essential "
        "context next, official collector details last. Normally use no more than one concise "
        "achievement/statistics line and one discreet date/event line. These are maximums, not required "
        "fields.\n"
        "6. **Use meaningful headlines:** evoke the sporting story without sounding like a news headline "
        "or advertisement. Avoid “latest,” “today,” “this season” and unsupported greatness claims.\n"
        "7. **Do not remove a meaningful date merely because it is recent.** Do not add a date merely "
        "because the subject is historic. Preserve context when it creates collector value.\n"
        "\n"
        "List the best possible images. Show the photos in this chat first. Use web image search to "
        "aim for 4–8 images from the event. If fewer are usable after checking the original source "
        "pages, show the candidates that meet the Step 1 standard. Focus on photo authenticity, image "
        "quality, and how each photo supports the artwork. I will handle photo licensing "
        "separately. Do not research, assess, or mention photo licensing, commercial-use "
        "permissions, or usage rights.\n\n"
        "**STORY-FIRST IMAGE SELECTION**\n"
        "\n"
        "Use these cues within the existing image search. Start with the title and the exact "
        "sporting moment or emotional reason to own the artwork. Search the named achievement, "
        "gesture, event or era alongside the subject. Where available, compare distinct authentic "
        "action, celebration, achievement and identity photos within the event shortlist. "
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
        "standard, search original galleries and alternate sources even if the shortlist is small. "
        "Keep an individual tribute centred on that athlete. Use one strong hero photograph when "
        "it tells the story on its own. If a second photo adds distinct value, use it as subordinate "
        "background imagery. Place the selected hero in the artwork. Preserve "
        "recognisable faces, uniforms, and event details. Follow the project’s Collector Series "
        "references for typography, colour, depth, and visual hierarchy. Refer to the project "
        "instructions in Sports Cave Designs for how Sports Cave designs are structured.\n\n"
        "Step 2. Inspect designs-canvas.psd in Dropbox for the exact pixel dimensions, orientation, "
        "safe margins, and limited-edition badge. Preserve the "
        "original limited-edition badge and edition-number layer.\n\n"
        "Step 3. Define the composition for a realistic Sports Cave Collector Series design with "
        "a strong focal point and clear visual hierarchy.\n\n"
        "Step 4. For each featured person, search both web and image results. Check at least "
        "three distinct credible sources before skipping a signature. Use a clear, verified "
        "example and place it on a separate layer where it fits naturally with the artwork "
        "and typography. Keep the original letterforms and strokes. Refine the placement, "
        "scale, and ink finish for a premium collector look. A textured background alone is no "
        "reason to omit an autograph. Search for a clearer flat reference, download and inspect "
        "the strongest authentic candidates, and attempt a faithful extraction that preserves "
        "the original strokes. Three sources is the minimum. A page without a signature image "
        "counts as a search result only. If extraction fails on a genuine example, search beyond "
        "the first three sources for alternate photographs or scans of that autograph or other "
        "verified signed items. Download and inspect the strongest alternatives and attempt "
        "extraction before omitting it. If the best verified source is low resolution but the strokes "
        "can be faithfully extracted, use it on a separate layer in the final collector design. "
        "Improve legibility with precise masking, contrast, and a suitable display size and ink "
        "finish. Keep all original stroke shapes and gaps. Never generate, redraw, or reconstruct "
        "the signature or fill in missing strokes. Omit it only after the search and extraction "
        "attempts fail. Record the sources checked, extraction attempted, and exact reason it "
        "failed in REVIEW NOTES, and continue.\n\n"
        "Step 5. Use the image generation tool to generate the first complete Sports Cave "
        "Collector Series artwork. Build a cohesive vintage background with subtle textures "
        "and details from the sport or venue and restrained team colours. Keep vintage texture, "
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
        "Use the same Dropbox review folder for both files at /Sportscave Team Folder/"
        "02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/. "
        "Check both names before saving. If either exists, choose an unused matching version "
        "suffix for both, such as `[Product Title] - v2 - TRIAL.psd` and "
        "`[Product Title] - v2.psd`. Create files without replacing existing files. "
        "Confirm the save and continue immediately to Step 8.\n\n"
        "**STEP 8 — REQUIRED SECOND FULL-ARTWORK GENERATION, AFTER THE FIRST DROPBOX SAVE**\n"
        "\n"
        "**Entry requirement:** Dropbox must have confirmed the trial save in Step 7. Record the "
        "trial file ID, path and revision from that save for exact cleanup after final verification.\n"
        "\n"
        "**8A. Re-read and review**\n"
        "\n"
        "Re-read `SPORTS-CAVE-LIMITED-EDITION-COLLECTOR-DESIGNS.txt`. Inspect the first complete "
        "artwork against the original photographs and use REVIEW NOTES to prioritise corrections. "
        "Identify specific improvements to composition, "
        "subject scale, integration, lighting, typography and border treatment.\n"
        "After Dropbox confirms the trial save and before the second generation, find the matching "
        "sport or collection on the Sports Cave storefront. Use authorised Shopify sales reports "
        "in read-only mode to identify bestsellers or recent trending sellers within that category. "
        "Open the matching storefront product pages and visually inspect the actual artwork for "
        "subject integration, lighting, typography, depth and border treatment. Apply those style "
        "cues to a unique composition using this trial's title and hero subject. Use the artwork "
        "images as style inputs where supported. If Shopify sales data is unavailable, use verifiable "
        "storefront bestseller listings or approved project references and record the source in "
        "REVIEW NOTES. Treat unranked products as style references only. If reference images are "
        "inaccessible, record the gap and continue using the Sports Cave design rules.\n"
        "\n"
        "**8B. Second generation — new composition, authentic subject**\n"
        "\n"
        "**Sports Cave design rules for every final generation**\n"
        "\n"
        "Give fans a specific reason to display the artwork. Make the sporting moment, rivalry, "
        "era, team identity or personal legacy immediately recognisable. Use the strongest original "
        "photograph to establish the subject and story. Add supporting imagery only when it adds "
        "meaning. Verify any factual text before including it. For an upcoming event, depict it as "
        "a preview and reserve victory imagery for verified outcomes.\n"
        "\n"
        "Choose one primary composition that suits the story and source photographs:\n"
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
        "perspective. Use natural contact shadows and keep glow, sparks, smoke and haze restrained. "
        "Choose backgrounds that convey setting, era or emotion.\n"
        "\n"
        "Work to the master PSD's aspect ratio and safe area. Give the subject or sporting moment "
        "visual priority, followed by the collector title and essential context. Use a short, "
        "story-specific title in elegant serif or restrained cinematic type, with smaller tracked "
        "uppercase text where appropriate. Follow the existing date and statistics rules. Use a "
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
        "- The first complete artwork for the intended title, factual wording, story and subject. "
        "Design a new layout.\n"
        "- The original photographs for identity, expression, anatomy, pose, uniform and equipment. "
        "Redesign the setting and remove distracting surrounding players where appropriate. Use "
        "the category references to guide the visual treatment.\n"
        "\n"
        "Generate a visibly different **complete Sports Cave collector artwork** with the subject, "
        "purposeful setting, lighting, refined typography and border integrated in one composition. "
        "Give the named subject stronger visual dominance and use restrained depth. Isolate, "
        "reposition or proportionally resize the authentic subject where the source supports it. "
        "Build the title into the scene's negative space and avoid a rectangular photo above a "
        "separate title panel. Choose another verified photo from the same event if the crop "
        "or obstruction hides anatomy needed for the composition.\n"
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
        "**MANDATORY ACCEPTANCE CHECK**\n"
        "\n"
        "Compare the second artwork side by side with the trial. Reject cosmetic changes that "
        "retain essentially the same subject arrangement, title placement and background. The "
        "named subject must dominate at thumbnail size, the title must match the image, and the "
        "composition must visibly improve on the trial. If any check fails, correct the layout "
        "or regenerate with a different composition and check again yourself before saving.\n"
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
        "If the first restoration leaves defects or the second pass still looks like a photo "
        "above a title panel, continue correcting it. Find a cleaner or higher-resolution "
        "original, or another verified photograph from the same event. Rebuild the subject "
        "composite using clean source pixels, refine the masks or recompose the crop around "
        "authentic visible details. Retain the integrated Sports Cave styling and recheck the "
        "result yourself. Both full-artwork generations are required. Photographic restoration "
        "is an authorised finishing step after generation. Use the best faithful composition "
        "that meets the acceptance check. Record remaining limitations in REVIEW NOTES and "
        "continue directly to the final PSD.\n"
        "\n"
        "**8D. Prepare the separate final PSD**\n"
        "\n"
        "Place the inspected second artwork in **FINAL POLISHED ARTWORK**. Keep the first artwork "
        "intact in a hidden **ORIGINAL EDITABLE ARTWORK** group.\n"
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
        "in the same review folder using the final name "
        "chosen in Step 7. If that name becomes occupied by another file, select a new unused "
        "matching pair and move only this run's trial to the new trial name without replacing "
        "any file. Verify the moved trial's identity and update its recorded path before saving "
        "the final. Confirm the final upload, match its Dropbox path and byte size to the intended "
        "final PSD, and reopen or download the saved copy to verify its contents, including both "
        "artwork versions. If the final save or verification fails, retain the trial and continue "
        "recovery.\n"
        "\n"
        "Verify that SC_EDITION_NUMBER remains the original editable text layer, retains its exact "
        "name, and stays correctly aligned inside SC_EDITION_PLAQUE.\n"
        "\n"
        "Use Photoshop when available. Otherwise, inspect the saved PSD’s text-layer data, transform, "
        "position and rendered preview using available PSD tools. Do not rasterise or duplicate the "
        "number.\n"
        "\n"
        "If interactive text editing cannot be tested, record “Photoshop live-number check pending” "
        "in REVIEW NOTES. Complete all other generation, save and verification steps. Retain the "
        "trial until this remaining check passes, and clearly report the final PSD as awaiting that "
        "check.\n"
        "\n"
        "A missing application or a later verification limitation must not prevent earlier executable "
        "steps or independent work from being completed. A flattened preview alone does not verify "
        "the text layer. Correct any mismatch before calling the final PSD verified.\n"
        "\n"
        "**8F. Remove the trial and display the final artwork**\n"
        "\n"
        "If the Photoshop live-number check is pending, retain the trial and display the final "
        "artwork in chat with the final PSD status and outstanding check. Resume cleanup only "
        "after that check passes.\n"
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
        "**Completion requires:** first generation → confirmed trial save → second full generation "
        "→ confirmed and verified final save → confirmed trial deletion → display final artwork.\n"
        "\n"
        "Report any incomplete checkpoint plainly. Never describe the workflow as complete when one "
        "is missing."
    )


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
