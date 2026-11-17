"""Creative-only upgrades at the Product Upload prompt boundary, including saved copy.

No workflow steps, approval requirements, exports or shared prompt storage change.
"""
import re

GLASS = ('Show the wall-mounted artwork behind one continuous pane of premium clear glass. '
         'Use broad, soft, low-contrast reflections of a plausible window or surrounding room, '
         'with gentle tonal variation across part of the pane and finer physically appropriate highlights. '
         'Transparent reflections may cross the printed image while faces, lettering, signatures and '
         'edition details remain recognisable and readable through them. Preserve the underlying print. '
         'Do not confine glass to one corner or an edge streak; avoid opaque glare, a milky wash, '
         'mirror-like glass and repeated diagonal highlights. Adapt reflections to each camera angle '
         'and actual room light. Retain narrow wall-contact shadows, soft directional mounting shadows, '
         'natural frame highlights and consistent light falloff.')

ROOM = ('Give the Man Cave, Office and Living Room a restrained Sports Cave collector character: '
        'believable residential furniture, tactile upholstery, timber and subtle metal details. '
        'Use distinct neutral wall colour families and finishes across the three homes, mixing light '
        'and dark settings. No green walls or green decorative accents; preserve green within the '
        'original artwork. Use one or two restrained sport/team colour accents in furnishings where '
        'appropriate. No plants, flowers, foliage or botanical arrangements. Use sparse functional '
        'objects such as a remote, controller, speaker, notebook, books or folded throw; empty space '
        'is welcome. Do not replace each plant with another object or invent collectible memorabilia.')

PHOTOGRAPHY = ('Photograph a believable corner of a real collector’s home with natural window light '
               'and restrained practical lights. Use slight asymmetry, realistic upholstery creases, '
               'subtle surface wear and convincing architectural junctions. Keep the artwork sharp '
               'and the room naturally resolved, without showroom perfection, artificial blur or '
               'dramatic cinematic effects. Use subtle residential proportions, windows, trim and '
               'materials appropriate to the known buyer market; when unspecified, the league’s '
               'home market can inform the setting (NFL/NBA/MLB: American, NRL/AFL: Australian, '
               'British darts: British). International sports use the known sales market. '
               'Avoid flags, landmarks and national caricatures. Vary layouts, wall treatments, '
               'furnishings and lighting between products and avoid recent scene combinations when '
               'available in context. All three artworks hang physically on the wall, never lean '
               'on furniture or stand on the floor.')

SCALE = ('Every mockup depicts the XL framed edition: 87 cm wide × 62 cm high for landscape, '
         '62 cm wide × 87 cm high for portrait. Use these outer framed dimensions rather than '
         'the smaller A1 paper dimensions. Keep realistic scale against nearby furniture and '
         'architecture at their respective camera distances. Make the artwork prominent through '
         'camera position and composition, never by enlarging its physical size. Preserve source '
         'orientation, frame proportions and moulding width. No size confirmation is required.')


def upgrade(text):
    """Replace known conflicting creative clauses, rather than append rival instructions."""
    replacements = {
        'Keep reflections clear of important artwork details, titles and faces.': GLASS,
        "Honour each card's saved room and camera selections; keep the three homes architecturally distinct.": ROOM + '\n' + PHOTOGRAPHY + "\nHonour each card's resolved room, camera and wall selections; keep the three homes architecturally distinct.",
        '- Appropriate reflections near frame edges.': '- Broad transparent room reflections across part of the pane, with finer natural highlights.',
        'Never allow reflections to obscure:': 'Transparent reflections may cross the following details, which remain clearly readable through the glass:',
        'a slightly stronger reflection toward an edge or upper area where physically appropriate': 'broad, transparent room reflections across part of the pane rather than an isolated corner streak',
        'One laptop, lamp, plant, notebook or a few books may be appropriate.': 'One laptop, lamp, notebook or a few books may be appropriate. No plants or foliage.',
        'Use seating, sideboards, lamps, books, plants and tables only when they improve the composition.': 'Use seating, sideboards, lamps, books and tables sparingly when they improve the composition. No plants or foliage.',
        '- Repeating plants and shelving layouts.': '- Plants, foliage and repeated shelving layouts.',
        '- Matching decorative plants.': '- Plants or botanical arrangements.',
        'from the last image created': 'from the original supplied product reference',
        'premium cinematic lighting': 'believable natural residential photographic lighting',
        'Premium cinematic lighting': 'Believable natural residential photographic lighting',
        'restrained glass reflections that do not obscure the artwork': 'broad transparent glass reflections through which the artwork remains readable',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Retired room-library palette choices in both defaults and saved masters.
    text = re.sub(r'\b(?:muted olive|heritage green|heritage forest green|forest green|sage green|eucalyptus green|rich bottle green|muted green)\b',
                  'warm stone', text, flags=re.I)
    text = re.sub(r'Give all three room types a premium Sports Cave sports collector / man cave feel,[^\n]*', ROOM + '\n' + PHOTOGRAPHY, text)
    text = text.replace('Use the owner-confirmed large 87 × 62 cm landscape edition, reversed for portrait, with premium glass; never ask for size or glazing confirmation.', SCALE)
    # This is the canonical size paragraph in current and saved master/card briefs.
    text = re.sub(r'Every framed mockup represents the owner-confirmed large 87 × 62 cm landscape edition, or 62 × 87 cm portrait edition\. Preserve source proportions and realistic scale\. Never request size or glazing confirmation\.', SCALE, text)
    return text
