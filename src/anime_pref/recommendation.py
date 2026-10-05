"""End-to-end preference parsing and recommendation with explicit failure states."""
from anime_pref.data.domain_validation import validate_query_domain
from anime_pref.data.query_validation import canonicalize_query, validate_query_structure
from anime_pref.evaluation.e0_baseline import strict_parse_prediction
from anime_pref.retrieval.executor import execute_query, rank_candidates, relevant_tags, resolve_reference


class RecommendationService:
    """Injecting a parser makes offline tests independent of GPU and AniList."""
    def __init__(self, parser, rules, catalog):
        self.parser=parser;self.rules=rules;self.catalog=catalog

    def recommend_anime(self, user_text, top_k=10):
        if not isinstance(user_text,str) or not user_text.strip():
            raise ValueError("user_text must be nonempty")
        if type(top_k) is not int or not 1<=top_k<=100:
            raise ValueError("top_k must be 1..100")
        # Raw UI text may contain outer spaces, whereas the existing inference
        # message builder requires trimmed input. Preserve the original below;
        # this boundary cleanup never changes SemanticSpec or repairs a Query.
        raw=self.parser.generate_batch((user_text.strip(),))[0]
        result=self.recommend_query_output(raw,top_k)
        result.update(user_text=user_text,raw_model_output=raw)
        return result

    def recommend_query_output(self, raw, top_k=10):
        if type(top_k) is not int or not 1<=top_k<=100: raise ValueError("top_k must be 1..100")
        query,error=strict_parse_prediction(raw)
        if error: return {"status":"parse_failed","error":error,"parsed_query":None,"recommendations":[]}
        try:
            validate_query_structure(query);validate_query_domain(query,self.rules)
        except ValueError as exc:
            return {"status":"validation_failed","error":str(exc),"parsed_query":query,"recommendations":[]}
        query=canonicalize_query(query)
        candidates=execute_query(query,self.catalog)
        ranked=rank_candidates(query,candidates,self.catalog)
        warnings=[]
        for title in query["reference_titles"]:
            if resolve_reference(title,self.catalog) is None:
                warnings.append(f"Reference unresolved or ambiguous: {title}; no similarity bonus applied.")
        if query["unresolved_preferences"]:
            warnings.append("Unresolved preferences were not enforced: "+", ".join(query["unresolved_preferences"]))
        if query["soft_preferences"]:
            warnings.append("Approved soft preferences currently have no ranking implementation.")
        def present(row):
            return {"id":row["id"],"url":f"https://anilist.co/anime/{row['id']}",
                    "title":row["title"]["english"] or row["title"]["romaji"] or row["title"]["native"],
                    "titles":row["title"],"year":row.get("year"),"format":row.get("format"),
                    "status":row.get("status"),"episodes":row.get("episodes"),"genres":row["genres"],
                    # Display only admitted, relevant tags, not unreviewed/spoiler metadata.
                    "tags":sorted(relevant_tags(row)&self.rules.tags),"score":row["score"],
                    "score_components":row["score_components"]}
        return {"status":"ok" if ranked else "no_matches","parsed_query":query,
                "candidate_count":len(ranked),"recommendations":[present(r) for r in ranked[:top_k]],
                "warnings":warnings,"message":"" if ranked else "No matching anime found."}
