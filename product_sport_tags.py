"""Conservative, additive product classification shared by prompts and webhooks.

Collections are exact catalogue matches, not arbitrary substring guesses. Unknown
or contradictory evidence produces a review result, never a destructive correction.
No network, customer, inventory, edition or publication operations live here.
"""
from dataclasses import dataclass
import html
import json
import re
import unicodedata

TAGS = dict(zip(
    ('Motorsport', 'Formula One', 'NASCAR', 'V8 Supercars', 'MotoGP', 'Basketball',
     'NFL', 'Baseball', 'Ice Hockey', 'Cricket', 'Football', 'Rugby League',
     'Rugby Union', 'AFL', 'Tennis', 'Golf', 'Horse Racing', 'Combat', 'WWE',
     'Athletics', 'Olympics', 'Surfing', 'Apparel'),
    ('SC_SPORT_MOTORSPORT', 'SC_SPORT_FORMULA_ONE', 'SC_SPORT_NASCAR',
     'SC_SPORT_V8_SUPERCARS', 'SC_SPORT_MOTOGP', 'SC_SPORT_BASKETBALL',
     'SC_SPORT_NFL', 'SC_SPORT_BASEBALL', 'SC_SPORT_ICE_HOCKEY', 'SC_SPORT_CRICKET',
     'SC_SPORT_FOOTBALL', 'SC_SPORT_RUGBY_LEAGUE', 'SC_SPORT_RUGBY_UNION',
     'SC_SPORT_AFL', 'SC_SPORT_TENNIS', 'SC_SPORT_GOLF', 'SC_SPORT_HORSE_RACING',
     'SC_SPORT_COMBAT', 'SC_SPORT_WWE', 'SC_SPORT_ATHLETICS', 'SC_SPORT_OLYMPICS',
     'SC_SPORT_SURFING', 'SC_CATEGORY_APPAREL')))
TAGS.update({name: 'SC_SPORT_' + name.upper().replace(' ', '_') for name in
             ('Motocross', 'Rally', 'Motorcycle Road Racing', 'Rally Raid', 'IndyCar')})
MOTOR_CHILDREN = {'Formula One', 'NASCAR', 'V8 Supercars', 'MotoGP',
                  'Motocross', 'Rally', 'Motorcycle Road Racing', 'Rally Raid', 'IndyCar'}
OTHER_MOTOR = {'Sports Car Racing',
               'Superbike', 'Enduro', 'Speedway', 'Karting', 'Drag Racing',
               'Motorcycle Endurance', 'Supermoto', 'Hill Climb'}
ALIASES = {
    'Motorsport': ('motor racing', 'motorsports', 'motor sports'),
    'Formula One': ('f1', 'formula 1'),
    'NASCAR': (), 'V8 Supercars': ('australian touring car championship', 'atcc', 'australian supercars', 'bathurst 1000'),
    'MotoGP': ('motorcycle grand prix', '500cc grand prix'),
    'Basketball': ('nba',), 'NFL': ('american football',), 'Baseball': ('mlb',),
    'Ice Hockey': ('nhl',), 'Cricket': (), 'Football': ('soccer', 'association football'),
    'Rugby League': ('nrl',), 'Rugby Union': (),
    'AFL': ('australian rules football', 'australian football', 'aussie rules'),
    'Tennis': (), 'Golf': (), 'Horse Racing': ('thoroughbred racing',),
    'Combat': ('combat sports', 'boxing', 'mma', 'ufc', 'mixed martial arts'),
    'WWE': (), 'Athletics': ('track and field',), 'Olympics': ('olympic games', 'olympic'),
    'Surfing': (), 'Apparel': (), 'Motocross': ('supercross',), 'Rally': ('wrc', 'rac rally'),
    'Rally Raid': ('dakar', 'dakar rally'),
    'IndyCar': ('indy 500', 'indianapolis 500'), 'Motorcycle Road Racing': ('isle of man tt',),
    'Sports Car Racing': ('gt world challenge', 'world endurance championship', 'le mans', 'bathurst 12 hour'),
    'Superbike': ('world superbike', 'wsbk'), 'Enduro': (), 'Speedway': (),
    'Karting': ('kart racing',), 'Drag Racing': (), 'Motorcycle Endurance': ('suzuka 8 hours',),
    'Supermoto': (), 'Hill Climb': ('hillclimb',),
    'Swimming': (),
}
# Curated identity fallback for the supplied acceptance cases. Explicit artwork
# discipline overrides a driver's career fallback (e.g. Rossi's GT racing).
ATHLETES = {
    **dict.fromkeys(('peter brock', 'allan moffat', 'dick johnson', 'craig lowndes', 'jamie whincup'), 'V8 Supercars'),
    **dict.fromkeys(('ayrton senna', 'lewis hamilton', 'max verstappen', 'oscar piastri', 'michael schumacher', 'daniel ricciardo'), 'Formula One'),
    **dict.fromkeys(('dale earnhardt', 'dale earnhardt sr', 'jeff gordon', 'kyle larson', 'richard petty', 'jimmie johnson', 'bill elliott'), 'NASCAR'),
    **dict.fromkeys(('valentino rossi', 'marc marquez', 'casey stoner', 'mick doohan', 'jorge lorenzo'), 'MotoGP'),
    'michael jordan': 'Basketball', 'shane warne': 'Cricket', 'tom brady': 'NFL',
    'andrew johns': 'Rugby League', 'cristiano ronaldo': 'Football', 'winx': 'Horse Racing',
    'undertaker': 'WWE',
    'jett lawrence': 'Motocross', 'colin mcrae': 'Rally',
    'michael dunlop': 'Motorcycle Road Racing', 'toby price': 'Rally Raid',
    'will power': 'IndyCar',
}
# Reuse the existing audited athlete-collection identities; no new live lookups.
from product_upload_collections import SUBJECTS as _COLLECTION_SUBJECTS
ATHLETES.update({name: {'nba': 'Basketball', 'football': 'Football'}[sport]
                 for name, (sport, _) in _COLLECTION_SUBJECTS.items()
                 if sport in {'nba', 'football'}})
PROMOTIONAL = {'all sports wall art', 'best selling sports wall art', 'popular',
               'featured designs', 'collector series', 'collector series art',
               'new products', 'the gift edit', 'rivalries'}


def key(value):
    text = unicodedata.normalize('NFKD', html.unescape(str(value or '')))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', text.casefold()))


LABELS = {key(alias): sport for sport, aliases in ALIASES.items() for alias in (sport, *aliases)}
COLLECTIONS = {**LABELS, **{key(name + ' wall art'): sport for name, sport in LABELS.items()}}
COLLECTIONS.update({'rugby league collection': 'Rugby League', 'combat art': 'Combat'})


def hierarchy(sports):
    sports = set(sports)
    if sports & (MOTOR_CHILDREN | OTHER_MOTOR): sports.add('Motorsport')
    if 'WWE' in sports: sports.add('Combat')
    return sports


def family(sport):
    if sport in MOTOR_CHILDREN | OTHER_MOTOR: return 'Motorsport'
    if sport == 'WWE': return 'Combat'
    return sport


def text_sports(text):
    """Whole labels, longest first: American Football must not become Soccer."""
    text = ' ' + key(re.sub('<[^>]*>', ' ', str(text or ''))) + ' '
    found = set()
    for alias, sport in sorted(LABELS.items(), key=lambda row: -len(row[0])):
        token = ' ' + alias + ' '
        if token in text:
            found.add(sport)
            text = text.replace(token, ' ')
    # Apparel is a product category, not a word in artwork copy about uniforms.
    return found - {'Apparel'}


def identities(text):
    text = ' ' + key(text) + ' '
    return {sport for name, sport in ATHLETES.items() if ' ' + name + ' ' in text}


def collection_sports(collection):
    explicit, subjects = set(), set()
    for value in (collection.get('handle'), collection.get('title')):
        name = key(value)
        if name in PROMOTIONAL: continue
        if name in COLLECTIONS: explicit.add(COLLECTIONS[name])
        subject = re.sub(r' (wall art|collection|tribute)$', '', name)
        if subject in ATHLETES: subjects.add(ATHLETES[subject])
    return explicit, subjects


def tag_list(values):
    if isinstance(values, str): values = values.split(',')
    return list(dict.fromkeys(str(t).strip() for t in (values or []) if str(t).strip()))


@dataclass(frozen=True)
class Classification:
    required_tags: tuple
    merged_tags: tuple
    missing_tags: tuple
    review: tuple
    evidence: tuple

    @property
    def ready(self):
        return bool(self.required_tags) and not self.review


def classify_product(product, *, verified_facts=None):
    """Facts are explicit, verified artwork facts, never model-generated biography.

    Supported facts: sports (list), events (list), competition_context (string),
    athletes (list). Descriptions only supplement already supported disciplines;
    weak/contradictory prose never creates an additional buyer-segment tag.
    """
    facts = verified_facts or {}
    explicit, subjects, evidence, review = set(), set(), [], []
    for collection in product.get('collections', []):
        sports, athletes = collection_sports(collection)
        explicit |= sports; subjects |= athletes
        if sports or athletes: evidence.append('Collection: ' + str(collection.get('title') or collection.get('handle')))
    declared = set()
    for value in facts.get('sports', []):
        sport = LABELS.get(key(value))
        if sport: declared.add(sport)
        else: review.append('Unmapped verified sport: ' + str(value))
    context = text_sports(' '.join(facts.get('events', [])) + ' ' + str(facts.get('competition_context', '')))
    title = str(product.get('title') or '')
    title_sports = text_sports(title)
    subjects |= identities(title)
    for athlete in facts.get('athletes', []): subjects |= identities(athlete)
    primary = explicit | declared
    supporting = context | title_sports
    # A contradictory series is not permission to assign both. A genuine multi-
    # discipline title/fact supports both; a broad parent is always compatible.
    exact_collections = explicit & (MOTOR_CHILDREN | OTHER_MOTOR)
    exact_context = supporting & (MOTOR_CHILDREN | OTHER_MOTOR)
    if exact_collections and exact_context and not exact_collections <= (exact_context | declared):
        review.append('Collection discipline conflicts with the depicted competition; review before tagging.')
    if (exact_collections & MOTOR_CHILDREN and subjects & MOTOR_CHILDREN and not exact_context
            and not declared & MOTOR_CHILDREN and not (subjects & MOTOR_CHILDREN) <= exact_collections):
        review.append('Specific motorsport collection conflicts with the documented subject fallback; verify the event.')
    def families(values): return {family(s) for s in values} - {'Olympics', 'Apparel'}
    supported = supporting | subjects | declared
    # Prose is supporting evidence, never authority to expand a career into every
    # competition. A contrary precise motorsport discipline must nevertheless
    # prevent a misleading athlete fallback (Rossi art depicting GT/motocross).
    prose_motor = text_sports(product.get('descriptionHtml', '')) & (MOTOR_CHILDREN | OTHER_MOTOR)
    known_motor = (primary | supporting | subjects) & (MOTOR_CHILDREN | OTHER_MOTOR)
    if prose_motor - known_motor:
        review.append('Description mentions another competition; verify the depicted discipline before tagging.')
    if re.search(r'\b(not|unrelated|excluding|except|never|without)\b', key(title)) and title_sports:
        review.append('Negated/qualified sport context requires review; do not classify by keyword alone.')
    if families(explicit) and families(supported) and not families(explicit) <= families(supported):
        # Empty supporting information is fine: exact sport collections alone suffice.
        review.append('Sport collection conflicts with product identity/context; review before tagging.')
    sports = primary | supporting
    if families(supporting | declared) and families(subjects) and not families(subjects) <= families(supporting | declared):
        review.append('Depicted sport conflicts with named subject; verify genuine multi-sport artwork.')
    if sports & (MOTOR_CHILDREN | OTHER_MOTOR):
        subjects -= MOTOR_CHILDREN | OTHER_MOTOR
    # Explicit Olympic context does not turn a swimmer into a track athlete.
    sports |= subjects
    if key(product.get('productType') or product.get('product_type')) in {'apparel', 'clothing'}:
        sports.add('Apparel')
    if not sports:
        review.append('No supported sport: verify the artwork and collection before tagging.')
    sports = hierarchy(sports)
    required = tuple(tag for sport, tag in TAGS.items() if sport in sports)
    old = tag_list(product.get('tags'))
    old_sports = {sport for sport, tag in TAGS.items() if tag in old}
    # Never erase or automatically correct historical classifications.
    incompatible = old_sports - sports
    if incompatible:
        review.append('Established sport tags need controlled review; preserved: ' + ', '.join(sorted(incompatible)))
    if not required and not review:
        review.append('No supported Shopify tag for this discipline; do not invent a tag.')
    if supported: evidence.append('Artwork identity/context: ' + ', '.join(sorted(supported)))
    missing = tuple(tag for tag in required if tag not in old)
    return Classification(required, tuple(old + list(missing)), missing,
                          tuple(dict.fromkeys(review)), tuple(evidence))


START = 'SPORTS CAVE AUTOMATIC SPORT TAGGING — V2'
END = 'END SPORTS CAVE AUTOMATIC SPORT TAGGING'


def apply_prompt_rules(prompt, metadata=None):
    """One generated policy for all three existing SOPs, including saved templates."""
    text = strip_prompt_rules(prompt)
    mapping = '\n'.join(f'- {sport}: {tag}' for sport, tag in TAGS.items())
    athlete_mapping = '\n'.join(f'- {name}: {sport}' for name, sport in ATHLETES.items())
    metadata = metadata or {}
    preview = classify_product({'title': metadata.get('product_name', ''),
                                'collections': metadata.get('selected_collections', []),
                                'tags': metadata.get('existing_tags', [])})
    advisory = json.dumps({'required_tags': preview.required_tags, 'review': preview.review}, ensure_ascii=False)
    rules = f'''{START}
Applies to UPLOAD TO DRAFT, UPLOAD & PUBLISH LIVE and Update existing product,
including Media Update Mode: sport-tag additions are the only extra permitted change.
Use the existing complete collection selector and fresh product read. Identify ALL
sports actually depicted, not every competition in a subject's biography. Exact
sport collections are primary evidence; supplement incomplete selections with
verified events/series, vehicle/competition context and documented subject history.
Do not change collection membership merely to obtain a tag. Promotional collections
(All Sports Wall Art, Best Selling Sports Wall Art, Popular, Featured Designs,
Collector Series, New Products, The Gift Edit, Rivalries) prove no sport.

EXACT SHARED MAPPING
{mapping}
CURATED SUBJECT FALLBACKS (only when the artwork has no contrary competition context)
{athlete_mapping}
Formula One, NASCAR, V8 Supercars, MotoGP, Motocross, Rally, Motorcycle Road Racing,
Rally Raid and IndyCar ALWAYS also require Motorsport.
Historical Australian Touring Car Championship and relevant Bathurst 1000 history
use V8 Supercars for marketing only; preserve accurate historical event/car wording.
Other motorsport (GT/endurance, karting, superbike) gets Motorsport only.
Isle of Man TT is Motorcycle Road Racing, not MotoGP. Dakar is Rally Raid, not Rally.
Explicit competition context overrides career defaults: Rossi in GT is not MotoGP.
WWE also requires Combat. Multiple depicted sports require every supported tag.
Olympics is cross-sport: require genuine Olympic context; swimming is not Athletics.
Champion, GOAT, Racing, Legend and Final alone never establish a sport.

ADDITIVE SAVE AND READ-BACK GATE
Before the normal create/update, derive required tags using this shared mapping;
merge them with existing unrelated tags, deduplicate, never remove established tags.
The existing products/create and products/update backend hook independently uses
product_sport_tags.classify_product and product_sport_tag_sync.sync_product_sport_tags.
It adds only missing tags with tagsAdd and verifies by fresh read. It is asynchronous,
not proof of completion merely because a webhook was accepted. This exported prompt
does not invoke local Python. Do not invent a connector endpoint or claim that it does.
After saving, read this SAME product ID and verify every required tag is present;
use bounded rereads for webhook completion. On timeout/userError/readback failure,
report SPORT TAGGING UNVERIFIED and exact product ID; never report complete success.
Reconcile the same ID/handle before retry; never recreate a product for a tagging error.
If metadata conflicts, or old sport tags appear wrong, preserve them, write no uncertain
tags and report SPORT CLASSIFICATION REVIEW REQUIRED with evidence and a separate
controlled-correction recommendation. Unknown sport requires review, not a guessed tag.
Do not activate a new Draft or pass Live staging QA with unresolved tagging checks.
For an existing product preserve status/publications and all non-tag scope safeguards.
Do not change variants, images, prices, inventory, copy, collections, edition numbers,
certificates, customer segments or consent as a side effect of tagging.
Local advisory preflight from supplied identity only (revalidate with fresh Shopify
collections and verified artwork facts; not permission to bypass review): {advisory}
{END}'''
    return text + '\n\n' + rules


def strip_prompt_rules(prompt):
    return re.sub(re.escape(START) + r'.*?' + re.escape(END), '', str(prompt), flags=re.S).strip()
