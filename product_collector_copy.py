"""Shared customer-copy policy applied last to both exported Product Upload SOPs."""
import re

START = 'SPORTS CAVE COLLECTOR COPY — AUTHORITATIVE V1'
END = 'END SPORTS CAVE COLLECTOR COPY'
RULES = '''SPORTS CAVE COLLECTOR COPY — AUTHORITATIVE V1
Scope: customer-facing Shopify product title/H1 and description only. These rules
supersede conflicting visible-copy instructions anywhere in this SOP or saved
templates. Preserve all response keys, completion tables and Shopify HTML contracts.
Do not apply these title/length/style rules to SEO meta title, SEO meta description,
URL slug, image alt text or structured data: retain their separate SEO instructions.
On an existing product, rewrite title/description only when the user requests copy
changes/full standardisation; Media Update Mode still preserves both. This block
does not authorise any extra Shopify changes or alter publishing/edition policies.

TITLE
Default: [ATHLETE / SUBJECT] — [DESIGN TITLE] Wall Art
Two subjects: [SUBJECT 1] & [SUBJECT 2] — [DESIGN TITLE] Wall Art
Subject first, one EM DASH (—), Wall Art at the end. Never use a colon separator,
or remove the separator to form an awkward SEO phrase. No pipes, brackets, quotes
or unnecessary punctuation. Use verified name spelling and accents from supplied
research. Do not repeat the subject inside the design name. Do not automatically
insert Framed, Limited Edition, Premium, Collector, Poster, Print or Memorabilia.
Preserve a strong approved artwork/design name. Improve a weak, generic or awkward
name before constructing the title: normally 2–6 memorable words, grounded in the
actual subject/moment, not clickbait. Do not invent an event to justify a title.
An identification filename or existing SEO title is input evidence, not an order
to reuse awkward wording. If subject identity is uncertain, request clarification.

DESCRIPTION
Aim for approximately 45–70 words; shorter is welcome when stronger. Never pad to
reach a minimum. Use 3–4 compact mobile-friendly blocks, one central idea:
1. A bold, individual 3–7 word hook.
2. The moment: 1–2 short sentences about one supported memory, achievement,
   defining characteristic or rivalry. Emotion before product explanation.
3. Usually one fan-identity sentence: what owning this means to THIS fan.
4. One short collector close where appropriate, using confirmed scarcity only.
Combine blocks when that reads better. Use <p> and <strong> for the opening hook;
<em> only where useful. No extra headings, bullet lists, tables, CSS or divs.
Short sentences, meaningful fragments, pride, nostalgia and specificity. Do not
narrate where players, cars or trophies sit in the image: the buyer can see it.
No career summaries, room lists, stacked adjectives, fake hype or repeated ideas.

Never use these stock phrases in generated product descriptions:
"The artwork captures", "This artwork captures", "This piece captures",
"More than wall art", "Perfect for the cave, office, home bar", "Perfect for any",
"A must-have for", "Elevate your space", "Transform your", "The ultimate",
"Real fans do not just remember this moment — they own it."
Do not replace them with another universal ending. Generate a moment-specific
close; campaign slogans belong elsewhere. Do not copy examples mechanically.

FACTS AND SCARCITY
Use only supplied design/product research and verified product information.
Never invent dates, opponents, scores, championships, venues, cars, results,
awards, seasons, records, uniforms, licensing, signatures or specifications.
An image alone does not prove an event/date/result. If unsupported, use a broader
truthful fan connection or omit the claim. A supplied uncertain claim stays uncertain.
Use the authoritative confirmed edition limit, never an assumed default of 100.
"Limited to N worldwide" is allowed only if both N and that worldwide run policy
are confirmed. Never invent remaining counts or claim no reprints/closed forever
without confirmed policy. Omit scarcity when edition facts are unavailable; a
short product-specific emotional close is enough. Never imply a closed run is open.

INTERNAL QUALITY PASS — revise before returning; do not print this reasoning
Title: subject first? em dash? Wall Art suffix? strong design name? natural aloud?
No colon, repeated subject or keyword stuffing?
Description: around 70 words or less unless genuinely justified? strong hook?
One central idea? fan emotion/memory? no visual narration, banned phrases, room
lists or universal ending? every fact supported and scarcity authentic?
Does a passionate fan care, and does it sound individually written for THIS work?
Remove any sentence whose removal strengthens the copy. Revise failures before
returning the existing output schema. Leave separate SEO generation intact.
END SPORTS CAVE COLLECTOR COPY'''


def apply_rules(prompt):
    """Clean known legacy SOP sections, then supersede saved custom copy rules.

    Only known customer-copy sections/lines are removed; SEO, media, pricing,
    status and operational contracts are left intact. Safe on repeated rendering.
    """
    text=re.sub(re.escape(START)+r'.*?'+re.escape(END),'',str(prompt),flags=re.S).strip()
    for start,end in (
        ('PRODUCT TITLE AND H1','SHOPIFY HANDLE'),
        ('VISIBLE PRODUCT DESCRIPTION — COMPLETE SHOPIFY COPY','SEO PRINCIPLE'),
        ('VISIBLE PRODUCT DESCRIPTION IN FULL STANDARDISATION MODE','SEO IN FULL STANDARDISATION MODE'),
        ('\nDESCRIPTION\n','\nSEO\n'),
    ):
        text=re.sub(re.escape(start)+r'.*?(?='+re.escape(end)+r')',
                    start+'\nUse the shared collector-copy rules below when copy changes are authorised.\n\n',text,flags=re.S)
    lines=[]
    for line in text.splitlines():
        if ('90–130' in line or 'two story paragraphs' in line
            or 'complete, grounded Shopify description rather than short ad copy' in line):
            line='Follow the shared collector-copy title/description and quality checks below.'
        lines.append(line)
    return '\n'.join(lines).strip()+'\n\n'+RULES
