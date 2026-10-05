"""Small offline AniList catalog: acquisition, stable snapshots and loading."""

import json
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib import error, request

ENDPOINT = "https://graphql.anilist.co"
CATALOG_QUERY = """
query($page:Int,$perPage:Int,$sort:[MediaSort],$format:MediaFormat,$before:FuzzyDateInt) {
  Page(page:$page,perPage:$perPage) {
    pageInfo { hasNextPage }
    media(type:ANIME,isAdult:false,sort:$sort,format:$format,startDate_lesser:$before) {
      id idMal title { romaji english native } format status episodes
      startDate { year month day } seasonYear genres
      tags { name rank } averageScore popularity isAdult
    }
  }
}
"""


def canonical_json(value):
    """A shared UTF-8 content representation, independent of dict insertion order."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                              allow_nan=False) + "\n", encoding="utf-8")


def graphql(query, variables=None, attempts=4):
    """Sequential public API requests; bounded retries respect Retry-After."""
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = request.Request(ENDPOINT, data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "anime-pref/0.2"})
    for attempt in range(attempts):
        try:
            with request.urlopen(req, timeout=40) as response:
                payload = json.load(response)
            if payload.get("errors") or not isinstance(payload.get("data"), dict):
                raise RuntimeError(f"AniList GraphQL errors: {payload.get('errors')}")
            return payload
        except (error.URLError, TimeoutError) as exc:
            if isinstance(exc, error.HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"AniList HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
            if attempt == attempts - 1:
                raise RuntimeError(f"AniList unavailable after {attempts} attempts") from exc
            retry_after = getattr(exc, "headers", {}).get("Retry-After", "0")
            time.sleep(min(60, max(3 * (attempt + 1), int(retry_after))))


def normalize_media(raw):
    """Keep catalog facts, not parser preferences. Unknown year/episodes stay null."""
    if type(raw.get("id")) is not int or raw["id"] < 1:
        raise ValueError("catalog id must be a positive integer")
    titles = raw.get("title")
    if not isinstance(titles, dict) or not any(titles.values()):
        raise ValueError("catalog title missing")
    year = (raw.get("startDate") or {}).get("year") or raw.get("seasonYear")
    return {"id": raw["id"], "idMal": raw.get("idMal"),
            "title": {k: titles.get(k) for k in ("romaji", "english", "native")},
            "format": raw.get("format"), "status": raw.get("status"),
            "episodes": raw.get("episodes"), "year": year,
            "startDate": raw.get("startDate"), "seasonYear": raw.get("seasonYear"),
            "genres": sorted(set(raw.get("genres") or [])),
            "tags": sorted(({"name": t["name"], "rank": t.get("rank", 0)}
                            for t in raw.get("tags") or []), key=lambda t: t["name"]),
            "averageScore": raw.get("averageScore"), "popularity": raw.get("popularity"),
            "isAdult": raw.get("isAdult", False)}


def catalog_jsonl(rows):
    """Stable row order and bytes give the local snapshot a reproducible identity."""
    return "".join(canonical_json(row) + "\n" for row in sorted(rows, key=lambda r: r["id"]))


def load_catalog(path, manifest_path=None):
    """Load offline facts, rejecting duplicate IDs and a broken content hash."""
    data = Path(path).read_bytes()
    rows = tuple(json.loads(line) for line in data.decode("utf-8").splitlines() if line)
    if not rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("empty catalog or duplicate IDs")
    for row in rows:
        if type(row["id"]) is not int or not isinstance(row.get("genres"), list):
            raise ValueError("invalid catalog row")
        if not isinstance(row.get("tags"), list) or not isinstance(row.get("title"), dict):
            raise ValueError("invalid catalog facts")
    if manifest_path:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if sha256(data).hexdigest() != manifest["catalog_sha256"] or len(rows) != manifest["record_count"]:
            raise ValueError("catalog manifest mismatch")
    return rows


def fetch_catalog_snapshot(output_dir, delay_seconds=2.2):
    """~1000-1900 popular/movie/recent/older anime, resumable page cache.

    This is deliberately a bounded catalog, not a complete site crawl. Existing
    source pages are reused, so a failed public API call never discards progress.
    """
    output_dir = Path(output_dir)
    schedules = (("popular", 20, ["POPULARITY_DESC", "ID"], None, None),
                 ("movies", 6, ["POPULARITY_DESC", "ID"], "MOVIE", None),
                 ("recent", 6, ["ID_DESC"], None, None),
                 ("older", 2, ["POPULARITY_DESC", "ID"], None, 20000101))
    by_id = {}; pages = []
    for name, count, sort, fmt, before in schedules:
        for page in range(1, count + 1):
            path = output_dir / "source" / f"{name}_{page:03d}.json"
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
            else:
                # AniList rejects inequality filters whose variable is null.
                # Omit optional arguments and their definitions together.
                query = CATALOG_QUERY
                variables = {"page": page, "perPage": 50, "sort": sort}
                for value, variable, declaration, argument in (
                    (fmt, "format", ",$format:MediaFormat", ",format:$format"),
                    (before, "before", ",$before:FuzzyDateInt", ",startDate_lesser:$before")):
                    if value is None:
                        query = query.replace(declaration, "").replace(argument, "")
                    else:
                        variables[variable] = value
                payload = graphql(query, variables)
                write_json(path, payload)
                time.sleep(delay_seconds)
            for raw in payload["data"]["Page"]["media"]:
                if not raw.get("isAdult"):
                    by_id[raw["id"]] = normalize_media(raw)
            pages.append(str(path.name))
            print(f"{name} page {page}/{count}: unique anime={len(by_id)}", flush=True)
            if not payload["data"]["Page"]["pageInfo"]["hasNextPage"]:
                break
    content = catalog_jsonl(by_id.values())
    path = output_dir / "anilist_catalog_v0.1.jsonl"
    path.write_text(content, encoding="utf-8", newline="")
    manifest = {"source": ENDPOINT, "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "catalog_version": "anilist-catalog-v0.1", "record_count": len(by_id),
                "catalog_sha256": sha256(content.encode()).hexdigest(),
                "source_pages": pages, "coverage_strategy": [s[0] for s in schedules],
                "year_field": "startDate.year then seasonYear", "complete_site_crawl": False}
    write_json(output_dir / "manifest.json", manifest)
    return manifest
