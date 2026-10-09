"""Winner-relative Carousel Refresh contract. Pure local checks, no model/API calls.

Rubric declarations are review evidence, not automatic semantic or pixel analysis.
Only new plans carrying CONTRACT opt in; historical exports remain compatible.
"""
import json
import re

CONTRACT = 'SPORTS_CAVE_CAROUSEL_WINNER_COPY_EVOLUTION_V2'
ANALYSIS = ('hook', 'selling_angle', 'emotion', 'fan_collector_positioning', 'tone_intensity',
            'rhythm', 'scarcity', 'cta_intent_placement', 'sporting_references')
RUBRIC = ('strategy', 'emotion', 'style', 'meaningful_improvement', 'verified_facts', 'natural_words')
BLAND = ('transform your space', 'elevate your decor', 'stunning masterpiece',
         'the perfect addition to your room', 'celebrate sporting greatness in style',
         'a powerful centrepiece for every home')
STOCK_CLAIM = re.compile(
    r'\b(?:\d+|one|two|three|four|five|few)\s+(?:(?:editions?|prints?|pieces?|copies|units?)\s+)?(?:left|remaining)\b'
    r'|\b(?:remaining stock|last few|selling fast|sold out|almost gone)\b', re.I)


def clean(value):
    return value.replace('\r\n', '\n').replace('\r', '\n').strip() if isinstance(value, str) else ''


def words(value):
    # Whitespace-delimited words containing a letter/number; hyphenated words and
    # contractions count once. Standalone em dashes are punctuation, not words.
    return re.findall(r'\S*[\w]\S*', clean(value), re.UNICODE)


def measures(value):
    value = clean(value)
    lines = [line for line in value.splitlines() if line.strip()]
    return dict(words=len(words(value)), characters=len(value), lines=len(lines),
                paragraphs=len(re.split(r'\n\s*\n', value)) if value else 0,
                fragments=sum(len([p for p in re.split(r'[.!?]+(?:\s+|$)', line) if words(p)]) for line in lines))


def bounds(value, kind='primary'):
    n = len(words(value))
    tolerance = max(2, n * 15 // 100) if kind == 'primary' else max(1, n * 15 // 100) if kind == 'shared' else 1
    return max(1, n - tolerance), n + tolerance


def sources(context, references):
    """Preserve actual source identities; never label a derived option an original."""
    source = context.get('source_winner') or {}
    catalog, issues = {}, []
    for group, prefix, fallback in (
        ('primary_texts', 'PRIMARY', source.get('shared_primary_text') or context.get('winning_primary_text')),
        ('headlines', 'HEADLINE', source.get('shared_headline') or context.get('winning_headline')),
        ('descriptions', 'DESCRIPTION', source.get('shared_description')),
    ):
        raw = source.get('shared_' + group)
        if raw is None or raw == []:
            raw = [fallback] if clean(fallback) else []
        if not isinstance(raw, list) or any(not clean(v) for v in raw):
            issues.append(f'Source {group}: missing or ambiguous text; reload/confirm the original copy.')
            raw = []
        seen, entries = set(), []
        for i, value in enumerate(raw, 1):
            value = clean(value)
            if value in seen:
                continue
            seen.add(value)
            entries.append(dict(source_id=f'{prefix}_{i}', text=value, **measures(value),
                                word_bounds=bounds(value, 'primary' if prefix == 'PRIMARY' else 'shared')))
        catalog[group] = entries
    if not catalog['primary_texts']:
        issues.append('No original shared primary text is available. Supply it before completing a winner refresh.')
    catalog['cards'] = []
    for i, ref in enumerate(references, 1):
        card = {'position': i, 'winner_reference': ref['label']}
        for field in ('headline', 'description'):
            value = clean(ref.get(field))
            if not value:
                issues.append(f'Card {i} source {field} is missing; confirm the actual winner before refreshing it.')
            card[field] = dict(source_id=f'CARD_{i}_{field.upper()}', text=value,
                               **measures(value), word_bounds=bounds(value, 'card'))
        catalog['cards'].append(card)
    return catalog, issues


def instruction(context, references):
    catalog, issues = sources(context, references)
    return f'''{CONTRACT} — HIGHEST PRIORITY FOR CAROUSEL REFRESH COPY
The original winner is the source of truth for advertising strategy, emotional angle, tone, sentence rhythm, copy length and card sequence. Create an improved sibling of the winner, not a new advertising concept. This overrides any fixed sentence count, generic five-angle strategy or New Ads history-first priority. Preserve the same purchase motivation and selling pressure; strengthen clarity, fan language and hook without replacing the argument. Performance improvement is a hypothesis, never a guarantee.

SOURCE COPY CATALOG (source IDs are independent of output/card positions)
{json.dumps(catalog, ensure_ascii=False)}
Source problems: {json.dumps(issues, ensure_ascii=False) if issues else 'None'}
If source problems exist, list them and request the missing/ambiguous original fields. Stop before producing completed copy/CSV; never fabricate a proven baseline. Preserve supplied images and work. Legacy manual sources must supply the actual card copy.

Select exactly five primary outputs, each mapped to an actual PRIMARY source ID. With more than five originals, select the five strongest relevant distinct source angles using explicit selection reasons; no invented variation-level performance attribution. With fewer than five distinct originals, explicitly reuse source IDs for sibling refinements, cover every available original and state that limitation. Primary N does NOT belong to Card N. Never invent extra winning variations.
Analyse each selected field independently: {', '.join(ANALYSIS)}. The catalog records word/character counts, sentence-or-fragment count, non-empty lines and paragraph breaks. Preserve sporting references, verified facts, scarcity treatment and CTA intent/position.
Primary text: stay inside each mapped source's word_bounds (approximately ±15%, minimum two-word tolerance for short texts). Preserve its line/blank-line rhythm, normally within one sentence/fragment and one non-empty line; keep paragraph count. Four sharp lines should remain four sharp lines, not an explanatory paragraph. No fixed global sentence count.
Each card headline and description maps ONLY to its own original field, normally ±1 word. Maximum 17 characters including spaces/punctuation (Python len); no commas/full stops, truncated words or unnatural abbreviations. Complete natural words. Preserve the card role and sequence: framing remains framing/presentation; fan belonging and personal sports-space desire remain fan ownership; rivalry remains rivalry; nostalgia remains nostalgia; verified edition-limit scarcity retains that limit, never invented remaining stock. Product identity may repeat where protected.
Also complete all five shared headline variation rows and all five shared description variation rows. Map each to an original of that type when available, using its individual length/style/intent and word_bounds. If no originals of that type exist, set baseline_kind=derived_no_original and derive a concise option from a named PRIMARY or card-copy source; do not claim an original shared baseline. Derived options must be no longer than 10 words or their basis if shorter. Shared options are separate from the 17-character card rule.
Do not copy whole sentences unchanged except protected product names or mandatory verified facts. No unchanged field, phrase shuffling or synonym-only revision: explain a meaningful hook/clarity/specificity improvement. Do not force different strategies or ban recurring protected facts just to make siblings unlike each other.
Keep premium collector voice, natural Australian English for Australian campaigns, fan-recognisable nostalgia and direct confident language. No new hype, emojis, promises, demand, stock or endorsements. Reject bland additions: {', '.join(BLAND)}.

COPY REVIEW IN EXISTING EXECUTION NOTES — NOT IN CSV
Keep the existing JSON array of card execution records. Add copy_review to EVERY card record, with headline and description review objects. Add shared_copy_review ONLY to the first record: primary_texts, headlines, descriptions arrays, exactly five review objects each in output order. Add visual_review to each record: {{"passed": true, "reason": "Specific comparison of source family/function and new physical execution"}}.
Each copy review object must contain position (1-based output position), source_id (catalog ID), source_text (exact original catalog text), output_text (exact final CSV text, including line breaks), baseline_kind (original or derived_no_original), selection_reason (source selection/reuse/derivation rationale), source_analysis (object with all keys: {', '.join(ANALYSIS)}; use explicit 'absent in source' when applicable), checks (object with all keys: {', '.join(RUBRIC)}). Each check is {{"passed": true/false, "reason": "Concrete source-to-output evidence"}}. Strategy/emotion/style checks must explain continuity; meaningful_improvement must explain more than synonyms; verified_facts must identify evidence and no new claims; natural_words must check complete readable language. These are qualitative review declarations, not automated semantic certification or numeric similarity scores.
Before finalising compare EVERY field to its actual mapped source and EVERY visual to its own winner. Verify counts/order mechanically; apply the qualitative rubric honestly. If a check fails, revise only that item and its review. A changed CSV field needs a matching new review. Never mark ready with unresolved copy or visual review.
'''


def _normal(value):
    return ' '.join(w.casefold().strip('.,!?;:') for w in words(value))


def _review_pass(value):
    return (isinstance(value, dict) and value.get('passed') is True
            and bool(clean(value.get('reason'))) and clean(value['reason']).casefold() not in {'pass', 'ok', 'yes', 'pending', 'unknown'})


def quality_issues(carousel, records, context, references, product, destination, fixed_facts=()):
    catalog, issues = sources(context, references)
    if not isinstance(records, list) or len(records) != len(references):
        return issues + ['Complete the source-mapped copy review in the card execution notes.']
    records = [r if isinstance(r, dict) else {} for r in records]
    lookup = {s['source_id']: s for group in ('primary_texts', 'headlines', 'descriptions') for s in catalog[group]}
    lookup.update({s['source_id']: s for c in catalog['cards'] for s in (c['headline'], c['description'])})
    protected = {_normal(v) for v in (product, *fixed_facts) if clean(v)}

    def review(value, note, allowed, label, position, kind, derived=False):
        value = clean(value)
        if not value:
            issues.append(f'{label}: populate the production copy.')
        if not isinstance(note, dict):
            issues.append(f'{label}: missing source-to-refresh review.')
            return None
        original = lookup.get(note.get('source_id')) if isinstance(note.get('source_id'), str) else None
        if not original or note['source_id'] not in allowed:
            issues.append(f'{label}: source mapping must use its own actual winning field.')
            return None
        old = original['text']
        if (note.get('position') != position or clean(note.get('source_text')) != old
                or clean(note.get('output_text')) != value
                or note.get('baseline_kind') != ('derived_no_original' if derived else 'original')):
            issues.append(f'{label}: review is stale or has the wrong output/source/baseline; review this field again.')
        if not clean(note.get('selection_reason')):
            issues.append(f'{label}: explain source selection, reuse or derivation.')
        analysis = note.get('source_analysis')
        if not isinstance(analysis, dict) or any(not clean(analysis.get(k)) for k in ANALYSIS):
            issues.append(f'{label}: complete the independent source analysis.')
        checks = note.get('checks')
        failed = [k for k in RUBRIC if not isinstance(checks, dict) or not _review_pass(checks.get(k))]
        if failed:
            issues.append(f'{label}: revise/review {", ".join(failed)} with specific source evidence.')
        low, high = (1, min(10, max(1, len(words(old))))) if derived else bounds(old, kind)
        if not low <= len(words(value)) <= high:
            issues.append(f'{label}: {len(words(value))} words; mapped source has {len(words(old))}, required {low}–{high}.')
        if kind == 'primary':
            before, after = measures(old), measures(value)
            if (abs(before['fragments']-after['fragments']) > 1 or abs(before['lines']-after['lines']) > 1
                    or before['paragraphs'] != after['paragraphs']):
                issues.append(f'{label}: preserve the mapped source sentence/fragment and line-break rhythm.')
        if kind == 'card' and (len(value) > 17 or re.search(r'[.,\n]', value)):
            issues.append(f'{label}: maximum 17 characters, one line, no commas/full stops; use complete words.')
        numbers = lambda text: set(re.findall(r'\b\d+(?:[.,]\d+)*%?', text))
        if numbers(value) - numbers(old) or (not derived and numbers(old) - numbers(value)):
            issues.append(f'{label}: preserve source numbers; do not add or change factual claims.')
        if STOCK_CLAIM.search(value) and not STOCK_CLAIM.search(old):
            issues.append(f'{label}: unsupported stock/demand claim; retain verified edition scarcity only.')
        if any(p in value.casefold() and p not in old.casefold() for p in BLAND):
            issues.append(f'{label}: remove the generic marketing addition.')
        if any(ord(c) >= 0x1F000 for c in value if c not in old):
            issues.append(f'{label}: remove emojis absent from the source.')
        old_sentences = {_normal(p) for p in re.split(r'[.!?]+(?:\s+|$)|\n+', old) if words(p)}
        for sentence in re.split(r'[.!?]+(?:\s+|$)|\n+', value):
            normal = _normal(sentence)
            is_protected = normal in protected or (len(words(normal)) >= 2 and f' {normal} ' in f' {_normal(product)} ')
            if normal and not is_protected and (normal in old_sentences or (normal == _normal(value) and sorted(words(normal)) == sorted(words(_normal(old))))):
                issues.append(f'{label}: unchanged sentence/field or reordered source words; refine the wording within its original angle.')
                break
        return note['source_id']

    shared = records[0].get('shared_copy_review', {}) if records else {}
    for group in ('primary_texts', 'headlines', 'descriptions'):
        values = carousel.get(group)
        notes = shared.get(group) if isinstance(shared, dict) else None
        if not isinstance(values, list) or len(values) != 5 or not isinstance(notes, list) or len(notes) != 5:
            issues.append(f'{group}: exactly five populated outputs and five mapped review records are required.')
            continue
        derived = group != 'primary_texts' and not catalog[group]
        allowed = {s['source_id'] for s in catalog[group]} if not derived else {k for k in lookup if k.startswith(('PRIMARY_', 'CARD_'))}
        mapped = []
        for i, (value, note) in enumerate(zip(values, notes), 1):
            mapped.append(review(value, note, allowed, f'{group} {i}', i, 'primary' if group == 'primary_texts' else 'shared', derived))
        if group == 'primary_texts' and len(set(mapped) - {None}) != min(5, len(catalog[group])):
            issues.append('Primary source selection: cover five distinct originals when available, otherwise every available original with explicit reuse.')
        normalised = [_normal(v) for v in values]
        if len(set(normalised)) != 5:
            issues.append(f'{group}: duplicate whole outputs; refine only the repeated options within their mapped angles.')
    cards = carousel.get('cards')
    if not isinstance(cards, list) or len(cards) != len(references):
        return issues + ['Keep exactly the original number of ordered cards.']
    for i, (card, record) in enumerate(zip(cards, records), 1):
        if not isinstance(card, dict):
            issues.append(f'Card {i}: invalid copy record.')
            continue
        if card.get('position') != i or card.get('slot_id') != f'carousel-{i:02d}':
            issues.append(f'Card {i}: preserve source/card/slot order.')
        if clean(card.get('destination_url')) != clean(destination):
            issues.append(f'Card {i}: use the verified selected product destination, including its intended URL parameters.')
        if record.get('winner_reference') != f'WINNER_CARD_{i}' or record.get('position') != i:
            issues.append(f'Card {i}: review belongs to a different winner/card position.')
        if not _review_pass(record.get('visual_review')):
            issues.append(f'Card {i}: review visual continuity and genuinely new execution against its own source.')
        notes = record.get('copy_review')
        for field in ('headline', 'description'):
            review(card.get(field), notes.get(field) if isinstance(notes, dict) else None,
                   {f'CARD_{i}_{field.upper()}'}, f'Card {i} {field}', i, 'card')
    return list(dict.fromkeys(issues))
