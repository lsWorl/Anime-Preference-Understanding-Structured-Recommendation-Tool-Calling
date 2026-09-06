"""Build deterministic AnimePreferenceQuery v0.1 Gold JSON.

This module must only validate, expand approved rules, and serialize semantics.
It must never infer a preference or silently repair an invalid specification.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from anime_pref.schemas.preference_query import SemanticSpec


@dataclass(frozen=True)
class DomainRules:
    schema_version: str
    genres: frozenset[str]
    tags: frozenset[str]
    formats: frozenset[str]
    statuses: frozenset[str]
    tag_groups: Mapping[str, tuple[str, ...]]


def load_domain_rules(path: Path) -> DomainRules:
    """Load and validate one versioned domain-rules JSON file."""
    # TODO-07: 使用 UTF-8 读取 JSON，并严格验证以下结构：
    # schema_version 是非空字符串；taxonomy 下四个 allowlist 是无重复非空字符串列表；
    # tag_groups 是 {非空组名: 非空 tag 列表}；展开出的每个 tag 都必须存在于
    # taxonomy.tags。配置缺失、类型错误、重复或未知 tag 时统一抛 ValueError，
    # 文件/JSON 解码异常保留原始异常原因。不要忽略未知的顶层键。
    raise NotImplementedError("TODO-07: load and validate domain rules")


def build_query(spec: SemanticSpec, rules: DomainRules) -> dict[str, Any]:
    """Validate a semantic spec and deterministically build Gold JSON v0.1."""
    # TODO-08: 实现时遵守以下契约：
    # 1. spec 必须是 SemanticSpec；每个字符串非空，禁止重复值。
    # 2. genre/tag/format/status 必须命中相应 allowlist；禁止近似匹配或猜测。
    # 3. tag_groups 只接受 rules.tag_groups 中的组名，并按相同 operator 展开；
    #    HAREM 等组名不得出现在最终 JSON。
    # 4. 同一字段的 all_of/any_of/none_of 不得出现交叉重复；展开后再次检查。
    # 5. year/episodes 的 bound 只接受 int（排除 bool）；min > max 时抛 ValueError。
    #    不要在这里发明理论分支没有批准的数值范围或默认值。
    # 6. reference_titles/soft_preferences/unresolved_preferences 只校验并原样复制；
    #    不得增删、改写或互相移动。
    # 7. 所有非法 spec 抛 ValueError，不能静默丢弃 constraint。
    # 8. 输出必须显式包含完整 Schema v0.1 键；空集合为 []，空 bound 为 None。
    # 9. 为消除采样顺序对 Gold 的影响，constraint 枚举值按字符串升序输出；
    #    顶层键和子键严格采用测试中的固定顺序。
    raise NotImplementedError("TODO-08: build deterministic Gold JSON")


def dumps_query(query: Mapping[str, Any]) -> str:
    """Serialize a validated query in one canonical, Unicode-preserving form."""
    # TODO-09: 调用前先确认 query 具有完整 Schema v0.1 结构；随后使用固定参数
    # json.dumps(..., ensure_ascii=False, separators=(",", ":"))。
    # 不要使用 sort_keys=True 改变 Schema 约定的键顺序，也不要接受 NaN/Infinity。
    raise NotImplementedError("TODO-09: serialize canonical Gold JSON")

