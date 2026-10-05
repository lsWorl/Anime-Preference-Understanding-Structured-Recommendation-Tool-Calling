"""v0.2 data: real vocabulary + reviewed patterns + existing E3/Gold builders.

No model writes Gold. The small phrase inventory below is controlled realization;
it does not infer genre/tag attributes from references or soften hard constraints.
"""

from collections import Counter
from dataclasses import asdict, replace
import json
from pathlib import Path
from random import Random

from anime_pref.data.catalog import load_catalog, write_json
from anime_pref.data.dataset_record_builder import build_dataset_record, count_hard_semantic_clauses
from anime_pref.data.pilot_dataset import records_to_jsonl
from anime_pref.data.query_builder import build_query, load_domain_rules
from anime_pref.data.reference_title_pool import load_reference_title_pool
from anime_pref.data.tag_subset import (build_executable_tag_subset, load_executable_tag_subset,
    executable_tag_subset_sha256, write_executable_subset_bundle)
from anime_pref.data.taxonomy_snapshot import load_canonical_taxonomy_snapshot, taxonomy_snapshot_sha256
from anime_pref.schemas.taxonomy import TagAuditRecordSpec
from anime_pref.schemas.preference_query import SemanticSpec, SetConstraintSpec, RangeConstraintSpec
from anime_pref.schemas.structural_atom import StructuralAtom
from anime_pref.schemas.structural_pattern import StructuralPatternPlan
from anime_pref.schemas.operator_cardinality import OperatorCardinalityPlan
from anime_pref.sampling.config import load_sampler_config
from anime_pref.sampling.semantic_spec_binder import sample_semantic_spec_from_pattern
from anime_pref.sampling.structural_atom import STRUCTURAL_ATOM_KIND_ORDER, structural_constraint_count

# Explicit, modest engineering-reviewed allowlist under the user's delegated
# selection authorization. We never claim these are independently human audited.
# No category-wide or popularity-only automatic approval.
TAG_ALIASES = {
    "Female Harem": [], "Male Harem": [], "Mixed Gender Harem": [],
    "Isekai": ["异世界"], "Reverse Isekai": ["反向异世界"], "Time Loop": ["时间循环"],
    "Ensemble Cast": ["群像"], "Philosophy": ["哲学"], "Death Game": ["死亡游戏"],
    "Video Games": ["电子游戏"], "Board Game": ["桌游"], "Virtual World": ["虚拟世界"],
    "Space": ["太空"], "Space Opera": ["太空歌剧"], "Cyberpunk": ["赛博朋克"],
    "Steampunk": ["蒸汽朋克"], "Post-Apocalyptic": ["末世"], "Dystopian": ["反乌托邦"],
    "School": ["校园"], "School Club": ["学校社团"], "College": ["大学"],
    "Work": ["职场"], "Family Life": ["家庭生活"], "Historical": ["历史背景"],
    "Military": ["军事"], "Police": ["警察"], "Detective": ["侦探"], "Crime": ["犯罪"],
    "Espionage": ["谍战"], "Survival": ["生存"], "Battle Royale": ["大逃杀"],
    "Martial Arts": ["武术"], "Swordplay": ["剑术"], "Samurai": ["武士"],
    "Ninja": ["忍者"], "Magic": ["魔法"], "Super Power": ["超能力"],
    "Superhero": ["超级英雄"], "Demons": ["恶魔"], "Vampire": ["吸血鬼"],
    "Zombie": ["丧尸"], "Ghost": ["幽灵"], "Aliens": ["外星人"],
    "Robots": ["机器人"], "Artificial Intelligence": ["人工智能"],
    "Dragons": ["龙"], "Mythology": ["神话"], "Youkai": ["妖怪"],
    "Urban Fantasy": ["都市奇幻"], "Dungeon": ["地下城"], "Alchemy": ["炼金术"],
    "Coming of Age": ["成长"], "Revenge": ["复仇"], "Politics": ["政治"],
    "Economics": ["经济"], "Love Triangle": ["三角恋"], "Parody": ["恶搞"],
    "Satire": ["讽刺"], "Slapstick": ["肢体喜剧"], "Iyashikei": ["治愈系"],
    "Food": ["美食"], "Band": ["乐队"], "Idol": ["偶像"], "Dancing": ["舞蹈"],
    "Basketball": ["篮球"], "Volleyball": ["排球"], "Football": ["足球"],
    "Baseball": ["棒球"], "Tennis": ["网球"], "Swimming": ["游泳"],
    "Cycling": ["骑行"], "Boxing": ["拳击"], "Camping": ["露营"],
    "Travel": ["旅行"], "Animals": ["动物"], "Rural": ["乡村"],
    "Male Protagonist": ["男主角"], "Female Protagonist": ["女主角"],
    "Primarily Adult Cast": ["主要角色为成年人"], "Educational": ["教育"],
    "Software Development": ["软件开发"], "Writing": ["写作"], "Photography": ["摄影"],
}
GENRE_ALIASES = {"Action": "动作", "Adventure": "冒险", "Comedy": "喜剧",
    "Drama": "剧情", "Ecchi": "Ecchi", "Fantasy": "奇幻", "Horror": "恐怖",
    "Mahou Shoujo": "魔法少女", "Mecha": "机甲", "Music": "音乐", "Mystery": "悬疑",
    "Psychological": "心理", "Romance": "恋爱", "Sci-Fi": "科幻", "Slice of Life": "日常",
    "Sports": "运动", "Supernatural": "超自然", "Thriller": "惊悚"}
FORMAT_ALIASES = {"TV": "TV动画", "MOVIE": "动画电影", "TV_SHORT": "TV短篇",
                  "OVA": "OVA", "ONA": "ONA", "SPECIAL": "特别篇", "MUSIC": "音乐动画"}
STATUS_ALIASES = {"FINISHED": "已完结", "RELEASING": "正在连载", "NOT_YET_RELEASED": "尚未播出",
                  "CANCELLED": "已取消", "HIATUS": "暂停播出"}


def build_real_domain(root):
    """Bind explicit tag decisions to real snapshot IDs/hash, then active rules."""
    snapshot = load_canonical_taxonomy_snapshot(root / "data/domain/taxonomy_v0.2/canonical.json")
    catalog = load_catalog(root / "data/catalog/anilist_catalog_v0.1.jsonl", root / "data/catalog/manifest.json")
    digest = taxonomy_snapshot_sha256(snapshot)
    frequency = Counter(t["name"] for row in catalog for t in row["tags"] if t["rank"] >= 50)
    audits = []
    for tag in snapshot.tags:
        if tag.name not in TAG_ALIASES:
            continue
        approved = not tag.is_adult and not tag.is_general_spoiler
        audits.append(TagAuditRecordSpec(tag.id, tag.name, tag.category, approved,
            "Explicit engineering-reviewed concept; delegated selection, not independent human audit."
            if approved else "Excluded: adult/spoiler flag.", tuple(TAG_ALIASES[tag.name]),
            tag.is_general_spoiler, tag.is_adult, digest))
    subset = build_executable_tag_subset(tuple(audits), snapshot, subset_version="anilist-executable-tags-v0.2")
    names = {t.tag_name for t in subset.tags}
    harem = ["Female Harem", "Male Harem", "Mixed Gender Harem"]
    if not set(harem) <= names or not 50 <= len(names) <= 150:
        raise ValueError("real executable subset lacks required capacity/HAREM")
    domain_dir = root / "data/domain/subset_v0.2"
    if not (domain_dir / "manifest.json").exists():
        write_executable_subset_bundle(subset, output_dir=domain_dir)
    elif executable_tag_subset_sha256(load_executable_tag_subset(domain_dir / "executable_tags.json")) != executable_tag_subset_sha256(subset):
        raise ValueError("existing subset differs; use a new version")
    write_json(root / "data/domain/tag_audit.v0.2.json", [asdict(a) for a in audits])
    write_json(root / "data/domain/tag_selection.v0.2.json", {
        "reviewer": "engineering assistant under explicit user delegation",
        "independent_human_audit": False, "source_snapshot_hash": digest,
        "catalog_rank50_frequencies": {n: frequency[n] for n in sorted(names)},
        "not_present_in_snapshot": sorted(set(TAG_ALIASES) - {t.name for t in snapshot.tags})})
    rules_doc = json.loads((root / "tests/fixtures/domain_rules.synthetic.v0.1.json").read_text(encoding="utf-8"))
    rules_doc.update(rules_version="anilist-domain-rules-v0.2", executable_subset_version=subset.subset_version,
                     executable_subset_hash=executable_tag_subset_sha256(subset))
    rules_doc["taxonomy"]["genres"] = sorted(set(snapshot.genres) - {"Hentai"})
    rules_doc["taxonomy"]["tags"] = sorted(names)
    write_json(root / "configs/domain_rules.v0.2.json", rules_doc)
    rules = load_domain_rules(root / "configs/domain_rules.v0.2.json")
    # Reference titles remain strings; their catalog ID lives in a separate resolver file.
    popular = sorted(catalog, key=lambda r: (-(r["popularity"] or 0), r["id"]))[:200]
    title_map = {(r["title"]["english"] or r["title"]["romaji"]): r["id"] for r in popular}
    write_json(root / "data/domain/reference_titles.v0.2.json",
               {"pool_version": "anilist-reference-titles-v0.2", "titles": sorted(title_map)})
    write_json(root / "data/domain/reference_ids.v0.2.json", title_map)
    # The old sampler contract is reused as policy format, with real value pools.
    config = json.loads((root / "tests/fixtures/semantic_sampler.synthetic.v0.1.json").read_text(encoding="utf-8"))
    config["sampler_version"] = "anilist-semantic-values-v0.2"
    config["combination_policy_version"] = "reviewed-patterns-v0.2"
    config["tag_sampling"]["value_tiers"] = {}
    config["tag_sampling"]["default_weight"] = 1.0
    config["tag_sampling"]["maximum_value_share"] = 0.1
    config["numeric_sampling"]["year"].update(common_values=[2000, 2010, 2015, 2018, 2020],
        catalog_region_values=[1990, 1995, 2005, 2012, 2016, 2022, 2024], long_tail_values=[1970, 1980, 1985, 2025])
    config["numeric_sampling"]["episodes"].update(common_values=[12, 24],
        catalog_region_values=[1, 6, 13, 26, 50], long_tail_values=[2, 10, 39, 100])
    write_json(root / "configs/semantic_sampler.v0.2.json", config)
    # All three models get this same explicit v0.2 vocabulary prompt during comparison.
    prompt = (root / "configs/e0_system_prompt.v0.2.txt").read_text(encoding="utf-8").rstrip()
    lines = prompt.splitlines()
    lines = ["允许的 tags：" + "、".join(sorted(names)) + "。" if l.startswith("允许的 tags：") else l for l in lines]
    lines += ["年份下界不代表确切年份：2015年及以后只写 year.min=2015，year.max=null。",
              "TV只属于formats，FINISHED只属于status；未提到状态时status必须为空。",
              "明确的最多/以内/至少集数按hard约束提取；未批准的主观词条保留在unresolved_preferences。",
              "批准的中文genre别名：" + "；".join(f"{v}={k}" for k, v in GENRE_ALIASES.items()) + "。",
              "批准的中文tag别名：" + "；".join(f"{a}={n}" for n in sorted(names) for a in TAG_ALIASES[n]) + "。",
              "格式别名：" + "；".join(f"{v}={k}" for k,v in FORMAT_ALIASES.items()) + "。",
              "状态别名：" + "；".join(f"{v}={k}" for k,v in STATUS_ALIASES.items()) + "。"]
    (root / "configs/final_system_prompt.v0.2.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rules, subset


def reviewed_patterns():
    """A compact explicit pattern inventory; no additional probability framework."""
    result = []
    def add(*atoms):
        atoms = tuple(sorted(atoms, key=lambda a: STRUCTURAL_ATOM_KIND_ORDER.index(a.kind)))
        count = structural_constraint_count(atoms)
        kinds = {a.kind for a in atoms}
        if kinds & {"tag_group_any", "tag_group_none"}: family = "normalization"
        elif kinds == {"reference"}: family = "reference_only"
        elif "reference" in kinds: family = "reference_composition"
        elif len(atoms) == 1 and atoms[0].kind in {"genre_set", "tag_set"} and atoms[0].operator_plan.cardinality > 1: family = "same_field_logic"
        elif count == 1: family = "single_constraint"
        else: family = "cross_field_composition"
        result.append(StructuralPatternPlan(family, 0 if count == 0 else str(count) if count < 5 else "5_plus", atoms))
    def s(kind, op, n): return StructuralAtom(kind, OperatorCardinalityPlan(op,n))
    year = StructuralAtom("year_range", range_pattern="min_only")
    ep = StructuralAtom("episodes_range", range_pattern="max_only")
    fmt = StructuralAtom("format_any"); status = StructuralAtom("status_any")
    for kind in ("genre_set", "tag_set"):
        for op, sizes in (("all_of", (1,2,3)), ("any_of", (2,3)), ("none_of", (1,2))):
            for size in sizes:
                atom = s(kind,op,size); add(atom); add(atom, year); add(atom, ep, fmt)
    for kind in ("year_range", "episodes_range"):
        for mechanic in ("min_only", "max_only", "bounded_range"):
            atom = StructuralAtom(kind, range_pattern=mechanic)
            if mechanic != "bounded_range": add(atom)
            add(atom, fmt); add(atom, fmt, status)
    add(fmt); add(status); add(fmt,status); add(StructuralAtom("reference"))
    for op in ("all_of", "any_of", "none_of"):
        g=s("genre_set",op,2 if op=="any_of" else 1)
        t=s("tag_set",op,2 if op=="any_of" else 1)
        add(g,t); add(g,t,year,ep,fmt); add(g,year,ep,fmt,status)
        add(g,year,StructuralAtom("reference")); add(t,status,StructuralAtom("reference"))
    for group in ("tag_group_any", "tag_group_none"):
        add(StructuralAtom(group)); add(s("genre_set","any_of",2),StructuralAtom(group))
        add(s("genre_set","any_of",2),year,ep,fmt,StructuralAtom(group))
    return tuple(result)


STYLES = (
    ("想看", "，", "。"), ("请找动画：", "；", "。"), ("给我推荐动画，", "，", "。"),
    ("有没有这样的动画：", "；", "？"), ("帮我筛选作品，", "，", "。"),
    ("我想找一部动画，", "，", "。"), ("推荐一些满足这些条件的作品：", "；", "。"),
    ("这次想看动画，要求", "，", "。"), ("找动画，条件是", "，", "。"),
    ("能推荐动画吗？要求", "；", "。"), ("我的观看条件是：", "；", "。"),
    ("请按下面的偏好推荐动画：", "；", "。"), ("想找新作品，", "，", "。"),
    ("选几部动画给我，", "，", "。"), ("动画推荐：", "；", "。"),
    ("帮忙找番，", "，", "。"), ("筛一下动画吧，", "，", "。"),
    ("我在找动画：", "；", "。"))


def realize_final_text(spec, style, chinese=True):
    """Every clause is explicit; inclusive ranges and reference-only meaning survive."""
    clauses=[]
    for field in ("genres", "tags"):
        constraint=getattr(spec,field)
        def word(v):
            if not chinese: return v
            return GENRE_ALIASES.get(v,v) if field=="genres" else next(iter(TAG_ALIASES.get(v,[])),v)
        noun="题材" if field=="genres" else "标签"
        if constraint.all_of: clauses.append("同时包含"+"和".join(word(v) for v in constraint.all_of)+noun)
        if constraint.any_of: clauses.append(noun+"为"+"或".join(word(v) for v in constraint.any_of)+"中的任一种")
        if constraint.none_of: clauses.append("排除"+"和".join(word(v) for v in constraint.none_of)+noun)
    if spec.tag_groups.any_of: clauses.append("想要后宫类型")
    if spec.tag_groups.none_of: clauses.append("不要后宫")
    for field,unit in (("year","年"),("episodes","集")):
        r=getattr(spec,field)
        if r.min is not None and r.max is not None:
            clauses.append(("年份" if field=="year" else "集数")+f"在{r.min}到{r.max}{unit}之间（含端点）")
        elif r.min is not None: clauses.append(f"{r.min}年及以后" if field=="year" else f"至少{r.min}集")
        elif r.max is not None: clauses.append(f"{r.max}年及以前" if field=="year" else f"最多{r.max}集")
    if spec.formats: clauses.append("格式为"+"或".join(FORMAT_ALIASES.get(v,v) if chinese else v for v in spec.formats))
    if spec.status: clauses.append("状态为"+"或".join(STATUS_ALIASES.get(v,v) if chinese else v for v in spec.status))
    if spec.reference_titles: clauses.append("找类似"+"或".join(f"《{v}》" for v in spec.reference_titles)+"的作品")
    prefix,sep,suffix=STYLES[style % len(STYLES)]
    return prefix+sep.join(clauses)+suffix


def authored_challenges(rules):
    """40 explicitly authored evaluation cases, kept out of all training splits."""
    S=SemanticSpec; C=SetConstraintSpec; R=RangeConstraintSpec
    cases=[
      ("只要悬疑题材，最多二十四集。",S(genres=C(all_of=("Mystery",)),episodes=R(max=24))),
      ("科幻和悬疑必须同时有，格式选TV。",S(genres=C(all_of=("Mystery","Sci-Fi")),formats=("TV",))),
      ("科幻或者悬疑都行，但是别有后宫。",S(genres=C(any_of=("Mystery","Sci-Fi")),tag_groups=C(none_of=("HAREM",)))),
      ("只考虑2021年及以后的动画。",S(year=R(min=2021))),
      ("2013年及以前的科幻作品。",S(year=R(max=2013),genres=C(all_of=("Sci-Fi",)))),
      ("2014到2023年之间，起止年份都算。",S(year=R(min=2014,max=2023))),
      ("集数别超过十八集。",S(episodes=R(max=18))),
      ("至少十五集，可以长一些。",S(episodes=R(min=15),unresolved_preferences=("可以长一些",))),
      ("十二到二十六集都可以，包括十二集和二十六集。",S(episodes=R(min=12,max=26))),
      ("我只想看动画电影。",S(formats=("MOVIE",))),
      ("TV动画或动画电影都接受。",S(formats=("MOVIE","TV"))),
      ("已完结或正在连载都能接受。",S(status=("FINISHED","RELEASING"))),
      ("只要已经完结的作品，其他没有要求。",S(status=("FINISHED",))),
      ("想看异世界题材的已完结作品。",S(tags=C(all_of=("Isekai",)),status=("FINISHED",))),
      ("不要时间循环标签。",S(tags=C(none_of=("Time Loop",)))),
      ("包含时间循环标签的动画。",S(tags=C(all_of=("Time Loop",)))),
      ("有桌游或者电子游戏标签就可以。",S(tags=C(any_of=("Board Game","Video Games")))),
      ("要求同时有校园和学校社团标签。",S(tags=C(all_of=("School","School Club")))),
      ("排除恋爱以及恐怖题材。",S(genres=C(none_of=("Horror","Romance")))),
      ("喜剧或者日常题材都行。",S(genres=C(any_of=("Comedy","Slice of Life")))),
      ("想看后宫动画。",S(tag_groups=C(any_of=("HAREM",)))),
      ("不要后宫类型的任何作品。",S(tag_groups=C(none_of=("HAREM",)))),
      ("排除Female Harem标签就好。",S(tags=C(none_of=("Female Harem",)))),
      ("参考《Steins;Gate》推荐，别推断别的条件。",S(reference_titles=("Steins;Gate",))),
      ("类似《Attack on Titan》，但是不许有恋爱题材。",S(reference_titles=("Attack on Titan",),genres=C(none_of=("Romance",)))),
      ("2017年及以后，最多二十六集，科幻或悬疑的TV动画，排除后宫。",S(genres=C(any_of=("Mystery","Sci-Fi")),year=R(min=2017),episodes=R(max=26),formats=("TV",),tag_groups=C(none_of=("HAREM",)))),
      ("2022年及以后，至少六集，喜剧TV动画且已经完结。",S(genres=C(all_of=("Comedy",)),year=R(min=2022),episodes=R(min=6),formats=("TV",),status=("FINISHED",))),
      ("动画电影，2011年及以前，排除恐怖。",S(formats=("MOVIE",),year=R(max=2011),genres=C(none_of=("Horror",)))),
      ("战斗不作要求，只要机甲题材。",S(genres=C(all_of=("Mecha",)))),
      ("有哲学标签，至少十集。",S(tags=C(all_of=("Philosophy",)),episodes=R(min=10))),
      ("找群像TV动画，不要后宫。",S(tags=C(all_of=("Ensemble Cast",)),formats=("TV",),tag_groups=C(none_of=("HAREM",)))),
      ("我想看死亡游戏标签的作品。",S(tags=C(all_of=("Death Game",)))),
      ("排除校园和职场标签。",S(tags=C(none_of=("School","Work")))),
      ("OVA或特别篇，已完结。",S(formats=("OVA","SPECIAL"),status=("FINISHED",))),
      ("超自然和恐怖题材必须都有。",S(genres=C(all_of=("Horror","Supernatural")))),
      ("最多一集，格式是动画电影。",S(episodes=R(max=1),formats=("MOVIE",))),
      ("科幻TV动画，状态是正在连载。",S(genres=C(all_of=("Sci-Fi",)),formats=("TV",),status=("RELEASING",))),
      ("给我治愈系标签的动画，年份不晚于2019年。",S(tags=C(all_of=("Iyashikei",)),year=R(max=2019))),
      ("推荐带露营标签的作品，至少两集。",S(tags=C(all_of=("Camping",)),episodes=R(min=2))),
      ("想找节奏紧凑的作品。",S(unresolved_preferences=("节奏紧凑",))),
    ]
    return [{"challenge_id":f"final_challenge_{i:03d}","user_text":text,"gold_query":build_query(spec,rules)}
            for i,(text,spec) in enumerate(cases,1)]


def generate_final_dataset(root, count=1500, seed=20261004):
    """Deterministic 80/10/10 dataset, with simple exact-text hygiene checks."""
    rules,subset=build_real_domain(root)
    config=load_sampler_config(root / "configs/semantic_sampler.v0.2.json")
    refs=load_reference_title_pool(root / "data/domain/reference_titles.v0.2.json")
    patterns=reviewed_patterns(); rng=Random(seed)
    challenges=authored_challenges(rules)
    # Historical frozen evaluation texts also stay outside the new training corpus.
    used={c["user_text"] for c in challenges}
    for path in (root / "data/pilot").glob("*.jsonl"):
        if path.name.startswith(("test.","validation.","challenge.")):
            used.update(json.loads(l)["user_text"] for l in path.read_text(encoding="utf-8").splitlines())
    records=[]; attempts=0
    while len(records)<count:
        attempts+=1
        if attempts>count*20: raise RuntimeError("cannot find enough unique controlled texts")
        pattern=patterns[(attempts-1) % len(patterns)]
        draw_seed=rng.randrange(2**32); draw_rng=Random(draw_seed)
        spec=sample_semantic_spec_from_pattern(pattern,config,rules,subset,refs,draw_rng)
        # v0.2 explicitly exercises two-value OR lists; hard count stays +1.
        if spec.formats and draw_rng.random()<0.2:
            spec=replace(spec,formats=tuple(sorted(draw_rng.sample(sorted(rules.formats),2))))
        if spec.status and draw_rng.random()<0.2:
            spec=replace(spec,status=tuple(sorted(draw_rng.sample(sorted(rules.statuses),2))))
        style=draw_rng.randrange(len(STYLES))
        text=realize_final_text(spec,style,chinese=draw_rng.random()<0.75)
        if text in used: continue
        used.add(text)
        records.append(build_dataset_record(semantic_spec=spec,rules=rules,executable_subset=subset,
            dataset_version="anime-pref-final-v0.2",semantic_family=pattern.semantic_family,
            generation_family=f"controlled_style_{style:02d}",template_id=f"v02_pattern_{(attempts-1)%len(patterns):03d}_style_{style:02d}",
            seed=draw_seed,user_text=text))
    # Shuffle once after construction; evaluation records never feed back into generation.
    rng.shuffle(records)
    ntrain=int(count*.8); nval=int(count*.1)
    splits={"train":tuple(records[:ntrain]),"validation":tuple(records[ntrain:ntrain+nval]),"test":tuple(records[ntrain+nval:])}
    for left in splits:
        for right in splits:
            if left>=right: continue
            assert not {r.user_text for r in splits[left]} & {r.user_text for r in splits[right]}
    out=root / "data/final"
    out.mkdir(parents=True,exist_ok=True)
    for split,rows in splits.items():
        (out / f"{split}.v0.2.jsonl").write_text(records_to_jsonl(rows),encoding="utf-8",newline="")
    (out / "challenge.v0.2.jsonl").write_text("".join(json.dumps(c,ensure_ascii=False,sort_keys=True)+"\n" for c in challenges),encoding="utf-8",newline="")
    audit={"dataset_version":"anime-pref-final-v0.2","seed":seed,"count":count,
        "splits":{k:len(v) for k,v in splits.items()},"challenge_count":len(challenges),
        "semantic_families":dict(Counter(r.semantic_family for r in records)),
        "constraint_counts":dict(Counter(r.constraint_count for r in records)),
        "genre_values":sorted({v for r in records for op in (r.semantic_spec.genres.all_of,r.semantic_spec.genres.any_of,r.semantic_spec.genres.none_of) for v in op}),
        "tag_values":sorted({v for r in records for op in (r.semantic_spec.tags.all_of,r.semantic_spec.tags.any_of,r.semantic_spec.tags.none_of) for v in op}),
        "multivalue_formats":sum(len(r.semantic_spec.formats)>1 for r in records),
        "multivalue_statuses":sum(len(r.semantic_spec.status)>1 for r in records),
        "cross_split_exact_text_overlap":0,"cross_split_exact_pair_overlap":0,
        "rules_hash":rules.rules_hash,"subset_hash":rules.executable_subset_hash,
        "reference_pool_count":len(refs.titles),"approved_tag_count":len(subset.tags),
        "controlled_styles":len(STYLES),"patterns":len(patterns)}
    write_json(out / "audit.json",audit)
    write_json(out / "reviewed_patterns.json",[asdict(p) for p in patterns])
    return audit
