"""Dataset record provenance contract for Schema Contract v0.1.1.

This is the dataset's outer record. Its metadata is not part of the model's
AnimePreferenceQuery Gold JSON.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from anime_pref.schemas.preference_query import SemanticSpec


@dataclass(frozen=True)
class DatasetRecordSpec:
    sample_id: str
    schema_version: str
    dataset_version: str
    semantic_spec: SemanticSpec
    gold_query: Mapping[str, Any]
    constraint_signature: str
    constraint_count: int
    semantic_family: str
    generation_family: str
    template_id: str
    normalization_rule_ids: tuple[str, ...]
    seed: int
    user_text: str
    paraphrase_model: str | None = None
    prompt_version: str | None = None

    # TODO-17: 本工作块只冻结字段，不实现 record builder。
    # 后续实现时必须校验非空 ID/version/family/template/user_text、seed 排除 bool、
    # constraint_count 的正式计数定义、normalization_rule_ids 无重复且无首尾空格，
    # 并验证 gold_query/signature 与 semantic_spec 一致。
    # split 按理论结论留到后续划分阶段，不在此 dataclass 中加入。
