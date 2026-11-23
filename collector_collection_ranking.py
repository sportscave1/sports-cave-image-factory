"""Edition affinity using the storefront's sc-navigation-recommendations weights."""
WEIGHTS = {"SUBJECT": 110, "TEAM": 86, "EVENT": 76, "LEAGUE": 38,
           "SPORT": 27, "FORMAT": 5, "THEME": 7}


def affinity(anchor_tags, tags):
    shared = set(anchor_tags or ()) & set(tags or ())
    families = {tag.split("_")[1] for tag in shared
                if isinstance(tag, str) and tag.startswith("SC_")
                and len(tag.split("_")) > 2 and tag != "SC_SPORT_MOTORSPORT"
                and tag.split("_")[1] in WEIGHTS}
    if not any(WEIGHTS[family] > 7 for family in families):
        return 0
    return sum(WEIGHTS[family] for family in families)


def rank_candidates(anchor, candidates, tags, signals=None):
    signals = signals or {}
    def score(pair):
        index, identity = pair
        bonus = signals.get(identity.split("/")[-1], 0)
        bonus = min(6, max(0, bonus)) if type(bonus) is int else 0
        return -(affinity(tags.get(anchor), tags.get(identity)) + max(16-index, 1) + bonus)
    return [identity for _, identity in sorted(enumerate(candidates), key=score)]
