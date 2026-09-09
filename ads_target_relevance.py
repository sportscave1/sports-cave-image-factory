"""Deterministic presentation ranking; never resolves or changes Meta IDs."""
import re
import unicodedata

STOPWORDS = frozenset("the a an and of for wall art print framed frame limited edition sports sport cave collection product products poster official premium exclusive australia aus uk usa".split())
SPORT_ALIASES = {
    "basketball": "nba", "american football": "nfl", "ice hockey": "nhl",
    "baseball": "mlb", "rugby league": "nrl", "australian football": "afl",
    "formula one": "f1", "formula 1": "f1", "mixed martial arts": "ufc",
}


def tokens(text):
    text = unicodedata.normalize("NFKD", str(text or "")).casefold()
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"\bf[\s.-]+1\b", "f1", text)
    return tuple(re.findall(r"[a-z0-9]+", text))


def extract_relevance_terms(product_title="", sport=""):
    sport_text = " ".join(tokens(sport))
    sport_terms = {word for word in tokens(sport) if word not in STOPWORDS and word != "other"}
    if sport_text in SPORT_ALIASES:
        sport_terms.add(SPORT_ALIASES[sport_text])
    title_terms = tuple(dict.fromkeys(word for word in tokens(product_title) if word not in STOPWORDS and len(word) > 1))
    return sport_terms, title_terms


def rank_relevant_meta_options(options, *, product_title="", sport="", selected="", show_all=False, id_key="id"):
    sport_terms, title_terms = extract_relevance_terms(product_title, sport)
    terms = sport_terms | set(title_terms)
    sport_phrase = " ".join(tokens(sport))
    athlete_phrase = " ".join(term for term in title_terms if term not in sport_terms)
    ranked = []
    for position, raw in enumerate(options):
        row = dict(raw)
        name_tokens = tokens(row.get("name") or row.get("label"))
        matches = terms & set(name_tokens)
        name = " " + " ".join(name_tokens) + " "
        exact_sport = bool(sport_terms and sport_phrase and (
            f" {sport_phrase} " in name or SPORT_ALIASES.get(sport_phrase) in name_tokens
        ))
        phrase = bool(len(athlete_phrase.split()) > 1 and f" {athlete_phrase} " in name)
        score = (exact_sport, phrase, len(matches))
        ranked.append((score, position, row))
    ranked.sort(key=lambda item: (tuple(-int(part) for part in item[0]), item[1]))
    relevant = [row for score, _, row in ranked if score[2]]
    all_rows = [row for _, _, row in ranked]
    visible = all_rows if show_all or not terms else [
        row for score, _, row in ranked if score[2] or str(row.get(id_key)) == str(selected)
    ]
    return {"options": visible, "all_options": all_rows, "relevant_count": len(relevant), "has_context": bool(terms)}
