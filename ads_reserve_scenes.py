"""Conditional scene specifications; never extra deliverables or safety retries."""

VERSION = "SPORTS CAVE TWO CONDITIONAL RESERVE SCENES V2"
CHECKPOINT = """4a. Before final review, CSV export or SC_AD_BLOCKED, complete the mandatory reserve-room checkpoint below for this three-cover Instant Experience task. Inspect each original call result. For each missing slot with an explicitly retryable technical failure, automatically execute its allocated unused Reserve A/B now, without asking for approval. A missing image alone is not proof of a technical failure. Preserve successful images; recover uncertain assets. Safety/moderation and unexplained rejections are ineligible and must not be retried through another room. Record the actual reason and reserve outcome for each remaining missing slot; never end early with an eligible reserve still unused."""
RULES = f"""RESERVE ROOMS — TECHNICAL FAILURES ONLY
{VERSION}
Applies only to a three-cover Instant Experience task, never Carousel or Single Image.
These are two dormant replacement specifications, not instructions to generate
Ad 4 or Ad 5 in a successful pack. Complete the three initial assigned calls
first, preserving successful outputs and finishing independent unattempted slots.
If all three images exist, skip this entire reserve section and continue the
existing final review, three-image export, CSV and Companion handoff unchanged.

ELIGIBILITY AND ALLOCATION
This is a required execution checkpoint, not an optional suggestion when eligible.
After all three original calls have been attempted, inspect the result of EACH
slot before final review, CSV export or a blocked completion response. Continue
independent unattempted original slots after a failure; never abandon the pack
at the first failed call. Do not ask the user to choose a reserve or approve it.
An original slot is eligible only when its call produced no image and the
provider explicitly identifies a retryable technical failure. An ambiguous
result requires recovery/inspection of the existing call result first.
A safety rejection, moderation_blocked result or unexplained rejection never
authorizes a reserve room, reworded retry or substitute generation. Preserve
those completed outputs and copy and report the provider's actual reason.
A downloaded/display error requires recovery of the existing bytes, not another
image generation. Never change a reference or rewrite a prompt to evade a block.

After the initial three attempts, order eligible missing slots by Ad 1/2/3.
Use Reserve A for the first eligible missing slot. Use Reserve B only if a
second distinct original slot has an eligible failure. At most one reserve-room
attempt per eligible missing slot, at most two reserve attempts in the pack.
Execute each allocated eligible reserve now, then inspect its actual result;
do not merely describe the fallback or report a technical blocker before using
its available reserve. A single eligible slot uses A only. Two use A then B
for different slots in original slot order. Three eligible failures still permit
only A and B; report the third missing slot after those attempts.
Do not use Reserve B as another retry for Reserve A's slot. Do not reset this
budget on review, reopen or resume, use a reserve to replace a successful slot, or restart
the set. If a reserve also fails, retain every completed file and report the
remaining missing slot honestly using the existing incomplete-delivery marker.

RESERVE A — REQUIRED WHEN FIRST SLOT IS ELIGIBLE: COLLECTOR MAN CAVE
A premium private residential collector man cave, with believable warm directional
light and quiet tactile walls. The supplied framed edition remains the main
piece and unmistakable hero. At the distant edge or on a peripheral background
wall, include one or two small, softly out-of-focus hanging sports keepsakes;
keep them subdued, secondary and without readable invented claims, signatures
or certificates. No competing hero artwork, clutter or themed sports-bar layout.
Choose a different residential composition, wall treatment and lighting from
the completed covers while preserving the missing slot's assigned camera role,
physical product scale, complete frame and visible glazing.

RESERVE B — REQUIRED WHEN SECOND SLOT IS ELIGIBLE: DARK COLLECTOR STUDIO APARTMENT
A premium dark-themed residential studio apartment with a restrained masculine
collector aesthetic, quiet deep-toned wall, subtle leather/timber details and
soft practical/window light. A compact sofa or desk may appear only at the
periphery. Keep the supplied framed edition the main piece, legible and tonally
separated from the wall, with believable reflections and architectural depth.
This is a home, not a black void, showroom or sports bar. Make its composition
distinct from completed covers and Reserve A; retain the missing slot's camera
role, scale, complete frame and original framed-product reference.

UNCHANGED CONTRACT FOR EITHER REPLACEMENT
For the eligible missing slot only, combine the ORIGINAL product reference,
existing shared image requirements and that slot's exact resolved specification;
replace only its room/scene description with its allocated reserve scene above.
Do not pass the unused reserve or sibling instructions into the image call.
Retain its camera role, product scale, footer wording, route identity, filename
and CSV row. Keep the assigned 100-variation title, two-line footer, exact second
line and complementary written Meta headline; never reroll their saved split.
Preserve Baseline 2.0 typography, 160 px opaque black footer, gold shimmer,
1024 × 1024 sRGB JPEG, product fidelity, glazing, targeting and copy framework.
Label/save the result as the ORIGINAL missing Ad 1/2/3 slot, not as Ad 4/5.
Reuse completed images. Deliver three final covers, never an additional fourth
cover or fifth deliverable. Export the same three-row ad_copy.csv and continue
the existing review, attachments, completion markers and Companion workflow.
If fewer than three covers can actually be completed, preserve all successes
and copy records and identify the incomplete slot; never claim three images
or emit a successful completion marker for a two-image package.

INCOMPLETE DELIVERY EVIDENCE
Before SC_AD_BLOCKED, attach every available successful original and the existing
CSV. Include a concise table for each missing filename: original slot, exact
provider error code/message, request ID and stage when supplied, whether a
reserve was eligible, which reserve was attempted and its actual outcome, or
the precise reason no reserve was allowed. Say "not supplied" for absent provider
details. Never invent a technical cause, infer that the room caused moderation,
or suggest that another room would resolve a safety rejection. For moderation,
state explicitly: reserve not attempted because the provider rejected generation;
the reserve-room rule covers retryable technical failures only.
"""
