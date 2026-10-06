"""Manual reply-prompt templates and conservative review extraction; no I/O."""
import re
from support_email_provider import html_to_text

FIVE_STAR_TEMPLATE = """SPORTS CAVE — 5-STAR REVIEW RESPONSE

Write a short, warm customer reply on behalf of Sports Cave, a premium limited-edition sports wall art brand.

CUSTOMER
First name: {customer_first_name}

PRODUCT
{product_name}

REVIEW RATING
5/5

CUSTOMER REVIEW
{review_text}

Write the finished email reply using the context above.

REQUIREMENTS

- Address the customer naturally by first name.
- Thank them sincerely for their 5-star review.
- Acknowledge that they are happy with their purchase.
- Mention the product naturally, but shorten a long product title if that sounds better. For example, "Six Laps Ahead Peter Brock Wall Art" can simply be called their "Peter Brock piece".
- If their review contains a specific positive comment, acknowledge it naturally where appropriate.
- Invite them to send Sports Cave a photo or short video of the artwork displayed in their home, office, sports room or wherever they have placed it.
- Explain that Sports Cave would love to feature it in the Sports Cave community, website or social media, with their permission.
- As a thank-you specifically for sending the photo or video, offer them 15% off their next Sports Cave order.
- Do not imply that the 15% discount was given in exchange for the positive review.
- Keep the request optional and friendly. Do not pressure the customer.
- Keep the tone personal, premium, appreciative and genuine rather than corporate or overly promotional.
- Do not invent any facts about the customer, order or product.
- Do not mention Judge.me or the review platform.
- Do not include a subject line.
- Do not use bullet points or markdown.
- Keep the reply concise, ideally around 70–120 words.
- Sign off:

Thanks again,
Nathan
Sports Cave

Return ONLY the finished customer email reply, ready for me to paste into the reply box."""

EMAIL_REPLY_PROMPTS = {'five_star_review': {'label': '5-star review response', 'template': FIVE_STAR_TEMPLATE}}
NOTIFICATION = re.compile(r"^(?:re:\s*)?(?P<name>[^\n]{1,120}?)\s+left\s+(?:a\s+)?(?P<rating>[1-5])[- ]stars?\s+review\s+for\s+(?P<product>[^\n]+?)\s*$", re.I | re.M)
RATING = re.compile(r'^\s*(?:(?:review\s+)?rating\s*[:=]?\s*([1-5])(?:\s*/\s*5)?|([1-5])[- ]stars?)\s*[.!]?\s*$', re.I)
FOOTER = re.compile(r'^(?:kind regards|best regards|regards[,!]?|judge\.?me(?: team)?|the judge\.?me team|manage (?:this |your )?review|view (?:this |your )?review|reply to (?:this |the )?review|publish (?:this |the )?review|unsubscribe|(?:visit|go to|open) (?:your )?(?:shopify|admin)|if you (?:have|need) (?:any )?(?:questions|help)|powered by)', re.I)


def clean_text(value):
    text = html_to_text(str(value or ''))
    # Some notification bodies contain escaped literal formatting tags.
    if re.search(r'</?(?:b|i|p|div|br|span|strong|em)(?:\s[^>]*)?>', text, re.I):
        text = html_to_text(text)
    return '\n'.join(re.sub(r'[ \t\xa0]+', ' ', line).strip() for line in text.splitlines()).strip()


def extract_review(message, body):
    metadata = message.get('review') or body.get('review') or {}
    if not isinstance(metadata, dict):
        metadata = {}
    subject = clean_text(message.get('subject'))
    text = clean_text(body.get('html') or body.get('text'))
    subject_match = NOTIFICATION.fullmatch(subject)
    body_match = NOTIFICATION.search(text)
    match = subject_match or body_match
    ratings = [int(m.group('rating')) for m in (subject_match, body_match) if m]
    explicit = [RATING.fullmatch(line) for line in [subject, *text.splitlines()]]
    ratings.extend(int(m.group(1) or m.group(2)) for m in explicit if m)
    if metadata.get('rating') is not None:
        try:
            rating = float(metadata['rating'])
            scale = float(metadata.get('rating_scale', 5))
            ratings.append(rating if scale == 5 else 0)
        except (ValueError, TypeError):
            ratings.append(0)
    if not ratings or any(value != 5 for value in ratings):
        return {'error': '5-star rating could not be confirmed for this email.'}
    sender = message.get('sender') or {}
    platform = bool(re.search(r'judge\.?me|no[- ]?reply|notifications?', str(sender.get('name', ''))+' '+str(sender.get('email', '')), re.I))
    name = clean_text(metadata.get('reviewer_name') or metadata.get('customer_name'))
    if not name and match:
        name = match.group('name').strip()
    if not name:
        named = re.search(r'^(?:reviewer|customer)(?: name)?\s*:\s*(.+)$', text, re.I | re.M)
        name = named.group(1).strip() if named else ''
    if not name and not platform:
        name = clean_text(sender.get('name'))
    first = name.split()[0] if name and '@' not in name else 'Customer'
    product = clean_text(metadata.get('product_name') or metadata.get('product_title'))
    if not product and match:
        product = match.group('product').strip().strip("'\"‘’“”")
    if not product:
        found = re.search(r'^product(?: name)?\s*:\s*(.+)$', text, re.I | re.M)
        product = found.group(1).strip().strip("'\"‘’“”") if found else ''
    review = clean_text(metadata.get('review_text') or metadata.get('body'))
    if review:
        title = clean_text(metadata.get('review_title') or metadata.get('title'))
        review = '\n'.join(value for value in (title, review) if value)
    else:
        # Do not include the review-notification header in the customer's words.
        remaining = text[body_match.end():] if body_match else text
        lines = []
        for line in remaining.splitlines():
            if FOOTER.match(line) or re.match(r'^https?://|^support@', line, re.I):
                break
            if not line or RATING.fullmatch(line):
                continue
            if re.search(r'\bverified buyer\b|\bverified purchase\b', line, re.I):
                continue
            if re.match(r'^(?:hi|hello|dear)\b|^(?:reviewer|customer|product)(?: name)?\s*:|^(?:you (?:have )?received|a new review|new product review)', line, re.I):
                continue
            line = re.sub(r'^(?:review title|review text|review content|review body|review|title)\s*:\s*', '', line, flags=re.I)
            if line:
                lines.append(line)
        review = '\n'.join(lines).strip()
        if platform and not (match or re.search(r'^review(?: text| content| body)?\s*:', text, re.I | re.M)):
            review = ''
    if not review:
        return {'error': 'Customer review text could not be identified for this email.'}
    return {'customer_first_name': first, 'product_name': product, 'review_text': review}


def build_reply_prompts(message, body, *, thread_context=None, order_context=None):
    context = extract_review(message, body)
    prompts = [{'id': key, 'label': entry['label'], 'text': entry['template'].format(**context) if not context.get('error') else '',
             'error': context.get('error', '')} for key, entry in EMAIL_REPLY_PROMPTS.items()]
    from support_email_return_prompt import build_return_prompt
    prompts.append(build_return_prompt(message, body, thread_context=thread_context, order_context=order_context))
    return prompts
