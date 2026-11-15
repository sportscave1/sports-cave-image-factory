"""Pure local campaign search and reporting defaults; no metric transformations."""
from calendar import monthrange
from difflib import SequenceMatcher
from functools import lru_cache
import re
import unicodedata


def reporting_default(today):
    return today.replace(year=today.year-1, day=min(today.day, monthrange(today.year-1, today.month)[1])), today


@lru_cache(maxsize=4096)
def normalized(value):
    value = unicodedata.normalize('NFKD', value.casefold())
    return ' '.join(re.findall(r'[^\W_]+', ''.join(c for c in value if not unicodedata.combining(c))))


def search_campaigns(campaigns, query):
    query = normalized(str(query or ''))
    if not query:
        return list(campaigns)
    tokens = query.split()
    ranked = []
    for index, row in enumerate(campaigns):
        title = normalized(str(row.get('campaign_name') or row.get('campaign_id') or ''))
        words = title.split()
        exact = sum(token in words for token in tokens)
        partial = sum(any(word.startswith(token) for word in words) for token in tokens)
        similarities = [max((SequenceMatcher(None, token, word).ratio() for word in words), default=0) for token in tokens]
        fuzzy = sum(similarities)/len(tokens)
        if title == query: tier = 6
        elif exact == len(tokens): tier = 5
        elif title.startswith(query): tier = 4
        elif query in title: tier = 3
        elif partial == len(tokens): tier = 2
        elif exact or partial or (fuzzy >= .65 and min(similarities) >= .5): tier = 1
        else: continue
        ranked.append(((tier, exact/len(tokens), partial/len(tokens), fuzzy, SequenceMatcher(None,query,title).ratio(), -index), row))
    return [row for _, row in sorted(ranked, key=lambda item:item[0], reverse=True)[:5]]
