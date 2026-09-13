# F1.1 Pilot Split Hygiene 实现报告

## 1. 本次修正的目标

F1 的生成管线、受控语言和 DatasetRecord 构造保持不变。本次只补充 train、validation、test 的重复与泄漏检查，并调整少量显式 seed，使 evaluation split 不包含重复的 exact example。

当前结果：

- train↔validation 的 exact user text overlap：0；
- train↔validation 的 exact `(user_text, Gold)` overlap：0；
- train↔test 的两项 overlap：0；
- validation↔test 的两项 overlap：0；
- validation 内 exact user text / exact pair duplicate：0 / 0；
- test 内 exact user text / exact pair duplicate：0 / 0；
- train 内 exact pair duplicate excess：66，保留并报告；
- train↔validation 的 SemanticSpec overlap：2，按理论合同允许。

## 2. 新增函数

### `_record_hygiene_keys(record)`

为一条 `DatasetRecordSpec` 构造三种 canonical comparison key：

1. `exact_user_text`：原始受控文本；
2. `user_text_plus_gold`：user text 与 canonical Gold JSON 的无歧义组合；
3. `semantic_spec`：canonical SemanticSpec JSON。

Gold 和 SemanticSpec 都使用稳定 key order、compact JSON 和 Unicode serialization。组合 key 使用 JSON array，不通过字符串分隔符拼接，避免文本本身包含分隔符时发生碰撞。

### `audit_pilot_split_hygiene(splits)`

输入：

```python
{
    "train": tuple[DatasetRecordSpec, ...],
    "validation": tuple[DatasetRecordSpec, ...],
    "test": tuple[DatasetRecordSpec, ...],
}
```

输出分为两部分：

```python
{
    "pairwise": {
        "train<->validation": {
            "exact_user_text": 0,
            "user_text_plus_gold": 0,
            "semantic_spec": 2,
        },
        ...
    },
    "within_split": {
        "train": {...},
        "validation": {...},
        "test": {...},
    },
}
```

pairwise 数值表示两个 split 共享的 distinct key 数量。within-split 数值表示 duplicate excess，即记录数减去唯一 key 数。

### `validate_pilot_split_hygiene(hygiene)`

执行 F1.1 的硬边界：

- 任意两个 split 之间的 exact user text 必须为 0；
- 任意两个 split 之间的 exact `(user_text, Gold)` 必须为 0；
- validation/test 内部的 exact user text duplicate 必须为 0；
- validation/test 内部的 exact pair duplicate 必须为 0。

SemanticSpec 跨 split overlap 只统计，不拒绝。同一语义通过不同文本表达属于后续希望测量的泛化能力。

### `split_pilot_records(...)` 的调用变化

原有 sample ID 集合关系和 template ID 隔离验证完成后，现在继续执行：

```python
hygiene = audit_pilot_split_hygiene(result)
validate_pilot_split_hygiene(hygiene)
```

因此受污染的 split 无法从正式 split API 成功返回，而不是只在离线报告里留下警告。

### `render_pilot_audit_markdown(...)` 的调用变化

新增 `split_hygiene` 参数，并在审计文档中写出：

- 三组 split pair 的三类 overlap；
- 三个 split 内部的三类 duplicate excess。

## 3. Seed 调整

没有修改 sampler、E3 binder、structural pattern、generation family 或 template ID。只替换 `case_020` 至 `case_024` 中会在 evaluation split 内产生重复 exact pair 的显式 seed。

seed 选择仍然写死在 reviewed manifest 中，保持升序、确定性与可审查性。总量继续为 24 cases × 10 seeds = 240 records，划分继续为 180/30/30。

## 4. 一条记录如何进入 split hygiene 检查

以 validation 中一条 `case_020` 记录为例：

```text
manifest case + explicit seed
-> E3 SemanticSpec
-> controlled user_text
-> DatasetRecord builder + validator
-> split_pilot_records 根据 template_id 放入 validation
-> _record_hygiene_keys 生成 text / pair / spec 三个 key
-> audit_pilot_split_hygiene 计算集合交集与 split 内唯一数
-> validate_pilot_split_hygiene 验证 exact-example hygiene
-> 写入 validation.v0.1.jsonl
```

假设该记录的文本和 Gold 与某条 train record 完全相同，`train<->validation.user_text_plus_gold` 会大于 0，split 函数立即抛出 `ValueError`。如果 SemanticSpec 相同但 user text 不同，只增加 SemanticSpec overlap 统计，不阻止生成。

## 5. 自动测试

新增测试覆盖：

- 三组 split 的 exact user text 与 exact pair overlap 全为 0；
- validation/test 内部 exact text 与 exact pair duplicate 全为 0；
- train duplicate 继续保留并报告；
- SemanticSpec overlap 不被 validator 错误拒绝；
- 人工注入跨 split exact example 后 validator 必须失败；
- Markdown 必须包含 cross-split 和 within-split 两张 hygiene 表；
- 重新生成的 JSONL 与 checked-in output 字节一致。

## 6. 阶段边界

本次没有引入 dedup framework、自动重采样、LLM paraphrase 或新的 generation family，也没有开始 E0、SFT serialization、tokenizer statistics 或训练。
