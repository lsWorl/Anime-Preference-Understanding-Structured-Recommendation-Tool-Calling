"""Dataset record provenance contract for Schema Contract v0.1.1.

This is the dataset's outer record. Its metadata is not part of the model's
AnimePreferenceQuery Gold JSON.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from anime_pref.schemas.preference_query import SemanticSpec


# 外层记录分开保存输入来源与派生目标；不是模型应输出的 Gold JSON 本体。
# frozen 只禁止字段重新赋值，gold_query 的嵌套 dict/list 仍需一致性校验保护。
@dataclass(frozen=True)
class DatasetRecordSpec:
    """One training-data record containing source semantics and derived fields.

    Callers should construct and check records through ``build_dataset_record``
    and ``validate_dataset_record`` because this dataclass cannot enforce
    relationships between Gold, signatures, counts, rule IDs, and sample ID.
    """

    sample_id: str
    schema_version: str
    dataset_version: str

    # Approved executable tag pool identity.
    executable_subset_version: str
    executable_subset_hash: str

    # Active executable rules identity.
    rules_version: str
    rules_hash: str

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

    # This dataclass only stores the frozen outer shape. Construction and
    # cross-field consistency checks belong to data/dataset_record_builder.py.
    # split remains a later dataset-partition field and is intentionally absent.
