"""Shared offline sport taxonomy; Shopify read-only audit: 2026-10-07.

Evidence: docs/evidence/shopify-sport-audit-2026-10-07.json.
Rugby Union is retained for existing saved workflows, not claimed as live stock.
Collection handles are evidence/matching hints, never authority for Shopify writes.
"""
import re
from ui_option_ordering import alphabetize_options

SPORT_COLLECTION_HANDLES = {
    'AFL': ('afl-wall-art',), 'Baseball': ('baseball-wall-art',),
    'Combat': ('combat-art',), 'Cricket': ('cricket',), 'Football': ('soccer',),
    'Formula One': ('formula-one-wall-art',), 'Horse Racing': ('horse-racing-wall-art',),
    'Ice Hockey': ('ice-hockey-wall-art',), 'MotoGP': ('motogp-wall-art',),
    'Motorsport': ('motor-racing-wall-art',), 'NASCAR': ('nascar-wall-art',),
    'NBA': ('nba',), 'NFL': ('nfl-wall-art',), 'Olympics': ('olympics-wall-art',),
    'Rugby League': ('rugby-league-collection',), 'Tennis': ('tennis-wall-art',),
    'V8 Supercars': ('v8-supercars-wall-art',), 'WWE': ('wwe-wall-art',),
}
PRODUCT_EVIDENCED_SPORTS = {
    'Athletics': 'Usain Bolt No Limits Wall Art',
    'Swimming': 'Forever Golden - Thorpe & Freeman Wall Art',
    'Golf': '63 Years Later: Ryan Fox Open Championship Wall Art',
    'Surfing': 'Kelly Slater Surfing Wall Art',
    'Motocross': 'Jett Lawrence Motocross Wall Art',
    'Rally': 'Toby Price — Conquer The Dakar Wall Art',
    'IndyCar': 'Will Power — The First Australian',
    'Road Racing': 'Michael Dunlop The Mountain King Wall Art',
}
LEGACY_SUPPORTED_SPORTS = ('Rugby Union',)
CANONICAL_SPORT_CATEGORIES = alphabetize_options(
    (*SPORT_COLLECTION_HANDLES, *PRODUCT_EVIDENCED_SPORTS, *LEGACY_SUPPORTED_SPORTS)
)
MOTORSPORT_DISCIPLINES = frozenset(('Formula One', 'MotoGP', 'NASCAR', 'V8 Supercars',
                                  'Motocross', 'Rally', 'IndyCar', 'Road Racing'))


def _key(value):
    return ' '.join(re.findall(r'[a-z0-9]+', str(value or '').casefold()))


_ALIASES = {
    'AFL': ('Australian Rules', 'Australian Rules Football', 'Australian Rules Football / AFL', 'Aussie Rules', 'Australian Rules AFL', 'Australian Football'),
    'Baseball': ('MLB', 'MLB / Baseball', 'Baseball / MLB'),
    'Combat': ('Combat Sports', 'Boxing', 'MMA', 'UFC', 'UFC/MMA', 'MMA/UFC', 'UFC / Boxing', 'Combat Sports Boxing MMA', 'Mixed Martial Arts'),
    'Football': ('Soccer', 'Football/Soccer', 'Soccer/Football', 'Association Football'),
    'NBA': ('Basketball', 'Basketball / NBA', 'NBA Basketball'),
    'NFL': ('American Football', 'American Football / NFL'),
    'Ice Hockey': ('Hockey', 'NHL', 'NHL / Ice Hockey', 'Ice Hockey / NHL'),
    'Rugby League': ('NRL', 'Rugby League / NRL'),
    'Rugby Union': ('Rugby',),
    'Motorsport': ('Motor Racing', 'Motorsport Art', 'Motorsport - General',
                   'Formula 1 / Motorsport', 'Australian Motorsport', 'Motor Sports', 'Motorsports'),
    'Formula One': ('F1', 'Formula 1'),
    'V8 Supercars': ('Supercars', 'V8', 'Australian Supercars'),
    'MotoGP': ('MotoGP / Motorcycle Racing',),
    'Rally': ('Dakar', 'Dakar Rally', 'WRC', 'Rally / WRC'),
    'Road Racing': ('Isle of Man TT', 'TT Racing'),
    'Athletics': ('Track and Field', 'Athletics / Track and Field'),
    'WWE': ('Wrestling', 'WWE Wrestling', 'Professional Wrestling / WWE'),
}
SPORT_CATEGORY_ALIASES = {
    _key(alias): sport
    for sport in (*CANONICAL_SPORT_CATEGORIES, 'Other')
    for alias in (sport, *_ALIASES.get(sport, ()), *SPORT_COLLECTION_HANDLES.get(sport, ()))
}


def normalize_sport_category(value, default=''):
    key = _key(value)
    # Exact suffix removal only: no fuzzy matching of merchandising collections.
    return SPORT_CATEGORY_ALIASES.get(key, SPORT_CATEGORY_ALIASES.get(
        re.sub(r' wall art$', '', key), default))


canonical_sport_category = normalize_sport_category


def is_valid_sport_category(value):
    return bool(normalize_sport_category(value))


def sport_category_options(placeholder=None, *, include_other=True, controls=(), current=None):
    values = [*CANONICAL_SPORT_CATEGORIES, *controls]
    if placeholder is not None:
        values.insert(0, placeholder)
    if include_other:
        values.append('Other')
    if current:
        values.append(normalize_sport_category(current, str(current)))
    return alphabetize_options(dict.fromkeys(values), first=tuple(c for c in controls if c != 'Custom'), last=('Custom',))


def normalize_sport_state(state, key, default='', *, preserve_custom=False):
    """Call before constructing a keyed widget; do not rewrite persisted records."""
    if key in state:
        old = state[key]
        value = normalize_sport_category(old, old if preserve_custom else default)
        if value != old:
            state[key] = value


def sport_family(value):
    sport = normalize_sport_category(value)
    return 'Motorsport' if sport in MOTORSPORT_DISCIPLINES else sport


def infer_sport_category(values, default=''):
    # Bare "Rugby" is accepted for legacy saved selections, but does not prove
    # League versus Union when classifying Shopify tags/collection metadata.
    matches = {normalize_sport_category(value) for value in values if _key(value) != 'rugby'} - {'', 'Other'}
    if matches & MOTORSPORT_DISCIPLINES:
        matches.discard('Motorsport')
    return next(iter(matches)) if len(matches) == 1 else default


def sport_aliases(value):
    """Labels accepted for a canonical sport, for backward-compatible filters."""
    sport = normalize_sport_category(value)
    return (sport, *_ALIASES.get(sport, ())) if sport else ()


def sport_collection_handles(value):
    sport = normalize_sport_category(value)
    handles = SPORT_COLLECTION_HANDLES.get(sport, ())
    return (*handles, *SPORT_COLLECTION_HANDLES['Motorsport']) if sport in MOTORSPORT_DISCIPLINES else handles


def detect_sport_in_text(value, default=''):
    """Suggestion only; longest whole-label matches avoid Football within NFL.

    Ambiguous unrelated disciplines require an operator selection. Athlete names
    remain the responsibility of existing product-specific suggestion logic.
    """
    text = ' ' + _key(value) + ' '
    matches = []
    for alias, sport in sorted(SPORT_CATEGORY_ALIASES.items(), key=lambda item: -len(item[0])):
        token = ' ' + alias + ' '
        if sport != 'Other' and alias != 'rugby' and token in text:
            matches.append(sport)
            text = text.replace(token, ' ')
    return infer_sport_category(matches, default)
