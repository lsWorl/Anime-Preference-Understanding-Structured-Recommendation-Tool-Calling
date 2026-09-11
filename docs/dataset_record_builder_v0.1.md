# DatasetRecord Builder v0.1 实现说明

> 2026-09-10 更新：TODO-19–24 对应功能已实现，下面的编号保留为学习路径。本文“按顺序实现/移除 skip”描述历史练习流程，不表示这些函数仍为空。当前该模块6项测试与 taxonomy 模块12项测试均已启用。

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

genres 按以下规则计算：

```text
len(all_of)
+ (1 if any_of else 0)
+ len(none_of)
```

tags 与 tag_groups 仍在展开前计算，但两者的非空 `any_of` 共同组成一个 TAG_ANY OR
clause，因此总共最多加 1。它们的 `all_of` 和 `none_of` 继续按每个直接 item additive
计数。HAREM 的三个展开 tags 仍只代表一个 concept。year 与 episodes 每个存在的 bound
加 1；formats/status 每个非空 OR list 加 1。三个非 hard 文本字段不计数。

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

## `build_dataset_record()` 实现说明

这个函数是 dataset record 的唯一组装入口。调用方只传入源语义、规则、生成元数据和原始
用户文本；所有可推导字段都由函数内部计算，不能由调用方覆盖。

实现按以下顺序执行：

1. `gold_query = build_query(semantic_spec, rules)`：验证 canonical semantic spec，应用
   normalization rules，并生成完整显式 Gold Query。`build_query()` 已保证 structural 和
   domain validity。
2. `build_constraint_signature(gold_query)`：根据展开后的 executable hard constraints 计算
   固定顺序的结构签名。
3. `count_hard_semantic_clauses(semantic_spec)`：从展开前语义计算用户表达的 hard clause
   数量，因此 HAREM 仍按一个 concept 计数。
4. `collect_normalization_rule_ids(semantic_spec, rules)`：从展开前 tag groups 收集实际使用
   的 normalization provenance。
5. `make_sample_id(...)`：把 schema/dataset/rules/subset identity、语义、Gold Query、family、template、规则 ID、seed、原始
   文本和 optional paraphrase metadata 全部纳入确定性 SHA-256 identity。
6. `DatasetRecordSpec(...)`：保存源字段和上述派生字段。`schema_version` 始终读取
   `rules.schema_version`，函数签名不允许调用方另传；`sample_id`、Gold Query、signature、
   count 和 normalization rule IDs 同样不能由调用方覆盖。

逐行数据流如下：

```text
semantic_spec + rules
    -> build_query
    -> gold_query
    -> build_constraint_signature

semantic_spec
    -> count_hard_semantic_clauses

semantic_spec + rules
    -> collect_normalization_rule_ids

全部源字段 + 全部派生字段
    -> make_sample_id
    -> DatasetRecordSpec
```

函数不 strip 或改写 `user_text`。它通过 `make_sample_id()` 复用 metadata 验证；空白或类型
错误会抛出 `ValueError`，合法的 raw text 按原值同时进入 sample identity 与 record。

## Year 与 episodes

- year validity：1900–2100，来自 versioned config，仅用于 corruption/sanity guard。
- episodes validity：最小 1，maximum 仍为 null。
- sampler distribution bounds 不属于本工作块。

## 测试顺序

```powershell
python -B -m unittest tests.test_dataset_record_builder -v
python -B -m unittest discover -s tests -v
```

截至 2026-09-11，完整测试集48项全部通过且无跳过。后续若新增 skip，仍应把它视为
未执行的契约，而不是通过。

## Taxonomy 边界

taxonomy snapshot 与 reviewed executable tag subset 代码现已实现，但它们仍是与
DatasetRecord Builder 分离的治理流程。snapshot hash 针对筛选字段、canonical sort 后的
canonical JSON，不能直接 hash HTTP response bytes。正式进入 sampler 前仍需完成真实采集、
人工审核，并记录使用的 snapshot/subset 版本关系。


## 当前实现中的阅读重点

- count_hard_semantic_clauses 先验证基本结构，再在展开前计数；它没有 rules，不替代领域校验。
- collect_normalization_rule_ids 先调用 build_query，然后收集实际组来源；重复 ID 报错，返回升序 tuple。
- make_sample_id 只负责身份编码，不单独检验 spec/Gold 一致；user_text 允许有意义文本的首尾空白并原样参与哈希。
- validate_dataset_record 先验证 Gold 并重建期望 Gold，然后用源字段重建整条记录，比较 signature/count/rule IDs/sample ID，不修改记录。
- 记录一致性不等于自然语言与 Gold 对齐验证，当前没有语义解析器。

完整函数拆解与可运行例子见 [项目实现学习手册](项目实现学习手册.md) 第13–17章。
