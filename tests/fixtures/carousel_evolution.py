"""Controlled copy fixtures, never production performance or pixel-analysis evidence.

Only the first Greg primary and four original card pairs were supplied by the
user. Other primaries are explicitly synthetic coverage for independent angles.
Review helpers declare test evidence; they are NOT an automatic quality judge.
"""
from copy import deepcopy

import ads_carousel_evolution as evolution

GREG_TITLE = 'Greg Murphy — Lap Of The Gods'
GREG_URL = 'https://sportscave.com.au/products/greg-murphy-lap-of-the-gods?utm_source=meta#edition'
GREG_ORIGINAL = "Some laps become folklore.\nThis one became Bathurst scripture.\nA tribute to the day Murph bent the mountain to his will.\n\nLimited 100 run. Don't miss it."
GREG_REFRESH = "Some laps never leave you.\nThis one still echoes through Bathurst.\nRemember the day Murph made the mountain his own.\n\nJust 100 editions. Make one yours."
GREG_CARDS = [
    ('Lap Of The Gods', 'Limited Edition', 'Lap Of The Gods', 'Collector Edition', 'premium lounge', 'product identity and collector appeal'),
    ('Gallery Framed', 'Collector Piece', 'Gallery Presence', 'Framed For Pride', 'gallery entrance', 'premium framing and physical presentation'),
    ('True Fans Only', 'Man Cave Ready', 'For The Faithful', 'Your Cave Awaits', 'home bar', 'fan belonging and personal sports-space ownership'),
    ('Limited To 100', 'Collector Series', '100 Editions Only', 'Exclusive Series', 'edition detail', 'edition detail and verified collector scarcity'),
]


def review(source, output, position, derived=False, role='Synthetic controlled collector angle'):
    return dict(position=position, source_id=source['source_id'], source_text=source['text'], output_text=output,
                baseline_kind='derived_no_original' if derived else 'original',
                selection_reason=f'Test fixture source {source["source_id"]}: retain {role}; no variation performance claim.',
                source_analysis={k:f'Synthetic review of {role}: {k}; source text recorded above.' for k in evolution.ANALYSIS},
                checks={k:dict(passed=True, reason=f'Test declaration: {role}, checked {k} against the recorded source and output.') for k in evolution.RUBRIC})


def attach_reviews(result, copy, records):
    context = result['creative_refresh_context']
    catalog, _ = evolution.sources(context, context['refresh_plan']['references'])
    records = deepcopy(records)
    for i, record in enumerate(records):
        if i >= len(catalog['cards']):
            break
        role = record.get('role', 'source role')
        record['visual_review'] = dict(passed=True, reason=f'Synthetic declaration: retain {role} and source family; new architecture/detail composition.')
        record['copy_review'] = {field: review(catalog['cards'][i][field], copy['cards'][i][field], i+1, role=role)
                                 for field in ('headline', 'description')}
    shared = {}
    for group in ('primary_texts', 'headlines', 'descriptions'):
        originals = catalog[group]
        basis = originals or catalog['primary_texts']
        shared[group] = [review(basis[i % len(basis)], value, i+1, derived=not originals)
                         for i, value in enumerate(copy[group])] if basis else []
    records[0]['shared_copy_review'] = shared
    return records


def greg():
    import ads_page as ads
    import ads_refresh_plan as plan
    from tests.test_ads_refresh_plan import executions, fixture
    originals = [GREG_ORIGINAL,
                 'Holden through and through. Bring that red-blooded pride home.',
                 'Back to Bathurst. Hear that roar again on your wall.',
                 'A moment for the faithful. Give your collection its Bathurst story.',
                 'Remember that mountain magic. Make room for your motorsport memory.']
    outputs = [GREG_REFRESH,
               'Holden in your heart. Give that red-blooded loyalty a wall.',
               'Bathurst comes rushing back. Keep that roar close to home.',
               'For those who still remember. Let Bathurst anchor your collection.',
               'That mountain memory stays. Give your motorsport passion its place.']
    source = dict(creative_format='CAROUSEL', shared_primary_texts=originals, source_card_count=4,
                  product_mapping=dict(product_title=GREG_TITLE, product_name=GREG_TITLE, product_handle='greg-murphy-lap-of-the-gods',
                                       product_url=GREG_URL, verified=True),
                  carousel_cards=[dict(position=i, image_url=f'https://example.fbcdn.net/greg{i}.png',
                    headline=c[0], description=c[1], scene=c[4], role=c[5], destination_url='https://sportscave.com.au/products/wrong')
                    for i,c in enumerate(GREG_CARDS,1)])
    result = ads.build_ads_result_record(GREG_TITLE, 'Motorsport', 'Australia', 'Carousel', product_url=GREG_URL,
        product_metadata={'edition_limit':100,'edition_limit_source':'user-supplied regression fixture'},
        creative_refresh_context=dict(winning_primary_text=GREG_ORIGINAL, winning_headline='', source_winner=source))
    carousel = dict(primary_texts=outputs, headlines=['The Mountain Memory', 'Holden Pride At Home', 'Bathurst Comes Back', 'For The Faithful', 'Motorsport Lives Here'],
        descriptions=['Keep that lap close', 'Red blooded passion', 'Recall the roar', 'A collectors memory', 'Your racing story'],
        cards=[dict(position=i, slot_id=f'carousel-{i:02d}', headline=c[2], description=c[3], destination_url=GREG_URL)
               for i,c in enumerate(GREG_CARDS,1)], setup_notes='Synthetic Greg Murphy copy regression')
    # Reuse structurally complete offline visual declarations; no pixel assertions.
    records = executions(fixture())[:4]
    refs = result['creative_refresh_context']['refresh_plan']['references']
    for record, ref in zip(records, refs):
        record.update(scene=ref['scene'],role=ref['role'])
        record['image_prompt'] = plan.carousel_standalone_brief(GREG_TITLE, ref['label'], scene=ref['scene'], role=ref['role'],
            detail='detail' in ref['role'], references=[r['label'] for r in refs])
    records = attach_reviews(result, carousel, records)
    return result, carousel, records
