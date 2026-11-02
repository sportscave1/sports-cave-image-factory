"""Strict local caption matching for the experimental grouped-thumbnail route.

No fuzzy matching, remote inference, or input dispatch. Runtime coordinates must
be revalidated against the same visible shell pixels before use by the native host.
"""
import math
import unicodedata


def caption_key(value):
    if not isinstance(value, str) or not value or len(value) > 180:
        raise ValueError("Invalid thumbnail caption.")
    # OCR may omit spaces. Do not fold case, punctuation, or confusable letters.
    return ''.join(c for c in unicodedata.normalize('NFC', value) if not c.isspace())


def caption_matches(text, title):
    actual, expected = caption_key(text), caption_key(title)
    if actual == expected:
        return True
    # Windows inserts a close button on hover and ellipsizes the browser
    # suffix. Accept only that suffix loss, never a shortened page title.
    suffix = '-GoogleChrome'
    if not expected.endswith(suffix):
        return False
    prefix = actual[:-3] if actual.endswith('...') else actual[:-1] if actual.endswith('…') else None
    page = expected[:-len(suffix)]
    return bool(page and prefix and prefix.startswith(page+'-Google')
                and expected.startswith(prefix) and len(prefix) < len(expected))


def unique_caption(rows, title, width, height):
    key = caption_key(title)
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError("Caption candidate bound exceeded.")
    matches = [row for row in rows if caption_matches(row['text'], title)]
    if not matches:
        raise ValueError("Thumbnail caption is missing.")
    if len(matches) != 1:
        raise ValueError("Thumbnail caption is ambiguous.")
    row = matches[0]
    score = float(row['score'])
    if not math.isfinite(score) or not .97 <= score <= 1:
        raise ValueError("Thumbnail caption confidence is insufficient.")
    box = row['box']
    if len(box) != 4 or any(len(point) != 2 for point in box):
        raise ValueError("Invalid caption geometry.")
    values = [float(v) for point in box for v in point]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid caption geometry.")
    left, top = min(values[::2]), min(values[1::2])
    right, bottom = max(values[::2]), max(values[1::2])
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("Caption lies outside the observed image.")
    if right-left < 20 or bottom-top < 8 or bottom-top > 80:
        raise ValueError("Unsupported caption dimensions.")
    return dict(title=title, score=score, rect=[math.floor(left), math.floor(top),
                                             math.ceil(right), math.ceil(bottom)])
