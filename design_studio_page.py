import hashlib
import html
import json
import os
import textwrap
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from activity_log import record_activity_log
import prompt_store


DEFAULT_DEVELOPER_PAGE_PASSWORD = os.getenv("DEVELOPER_PAGE_PASSWORD", "sportscave1993")
BASE_DIR = Path(__file__).resolve().parent
EXPIRED_EDITION_NEXT_CHAPTER_PROMPT_PATH = (
    BASE_DIR / "design_studio_prompts" / "expired_edition_next_chapter_prompt.txt"
)


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

Use the searched images as realism and accuracy references.

Do not blindly copy a random photo.
Use the best references to improve likeness, lighting, pose accuracy, jersey accuracy, car accuracy, facial realism, and emotional authenticity.

If the uploaded design already has a strong subject pose, keep the same general pose and emotion, but rebuild it with more realistic detail.

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

Where appropriate, include a subtle signature-style graphic.

Only use a signature if it improves the memorabilia feeling.

Place it naturally in:

Dark sky
Background shadows
Near the title
Near the subject
Near the collector plaque
Empty negative space

The signature should feel authentic, subtle, and premium.

Do not make it oversized.
Do not put it in a box unless it looks like part of a premium memorabilia plate.
Do not use fake-looking random scribbles that distract from the design.

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

Use the uploaded design as the core reference, but rebuild it into a darker, more cinematic, more realistic, more emotional, more premium limited-edition collector piece.

Use better realistic source references from web/image search where needed.

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

Analyse the task above deeply and conduct current web research before recommending any creative direction.

Your job is to verify the subject, identify the strongest commercial angle, and build a clear research brief for a realistic, premium, bestselling Sports Cave limited-edition collector artwork.

RESEARCH THE SUBJECT

Identify and verify:

- The athlete, driver, team, rivalry, event or sporting moment
- Why the subject matters to fans
- The strongest emotional and nostalgic angle
- The correct era, season and location
- Accurate uniforms, race liveries, cars, equipment and colours
- Correct stadium, circuit, arena, pitch, course or background
- Correct trophies, medals and historical details
- The strongest country markets for the product
- Any current event or calendar reason the design is commercially relevant now
- Whether the proposed title and concept are strong enough to sell

RESEARCH OUTPUT

Provide:

- Recommended collector title
- Core fan emotion
- Verified subject, era, event and location
- Why the concept matters to fans
- Why it is commercially relevant now
- Strongest country markets
- Accurate visual details that must appear
- Historical details that must not be shown incorrectly
- Best hero-subject direction
- Best venue, track, stadium or background direction
- Important supporting details such as a trophy, car or equipment
- Any factual, historical or copyright risks
- A concise image-search brief for the next step

The final direction must feel:

- Realistic
- Premium
- Cinematic
- Minimal but emotionally powerful
- Nostalgic or culturally relevant
- Framed-first
- Collector-driven
- Suitable for a landscape 4:3 artwork
- Strong enough to become a Sports Cave bestseller

Be commercially honest.

If the task is weak, historically inaccurate or unlikely to sell, say so and recommend a stronger angle.

Use current web research, but do not find or display images yet.

Do not generate the final artwork yet.

Stop after completing the research brief.
"""


DESIGN_IMAGE_CAROUSEL_PROMPT_TEMPLATE = """
TASK

[PASTED TASK]

RESEARCH ANSWER

[PASTED RESEARCH ANSWER]

Use the task and completed research above only to find the strongest, most accurate visual references for this Sports Cave design.

Search the web and display approximately 10-12 strong images directly in this ChatGPT conversation as an image carousel.

Do not give me a text-only list of links.
Do not provide a new research report or creative direction.
Do not analyse, rank or recommend the images.
Do not generate the final artwork.

The carousel must include:

- 3-4 potential hero-subject images
- 2-3 action or emotional-moment images
- 2-3 venue, track, stadium or atmospheric background images
- 1-2 important supporting details such as a trophy, car, equipment or historical scene

Only show images that are:

- Highly relevant to the exact task and research
- Visually powerful
- Realistic and historically accurate
- Clear enough to guide a premium artwork
- Useful for a landscape 4:3 composition
- Strong enough to support a Sports Cave bestseller
- Free from obvious AI errors or factual inaccuracies

Do not introduce athletes, vehicles, clothing, trophies, locations or details belonging to a different product.

Under each image, add only a short label identifying its purpose, such as Hero, Action, Background or Detail.

This step is only for finding and displaying images.

Stop after the image carousel.
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

Signature and Memorabilia Feel

Where suitable, include a subtle signature-style graphic.

The signature should feel like memorabilia, not decoration.

Place it in a natural empty area:

sky
dark background
near the subject
near the title

Do not make it too large or distracting.

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

Use the selected hero image as the main subject reference.
Use the selected background/support image as the atmosphere and story reference.
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


HARSH_REVIEW_PROMPT = """
Give me a harsh truth review of this Sports Cave design.

Rate it out of 10 as a premium limited-edition collector artwork.

I want brutal honesty.

Tell me:

1. What still feels weak
2. What still feels too AI, too generic, or too cheap
3. Whether the composition feels premium and intentional
4. Whether fans would actually buy this and hang it proudly
5. Whether the background adds nostalgia and depth or just noise
6. Whether the title feels iconic or generic
7. Whether the limited-edition plaque feels properly placed
8. Whether the subject looks realistic and physically present
9. Whether the design feels framed-first and wall-worthy
10. What exact changes are needed to make this as close to 10/10 as possible

Do not be polite.
Be commercially honest.
Judge it like it needs to become a bestseller.

Rule:
Do not stop just because it looks good enough.
Refine until it feels premium, emotional, collector-worthy, and ready to sell.
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


def _clean_prompt(prompt):
    return textwrap.dedent(prompt).strip()


def _task_or_placeholder(task_text: str) -> str:
    task = str(task_text or "").strip()
    return task if task else "[PASTED TASK]"


def build_design_research_prompt(task_text: str) -> str:
    return _clean_prompt(DESIGN_RESEARCH_PROMPT_TEMPLATE).replace(
        "[PASTED TASK]",
        _task_or_placeholder(task_text),
    )


def build_design_image_carousel_prompt(task_text: str, research_answer: str) -> str:
    research = str(research_answer or "").strip() or "[PASTED RESEARCH ANSWER]"
    return (
        _clean_prompt(DESIGN_IMAGE_CAROUSEL_PROMPT_TEMPLATE)
        .replace("[PASTED TASK]", _task_or_placeholder(task_text))
        .replace("[PASTED RESEARCH ANSWER]", research)
    )


def build_design_generation_prompt(task_text: str) -> str:
    task = _task_or_placeholder(task_text)
    intro = f"""
From the research and images above you found, create me a premium Sports Cave limited-edition collector artwork for this task:

TASK

{task}

Use the selected hero image, background/support image, detail references and creative direction from the research above. Continue with this Sports Cave design system:
"""
    return f"{_clean_prompt(intro)}\n\n{_clean_prompt(SPORTS_CAVE_MASTER_DESIGN_SYSTEM_PROMPT)}"


def _design_studio_prompt_id(key: str) -> str:
    return f"design-studio::{key}"


def _developer_password_matches(password: str, developer_password: str | None) -> bool:
    expected_password = developer_password if developer_password is not None else DEFAULT_DEVELOPER_PAGE_PASSWORD
    return str(password or "") == str(expected_password or "")


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


def _render_prompt_editor(label: str, prompt_id: str, prompt_text: str, key: str, developer_password: str | None, default_text: str | None = None):
    editor_key = f"design-studio-edit-open::{key}"
    if not st.session_state.get(editor_key):
        return

    with st.container(border=True):
        source_record = prompt_store.get_prompt_source(
            prompt_id,
            prompt_text,
            prompt_name=label,
            module="design_studio",
        )
        st.caption(f"Developer only. {source_record.get('source_label')}")
        if source_record.get("warning"):
            st.warning(source_record["warning"])
        edited_prompt = st.text_area(
            "Edit prompt",
            value=prompt_text,
            height=460,
            key=f"design-studio-edit-text::{key}",
        )
        password = st.text_input(
            "Developer password",
            type="password",
            key=f"design-studio-edit-password::{key}",
        )
        save_col, cancel_col, _ = st.columns([1, 1, 4])
        if save_col.button("Save", key=f"design-studio-edit-save::{key}", use_container_width=True):
            if not edited_prompt.strip():
                st.error("Prompt cannot be empty.")
            elif not _developer_password_matches(password, developer_password):
                st.error("Developer password is incorrect.")
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
    developer_password: str | None = None,
):
    prompt_id = _design_studio_prompt_id(key)
    effective_prompt = prompt_store.get_prompt(prompt_id, _clean_prompt(default_prompt_text))
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

    _render_prompt_editor(
        label,
        prompt_id,
        effective_prompt,
        key,
        developer_password,
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
        "2. Paste the research answer into Step 2, then run the Find Images Prompt in the same chat.\n"
        "3. Once the image carousel is shown, run the Design Generation Prompt in the same chat."
    )
    st.markdown("### Step 1 - Research")
    task_text = st.text_area(
        "Paste design task",
        placeholder='Paste a task from "New designs to complete" here...',
        height=110,
        key="design-studio-task-research-input",
    )
    research_prompt = build_design_research_prompt(task_text)
    render_generated_prompt_box(
        "Research Prompt",
        research_prompt,
        "design-research",
        "Copy Research Prompt",
        height=340,
    )
    st.divider()

    st.markdown("### Step 2 - Find Images")
    research_answer = st.text_area(
        "Paste research answer",
        placeholder="Paste the complete research answer from ChatGPT here...",
        height=150,
        key="design-studio-research-answer-input",
    )
    image_prompt = build_design_image_carousel_prompt(task_text, research_answer)
    render_generated_prompt_box(
        "Find Images Prompt",
        image_prompt,
        "design-image-carousel",
        "Copy Find Images Prompt",
        height=340,
    )
    st.divider()

    st.markdown("### Step 3 - Generate Design")
    design_prompt = build_design_generation_prompt(task_text)
    render_generated_prompt_box(
        "Design Generation Prompt",
        design_prompt,
        "design-generation-from-research",
        "Copy Design Generation Prompt",
        height=420,
    )


def _render_prompt_box(name, prompt, key, developer_password):
    render_copy_prompt_box(name, prompt, key, developer_password)


def render_design_studio_page(developer_password: str | None = None):
    st.title("Design Studio")
    st.caption("Sports Cave prompt hub for premium collector artwork.")

    upgrade_tab, research_tab, expired_tab, create_tab, review_tab = st.tabs(
        [
            "Upgrade Existing Design",
            "New Design",
            "Update Expired Edition",
            "Create New Ultimate Moment",
            "Harsh Review Checklist",
        ]
    )

    with upgrade_tab:
        st.subheader("Upgrade Existing Sports Cave Design")
        with st.expander("How To Upgrade an Existing Sports Cave Design"):
            st.markdown("Watch this quick guide before upgrading a design.")
            st.video(UPGRADE_EXISTING_DESIGN_VIDEO_URL)
            st.caption(
                f"If the video does not load, open it here: {UPGRADE_EXISTING_DESIGN_VIDEO_URL}"
            )
            st.markdown(
                "1. Screenshot the current Sports Cave design.\n"
                "2. Open ChatGPT.\n"
                "3. Go to the \"Sports Cave Designs\" project/folder.\n"
                "4. Upload the current design screenshot.\n"
                "5. Upload or attach the Sports Cave limited-edition plaque asset from the project.\n"
                "6. Copy and paste this prompt.\n"
                "7. Generate the upgraded collector version."
            )
        _render_prompt_box(
            "Upgrade Existing Design Prompt",
            *PROMPT_BOXES["Upgrade Existing Design Prompt"],
            developer_password=developer_password,
        )

    with research_tab:
        render_new_design_tab()

    with expired_tab:
        st.subheader("Update Expired Edition")
        st.markdown(
            "Use this when an expired or sold-out limited edition needs a fresh next-chapter "
            "collector artwork without reprinting the original design."
        )
        _render_prompt_box(
            "Expired Edition / Next Chapter Design Prompt",
            *PROMPT_BOXES["Expired Edition / Next Chapter Design Prompt"],
            developer_password=developer_password,
        )

    with create_tab:
        st.subheader("Create New Ultimate Moment")
        st.markdown(
            "1. Start with the Find The Moment prompt.\n"
            "2. Replace [PLAYER / TEAM / RIVALRY / MOMENT] with the assignment.\n"
            "3. Let ChatGPT identify the strongest commercial and emotional moment.\n"
            "4. Search for the best hero image and best background/support image.\n"
            "5. Upload the selected images into ChatGPT with the limited-edition plaque asset.\n"
            "6. Use the Create Sports Cave Style Artwork prompt.\n"
            "7. Refine with harsh review until it feels close to 10/10.\n"
            "8. Save final PSD and flattened JPG in the correct Google Drive folder."
        )
        _render_prompt_box(
            "Find The Moment Prompt",
            *PROMPT_BOXES["Find The Moment Prompt"],
            developer_password=developer_password,
        )
        st.divider()
        _render_prompt_box(
            "Create Sports Cave Style Artwork Prompt",
            *PROMPT_BOXES["Create Sports Cave Style Artwork Prompt"],
            developer_password=developer_password,
        )

    with review_tab:
        st.subheader("Harsh Review Checklist")
        st.markdown(
            "After generating or designing, screenshot the artwork and use this prompt to judge whether "
            "it is good enough before saving final PSD/JPG."
        )
        _render_prompt_box(
            "Harsh Truth Sports Cave Design Review",
            *PROMPT_BOXES["Harsh Truth Sports Cave Design Review"],
            developer_password=developer_password,
        )
