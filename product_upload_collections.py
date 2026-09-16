"""Collection policy for the exported SOP, with an optional read-only preview.

The app exports instructions; the connected executor does Shopify writes. The
preview accepts caller-supplied verified facts and a catalogue, never fetches or
writes Shopify, and never treats a cached preview as upload authority.
"""
import json
import re

START = 'NEW PRODUCT MULTI-COLLECTION POLICY — AUTHORITATIVE V1'
END = 'END NEW PRODUCT MULTI-COLLECTION POLICY'
RULES = '''NEW PRODUCT MULTI-COLLECTION POLICY — AUTHORITATIVE V1
Scope: this new product only, in both Draft and Live staging. Supersede any
single-sport/only-two-collections instruction in saved templates. Preserve all
existing legitimate memberships. No bulk reassignment, migration or removals.

DISCOVER AND MATCH ALL COLLECTIONS
Read ALL existing Shopify collections, paginating to the end; include stable IDs,
titles, handles, current assignment capabilities, rules and established purpose.
Never invent a collection, hardcode cached IDs, or create duplicate collections.
Use explicit canonical mappings first, then verified structured product metadata:
sport, sub-sport/league, athlete(s), team(s), event, rivalry, era, country, product
category and tags. Title/filename alone and loose substrings are not authority.
Evaluate every collection. Return a deduplicated LIST of collection IDs, never a
single first match. Include every genuinely relevant broader and specific match.
Use these hierarchies only against collections actually present in the catalogue:
- Formula One / F1 -> Formula One + motor racing / motorsport + Collector Series.
- NBA -> NBA + basketball + Collector Series, plus verified player/team matches.
- NFL -> NFL + American football + Collector Series; never association football.
- Australian Supercars / V8 -> motor racing / motorsport + Collector Series;
  add Australia/discipline/driver collections only where purpose and facts match.
Also evaluate existing sport-specific Collector Series, subject, team, event,
rivalry, era and historical categories. Collector membership requires this product
to be eligible wall art. Exact athlete/team matches must agree with verified sport.
Do not infer a rivalry, historical tier or collection eligibility from champion,
legend, greatest, king, final or moment. Never cross sports: F1 is not NBA or NFL;
baseball is not rugby league; ice hockey is not cricket. Unknown identity means
review, not a guessed assignment. Missing optional collections are not errors.

COUNTRY AND MERCHANDISING
Evaluate real country/market collections using their established purpose and
verified metadata. Country or league alone does NOT prove best-seller status.
Manually curated Best Sellers, Popular, Featured or similar lists require explicit
existing upload eligibility or operator selection supported by relevance; otherwise
exclude them. Do not manufacture performance claims or tags to gain membership.

COMPACT REVIEW AND APPLY ALL
Before upload show a compact table: Collection title | ID | Manual/Automatic |
Reason | Selected/Needs review. Show ALL matches, not just the first. Preserve any
operator-approved relevant selections; deduplicate by stable ID. Show ambiguous
matches separately. Any cached/local preview is advisory: revalidate against the
fresh complete catalogue and researched product before writes.
Manual/custom: use the existing connected Shopify assignment operation supported
for each selected collection; apply EVERY selected manual ID to this exact new
product. Never truncate to index 0. Reuse memberships on retry. Inspect all errors.
Smart/automated: evaluate actual current rules (including all/any semantics);
verify resulting membership through Shopify. Never send an unsupported manual
collectionAddProducts request to a smart collection. Do not change collection
rules, price, identity or invent tags to force inclusion. Unknown/unsupported
rules require review and verified read-back, not assumed success. Discover current
capabilities before choosing any assignment operation; do not infer API support.
Re-read this product and EVERY selected collection, paginate memberships and report
each as verified/pending/error. Missing required memberships block completion;
leave Draft/report incomplete. Automatic rules may take time: use bounded retries.
Final summary includes ALL assigned and automatic collections and unresolved items.
Collection assignment does not authorise publication: obey the selected Draft/Live
finalisation mode. Draft never changes collection publications.
END NEW PRODUCT MULTI-COLLECTION POLICY'''

# Canonical handles verified in the store catalogue on 2026-09-16. IDs are always
# taken from the supplied catalogue; absent handles are simply not selected.
SPORT_HANDLES = {
    'f1': {'formula-one-wall-art', 'motor-racing-wall-art'},
    'supercars': {'motor-racing-wall-art'},
    'motorsport': {'motor-racing-wall-art'},
    'nba': {'nba'}, 'nfl': {'nfl-wall-art'},
    'football': {'soccer'}, 'cricket': {'cricket'},
    'baseball': {'baseball-wall-art'}, 'ice hockey': {'ice-hockey-wall-art'},
    'rugby league': {'rugby-league-collection'}, 'afl': {'afl-wall-art'},
    'tennis': {'tennis-wall-art'}, 'horse racing': {'horse-racing-wall-art'},
}
ALIASES = {'formula one': 'f1', 'formula 1': 'f1', 'v8': 'supercars',
           'v8 supercars': 'supercars', 'australian motorsport': 'motorsport',
           'motor racing': 'motorsport', 'soccer': 'football'}
SUBJECTS = {
    'michael jordan': ('nba', 'michael-jordan-wall-art'),
    'lebron james': ('nba', 'lebron-james-wall-art'),
    'stephen curry': ('nba', 'stephen-curry-wall-art'),
    'kobe bryant': ('nba', 'kobe-bryant-wall-art'),
    'lionel messi': ('football', 'lionel-messi-wall-art'),
    'cristiano ronaldo': ('football', 'cristiano-ronaldo-wall-art'),
}


def preview_collections(facts, catalogue):
    """Conservative known-catalogue preview, not a replacement for executor research.

    Automated and unmapped collections remain explicit review items so expanding
    the real catalogue cannot silently turn a preview into exhaustive approval.
    """
    identity = facts.get('league') or facts.get('sub_sport') or facts.get('sport', '')
    sport = str(identity).strip().casefold()
    sport = ALIASES.get(sport, sport)
    handles = {h: 'Verified sport hierarchy' for h in SPORT_HANDLES.get(sport, ())}
    if facts.get('collector_eligible') is True and sport in SPORT_HANDLES:
        handles['collector-series-art'] = 'Verified collector wall art'
    for subject in facts.get('athletes', []):
        match = SUBJECTS.get(str(subject).strip().casefold())
        if match and match[0] == sport:
            handles[match[1]] = 'Exact verified athlete and sport'
    rows, seen = [], set()
    for collection in catalogue:
        cid = collection.get('id')
        if not cid or cid in seen:
            continue
        seen.add(cid)
        automated = collection.get('ruleSet') is not None
        known_type = 'ruleSet' in collection
        reason = handles.get(collection.get('handle'))
        selected = bool(reason and known_type and not automated)
        rows.append({'id': cid, 'title': collection.get('title', ''),
                     'type': 'Automatic' if automated else 'Manual' if known_type else 'Unknown',
                     'selected': selected,
                     'reason': ('Evaluate current Shopify rules and verify membership' if automated
                                else reason if selected else 'Requires verified purpose/eligibility; not selected')})
    return {'manual_ids': [r['id'] for r in rows if r['selected']], 'review': rows}


def strip_rules(prompt):
    return re.sub(r'\s*' + re.escape(START) + r'.*?' + re.escape(END), '', str(prompt), flags=re.S).strip()


def apply_rules(prompt, metadata=None):
    text = strip_rules(prompt)
    # Preview is included inside the removable block for repeatable saved prompts.
    metadata = metadata or {}
    preview = ''
    if metadata.get('verified_collection_facts') and metadata.get('collection_catalogue'):
        plan = preview_collections(metadata['verified_collection_facts'], metadata['collection_catalogue'])
        preview = '\nLOCAL ADVISORY COLLECTION PREVIEW (revalidate before upload):\n' + json.dumps(plan, ensure_ascii=False)
    return text + '\n\n' + RULES.replace('\n' + END, preview + '\n' + END)
