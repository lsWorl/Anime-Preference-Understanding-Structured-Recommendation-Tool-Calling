"""Execute the full hard query; references never become hard constraints."""
from math import log1p
import unicodedata
from anime_pref.data.query_validation import validate_query_structure


def relevant_tags(anime, threshold=50):
    return {t["name"] for t in anime["tags"] if (t.get("rank") or 0) >= threshold}


def _matches_set(values, constraint, exclusion_values=None):
    """Empty operators impose no condition; ANY is one OR clause."""
    exclusions=values if exclusion_values is None else exclusion_values
    return (set(constraint["all_of"]) <= values
            and (not constraint["any_of"] or bool(values & set(constraint["any_of"])))
            and not exclusions & set(constraint["none_of"]))


def _matches_range(value, bounds):
    # Unknown metadata cannot prove a specified hard bound. Never substitute zero.
    if bounds["min"] is None and bounds["max"] is None: return True
    if value is None: return False
    return ((bounds["min"] is None or value >= bounds["min"])
            and (bounds["max"] is None or value <= bounds["max"]))


def execute_query(structured_query, catalog, tag_min_rank=50, exclusion_min_rank=1):
    """Inclusive numeric bounds and full ALL/ANY/NONE semantics on local facts.

    Presence is not strong theme relevance: positive tags require rank >= 50.
    Exclusion is deliberately conservative: any ranked presence >= 1 is excluded.
    Thresholds are runtime retrieval policy, independent of parser Gold identity.
    """
    validate_query_structure(structured_query)
    hard=structured_query["hard_constraints"];result=[]
    for row in catalog:
        if not _matches_set(set(row["genres"]),hard["genres"]): continue
        if not _matches_set(relevant_tags(row,tag_min_rank),hard["tags"],relevant_tags(row,exclusion_min_rank)): continue
        if not _matches_range(row.get("year"),hard["year"]): continue
        if not _matches_range(row.get("episodes"),hard["episodes"]): continue
        if hard["formats"] and row.get("format") not in hard["formats"]: continue
        if hard["status"] and row.get("status") not in hard["status"]: continue
        result.append(row)
    return result


def _title_key(value):
    # Case/Unicode normalization only, no fuzzy/embedding matches or guessed facts.
    return unicodedata.normalize("NFKC",value).casefold().strip()


def resolve_reference(title, catalog):
    """Match one of the three catalog titles, preserving ambiguity as unresolved."""
    key=_title_key(title)
    matches=[r for r in catalog if any(_title_key(t)==key for t in r["title"].values() if t)]
    return matches[0] if len(matches)==1 else None


def rank_candidates(query, candidates, catalog):
    """Transparent deterministic score; popularity/quality never relax filtering."""
    positive_genres=set(query["hard_constraints"]["genres"]["all_of"]+query["hard_constraints"]["genres"]["any_of"])
    positive_tags=set(query["hard_constraints"]["tags"]["all_of"]+query["hard_constraints"]["tags"]["any_of"])
    refs=[resolve_reference(t,catalog) for t in query["reference_titles"]]
    refs=[r for r in refs if r is not None]
    ref_genres=set().union(*(set(r["genres"]) for r in refs)) if refs else set()
    ref_tags=set().union(*(relevant_tags(r) for r in refs)) if refs else set()
    maxpop=max((r.get("popularity") or 0 for r in catalog),default=0)
    results=[]
    for row in candidates:
        genres=set(row["genres"]);tags=relevant_tags(row)
        def jaccard(a,b): return len(a&b)/len(a|b) if a|b else 0
        components={"genre_overlap":len(genres&positive_genres)*0.2,
                    "tag_overlap":len(tags&positive_tags)*0.2,
                    "reference_similarity":jaccard(genres,ref_genres)+jaccard(tags,ref_tags) if refs else 0,
                    "popularity":0.3*log1p(row.get("popularity") or 0)/log1p(maxpop) if maxpop else 0,
                    "average_score":0.3*(row.get("averageScore") or 0)/100}
        results.append({**row,"score":round(sum(components.values()),8),"score_components":components})
    return sorted(results,key=lambda r:(-r["score"],r["id"]))
