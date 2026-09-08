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

    # This dataclass only stores the frozen outer shape. Construction and
    # cross-field consistency checks belong to data/dataset_record_builder.py.
    # split remains a later dataset-partition field and is intentionally absent.
