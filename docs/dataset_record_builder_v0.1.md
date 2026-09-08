# DatasetRecord Builder v0.1 实现任务

## 本工作块边界

本工作块实现 structural/domain validation 分层和 DatasetRecord Builder。不要实现 semantic
sampler、语言模板、LLM paraphrase、split 或训练。

## Validation 分层

```text
raw model text
    ↓ parser（以后实现）
JSON value / parse validity
    ↓ validate_query_structure
structural/schema validity
    ↓ validate_query_domain(query, rules)
domain/executable-vocabulary validity
```

三个结果以后必须分别统计。`validate_query()` 暂时保留为 structural validator 的兼容名称；
新 evaluation 代码应使用显式函数名。

## 文件和 TODO

### `data/domain_validation.py`

`TODO-19` 实现 `validate_query_domain()`。它先要求 structural validity，再检查 executable
genre/tag/format/status、approved soft vocabulary 和 versioned numeric rules。它不做任何
canonicalization，也不处理 reference/unresolved 文本。需要检查 `DomainRules` 运行时类型时，
在函数内部局部导入该类，避免 `query_builder` 与 `domain_validation` 形成循环导入。

完成后在 `build_query()` 的 `TODO-19b` 将返回对象先保存为变量，并依次调用：

```python
validate_query_structure(query)
validate_query_domain(query, rules)
return query
```

### `data/dataset_record_builder.py`

按顺序实现：

1. `TODO-20 count_hard_semantic_clauses()`
2. `TODO-21 collect_normalization_rule_ids()`
3. `TODO-22 make_sample_id()`
4. `TODO-23 build_dataset_record()`
5. `TODO-24 validate_dataset_record()`

每完成一个 TODO，只移除 `tests/test_dataset_record_builder.py` 中对应测试的 skip。

## Constraint count 逐项规则

对 genres、tags、tag_groups 各自计算：

```text
len(all_of)
+ (1 if any_of else 0)
+ len(none_of)
```

tag group 在展开前计算，所以 HAREM 的三个实际 tags 仍只代表一个 concept。year 与 episodes
每个存在的 bound 加 1；formats/status 每个非空 OR list 加 1。三个非 hard 文本字段不计数。

## Deterministic sample ID

identity payload 应显式包含版本、pre-expansion SemanticSpec、canonical Gold Query、family、
template、normalization rule IDs、seed、user text 和 optional paraphrase metadata。先转换为只含
JSON types 的 mapping，再 canonical JSON serialization，最后计算 SHA-256。

固定输出格式：

```text
sample_<64 lowercase hex characters>
```

不得使用 Python `hash()`，因为它不保证跨进程稳定；不得使用时间或新随机数，因为相同输入
必须得到相同 ID。

## 一致性验证

`validate_dataset_record()` 不能只检查字段类型。它必须从 `semantic_spec` 和 `rules` 重算：

- Gold Query
- constraint signature
- constraint count
- normalization rule IDs
- sample ID

比较 Gold Query 时先 canonicalize，因此 key order 和 set-like list order 不造成误判。任何不
一致直接报错，不能把重算值写回 record。

## Year 与 episodes

- year validity：1900–2100，来自 versioned config，仅用于 corruption/sanity guard。
- episodes validity：最小 1，maximum 仍为 null。
- sampler distribution bounds 不属于本工作块。

## 测试顺序

```powershell
python -B -m unittest tests.test_dataset_record_builder -v
python -B -m unittest discover -s tests -v
```

跳过的测试表示对应 TODO 尚未实现，不能当作通过。

## Taxonomy 后续边界

进入 sampler 前还需要单独实现完整 GenreCollection/MediaTagCollection snapshot 和 reviewed
executable tag subset。snapshot hash 针对筛选字段、canonical sort 后的 canonical JSON，不能
直接 hash HTTP response bytes。该模块不在本工作块实现。
