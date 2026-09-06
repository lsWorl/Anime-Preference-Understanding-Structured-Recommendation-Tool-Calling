# Schema Contract v0.1.1 实现说明

本工作块只修正 semantic spec、domain rules、Gold Query validation、canonical
serialization、constraint signature 和 dataset record provenance。

## 文件职责

- `configs/domain_rules.v0.1.1.json`：版本化 executable taxonomy、tag group operator、
  normalization rule ID 和 numeric rule。当前 approved soft vocabulary 为空。
- `schemas/preference_query.py`：canonical semantic layer；不保存 raw user utterance。
- `schemas/dataset_record.py`：dataset 外层 provenance 字段；这些字段不进入 Gold JSON。
- `data/query_validation.py`：唯一的 Gold Query semantic validator 和 canonicalizer。
- `data/query_builder.py`：验证 SemanticSpec、应用 domain rules、构建完整 Gold Query。
- `data/constraint_signature.py`：在统一验证后统计 hard constraint pattern。
- `tests/test_schema_contract_v011.py`：理论结论对应的 executable contract。

## 函数契约与调用关系

```text
domain_rules.v0.1.1.json
        ↓ load_domain_rules            TODO-12
DomainRules + SemanticSpec
        ↓ build_query                  TODO-13
unordered-but-valid Gold Query
        ↓ validate_query               TODO-14a
semantic validity
        ↓ canonicalize_query           TODO-14b
fixed key order + sorted set values
        ├─ dumps_query                 TODO-15
        └─ build_constraint_signature  TODO-16
```

### `load_domain_rules(path)`

输入是 v0.1.1 JSON 路径，输出不可变 `DomainRules`。它负责配置结构和引用完整性，
不负责处理用户表达。HAREM 限制必须来自 `allowed_operators`，不能由代码检查组名。

### `build_query(spec, rules)`

输入是 canonical `SemanticSpec` 和已验证规则，输出完整显式 Gold Query dict。它不得
读取 raw utterance、猜测 taxonomy、静默 strip、自动移动 soft/unresolved 或自动去重。

### `validate_query(query)`

只判断 JSON 的结构和语义是否合法。JSON object 的 key order 以及 set-like list 的顺序
不属于语义，因此不能导致失败。该函数不修改输入，成功返回 `None`。

### `canonicalize_query(query)`

先复用 `validate_query()`，然后创建新 dict，以固定 key order 输出，并对 genres、tags、
formats、status 排序。三个文本列表保留原值和原顺序。

### `dumps_query(query)`

只负责 canonicalize 后的紧凑 Unicode JSON 序列化，不再维护独立 validation 规则。

### `build_constraint_signature(query)`

先调用统一 `validate_query()`，再按 `SIGNATURE_ORDER` 读取 hard constraints。它继续忽略
reference、soft 和 unresolved 的内容。

## 实现顺序

一次只完成一个 TODO：

1. TODO-12：DomainRules v0.1.1 与 loader，随后启用 TODO-18a。
2. TODO-13：SemanticSpec builder contract，随后启用 TODO-18b/18c。
3. TODO-14：统一 validator/canonicalizer，随后启用 TODO-18d。
4. TODO-15：serializer 复用，随后启用 TODO-18e。
5. TODO-16：signature 复用，随后启用 TODO-18f。
6. TODO-17：当前仅冻结 record 字段；等 constraint_count 定义确认后再实现 builder。

每次运行：

```powershell
python -B -m unittest discover -s tests -v
```

被 skip 的 v0.1.1 测试代表尚未实现，不能视为通过。旧 v0.1 测试应持续通过，直到对应
迁移步骤完成并更新为 v0.1.1 fixture。

## 暂未冻结的点

- `constraint_count` 的计算单位尚未定义：active slot、leaf value、numeric bound 还是组合。
- year 的 basic reasonable range 尚无精确数值；配置暂以 null 表示未冻结。
- approved soft preference vocabulary 当前为空。
- 完整 AniList taxonomy snapshot 与 executable tag subset audit 尚未开始。
