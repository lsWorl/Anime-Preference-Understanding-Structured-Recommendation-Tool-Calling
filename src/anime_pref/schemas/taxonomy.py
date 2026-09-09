"""Data contracts for AniList taxonomy snapshots and reviewed tag subsets."""

from dataclasses import dataclass


# 全局 tag 身份和描述；rank 属于作品与 tag 的关联，不属于此模型。
@dataclass(frozen=True)
class TaxonomyTagSpec:
    id: int
    name: str
    description: str | None
    category: str
    is_general_spoiler: bool
    is_adult: bool


# 计划参与内容哈希的 canonical 数据；获取时间放在另一个 manifest。
@dataclass(frozen=True)
class CanonicalTaxonomySnapshot:
    snapshot_schema_version: str
    genres: tuple[str, ...]
    tags: tuple[TaxonomyTagSpec, ...]


# 来源/获取时间/数量与内容身份摘要；字段定义已存在，构建函数仍待实现。
@dataclass(frozen=True)
class TaxonomySnapshotManifest:
    source: str
    resource: tuple[str, ...]
    fetched_at_utc: str
    genre_count: int
    tag_count: int
    canonical_sha256: str
    snapshot_schema_version: str


# 人工审核记录，approved 必须显式给出；source_snapshot_hash 绑定被审核快照。
@dataclass(frozen=True)
class TagAuditRecordSpec:
    tag_id: int
    tag_name: str
    category: str
    approved: bool
    reason: str
    aliases: tuple[str, ...]
    is_general_spoiler: bool
    is_adult: bool
    source_snapshot_hash: str


# 批准后供可执行词表使用的 tag；保留 aliases，审核理由留在原 audit。
@dataclass(frozen=True)
class ExecutableTagSpec:
    tag_id: int
    tag_name: str
    category: str
    aliases: tuple[str, ...]
    is_general_spoiler: bool
    is_adult: bool


# 单独版本化的批准子集，通过 hash 指向来源快照；不是全量 taxonomy。
@dataclass(frozen=True)
class ExecutableTagSubset:
    subset_version: str
    derived_from_snapshot_hash: str
    tags: tuple[ExecutableTagSpec, ...]


# 保存子集身份和数量，区分 subset_hash 与 derived_from_snapshot_hash。
@dataclass(frozen=True)
class ExecutableTagSubsetManifest:
    subset_version: str
    subset_hash: str
    derived_from_snapshot_hash: str
    approved_tag_count: int


