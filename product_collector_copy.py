"""Shared customer-copy policy applied last to both exported Product Upload SOPs."""
import re

START = 'SPORTS CAVE COLLECTOR COPY — AUTHORITATIVE V2'
END = 'END SPORTS CAVE COLLECTOR COPY'
DESCRIPTION_RULES = """Description: these narrative rules supersede conflicting description instructions in saved templates, additional requirements and QA/finalisation steps.
Aim for approximately 35–65 words; allow more only when the sporting story genuinely needs it. Never pad. Use 2–3 compact, mobile-friendly paragraphs:
Hook: a bold, individual, emotionally relevant opening of approximately 3–7 words.
Story: the actual sporting moment, legacy, achievement or rivalry. Prioritise specific, verified historical details. Write for the fan who remembers watching it, without narrating what is visually obvious.
Feeling (optional): a brief emotional conclusion connected to this athlete, event or rivalry. If the story finishes powerfully, stop. No forced endings, motivational quotes or universal closing slogan.
Use <p> and <strong> for the opening hook; <em> only where useful. No extra headings, lists, tables, CSS or divs.
Confident, restrained, emotionally specific. Short sentences and deliberate rhythm. Evoke pride, nostalgia, rivalry, triumph, resilience or sporting identity where it fits. Every description must sound individually written: no interchangeable athlete templates, generic AI phrases, stacked adjectives, exaggerated hype, career summaries, repeated product descriptions, room lists or wall-display instructions.
Keep sales language out of the narrative: no purchasing encouragement, scarcity, edition limits, urgency, certificates, shipping, frame options, sizing or specifications. Do not explain that the product is an artwork, print or collector edition. Shopping components already communicate this. Preserve actual edition limits, inventory, scarcity UI, specifications and structured product data outside the narrative.
Never use: "Limited to 100 editions", "Limited to 100 worldwide", "Secure yours", "Own yours today", "Shop now", "More than wall art", "The perfect addition to your collection", "This edition captures", "The edition captures", "This piece captures", "Perfect for any", "A must-have", "Elevate your space", "The ultimate", "Real fans remember this. Own the moment." or its older "Real fans do not just remember" variation. Do not replace them with another universal ending.
Use only supplied research and verified product information. Never invent dates, opponents, scores, championships, venues, cars, results, awards, seasons, records, uniforms, licensing, signatures or specifications. An image alone does not prove an event/date/result. Omit unsupported claims; uncertain evidence stays uncertain.
Internal description QA (revise silently): authentic? emotionally specific? clear and brief? every fact verified? individual? 2–3 paragraphs, around 35–65 words unless justified? no sales language, visual narration or forced ending? Remove any optional sentence whose removal strengthens the story."""

RULES = '''SPORTS CAVE COLLECTOR COPY — AUTHORITATIVE V2
Always describe the product as an ‘edition’, never ‘artwork’; use ‘edition’ or ‘editions’ wherever you would otherwise use ‘artwork’ or ‘artworks’.
Scope: customer-facing Shopify product title/H1 and description only. These rules
supersede conflicting visible-copy instructions anywhere in this SOP or saved
templates. Preserve all response keys, completion tables and Shopify HTML contracts.
Do not apply these title/length/style rules to SEO meta title, SEO meta description,
URL slug, image alt text or structured data: retain their separate SEO instructions.
On an existing product, rewrite title/description only when the user requests copy
changes/full standardisation; Media Update Mode still preserves both. This block
does not authorise any extra Shopify changes or alter publishing/edition policies.

TITLE
Default: [ATHLETE / SUBJECT] — [SHORT DESIGN HOOK]
Two subjects: [SUBJECT 1] vs [SUBJECT 2] — [SHORT HOOK]
Subject first, one EM DASH (—). Wall Art is optional within the 60-character limit. Never use a colon separator,
or remove the separator to form an awkward SEO phrase. No pipes, brackets, quotes
or unnecessary punctuation. Use verified name spelling and accents from supplied
research. Do not repeat the subject inside the design name. Do not automatically
insert Framed, Limited Edition, Premium, Collector, Poster, Print or Memorabilia.
Preserve a strong approved edition/design name. Improve a weak, generic or awkward
name before constructing the title: normally 2–6 memorable words, grounded in the
actual subject/moment, not clickbait. Do not invent an event to justify a title.
An identification filename or existing SEO title is input evidence, not an order
to reuse awkward wording. If subject identity is uncertain, request clarification.

''' + DESCRIPTION_RULES + '''

EDITION DATA (OUTSIDE THE NARRATIVE)
Use the authoritative confirmed edition limit, never an assumed default of 100.
Never invent remaining counts or no-reprint policy; preserve explicit exceptions.
Never imply a closed run is open. Keep edition tracking and publishing policies intact.

INTERNAL QUALITY PASS — revise before returning; do not print this reasoning
Title: subject first? em dash? Wall Art suffix? strong design name? natural aloud?
No colon, repeated subject or keyword stuffing?
Apply the description QA above. Revise failures before returning the existing
output schema. Leave separate SEO generation intact.
END SPORTS CAVE COLLECTOR COPY'''


def apply_rules(prompt):
    """Clean known legacy SOP sections, then supersede saved custom copy rules.

    Only known customer-copy sections/lines are removed; SEO, media, pricing,
    status and operational contracts are left intact. Safe on repeated rendering.
    """
    text=re.sub(r'SPORTS CAVE COLLECTOR COPY (?:—|â€”) AUTHORITATIVE V[12].*?'+re.escape(END),'',str(prompt),flags=re.S).strip()
    for start,end in (
        ('PRODUCT TITLE AND H1','SHOPIFY HANDLE'),
        ('VISIBLE PRODUCT DESCRIPTION — COMPLETE SHOPIFY COPY','SEO PRINCIPLE'),
        ('VISIBLE PRODUCT DESCRIPTION IN FULL STANDARDISATION MODE','SEO IN FULL STANDARDISATION MODE'),
        ('\nDESCRIPTION\n','\nSEO\n'),
    ):
        # Older saved exports contain a UTF-8 em dash decoded as Windows-1252.
        # Match that heading too; do not normalize unrelated operator content.
        heading=re.escape(start).replace('—', '(?:—|â€”)')
        text=re.sub(heading+r'.*?(?='+re.escape(end)+r')',
                    start+'\nUse the shared collector-copy rules below when copy changes are authorised.\n\n',text,flags=re.S)
    lines=[]
    for line in text.splitlines():
        # Preserve non-narrative fields even when their values quote old copy.
        protected = re.search(r'\b(?:SEO|meta title|meta description|alt text|structured data|inventory|edition_limit|confirmed_limit)\b', line, re.I) or line.lstrip().startswith(('{', '[', '"'))
        if not protected and (re.search(r'Real fans (?:remember|do not just remember|know)|Own the moment|REQUIRED DESCRIPTION ENDING|Limited to (?:100|N) (?:worldwide|editions)|required collector ending|standard closing', line, re.I)):
            continue
        if (re.search(r'90(?:–|â€“)130|two story paragraphs|two concise story paragraphs|bold scarcity close', line, re.I)
            or 'complete, grounded Shopify description rather than short ad copy' in line):
            line='Follow the shared collector-copy title/description and quality checks below.'
        lines.append(line)
    return '\n'.join(lines).strip()+'\n\n'+RULES
