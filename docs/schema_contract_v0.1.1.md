# Schema Contract v0.1.1 实现说明

本工作块修正 semantic spec、domain rules、Gold Query validation、canonical
serialization、constraint signature 和 dataset record provenance。它不包含 semantic
sampler、自然语言模板、数据集切分或训练。

## 文件职责

- `configs/domain_rules.v0.1.1.json`：版本化 executable taxonomy、tag group operator、
  normalization rule ID、soft vocabulary 和 numeric rules。
- `schemas/preference_query.py`：canonical `SemanticSpec` 数据结构。
- `schemas/dataset_record.py`：dataset 外层 provenance 字段定义。
- `data/query_builder.py`：加载规则、验证 SemanticSpec、展开规则并生成完整 Gold Query。
- `data/query_validation.py`：Gold Query 的共享 semantic validator 和 canonicalizer。
- `data/constraint_signature.py`：从已验证 query 提取结构签名。
- `tests/test_schema_contract_v011.py`：理论契约的自动回归测试。

## 调用关系

```text
domain_rules.v0.1.1.json
        ↓ load_domain_rules
DomainRules + SemanticSpec
        ↓ build_query
full-schema Gold Query
        ↓ validate_query
semantic validity
        ↓ canonicalize_query
fixed key order + sorted set values
        ├─ dumps_query
        └─ build_constraint_signature
```

## 数据结构

`TagGroupRule` 是不可变 dataclass：

- `tags`：展开后的 AniList tags，使用 tuple。
- `allowed_operators`：允许使用该组的 operator，使用 frozenset。
- `normalization_rule_id`：写入 dataset provenance 的规则标识。

`NumericRule` 保存可选的 `minimum/maximum`。当前 episodes minimum 为 1；year
上下界未冻结，因此均为 null。

`DomainRules` 保存 taxonomy allowlist、tag groups、approved soft vocabulary 和 numeric
rules。tag group 映射由 `MappingProxyType` 包装，调用方不能修改。

`DatasetRecordSpec` 仅预留 provenance 字段。`split` 将在后续划分阶段加入；record
builder 和 `constraint_count` 的计算尚未实现。

## 函数执行说明

### `load_domain_rules(path)`

1. 以 UTF-8 读取 JSON，把文件、编码和 JSON 错误统一转换为 `ValueError`。
2. 检查顶层、taxonomy、tag group、numeric rule 和 bound 的精确键集合。
3. 检查 taxonomy 列表的类型、空值与规范化后重复值。
4. 检查每个 tag group 的成员均属于 executable tag allowlist。
5. 检查 operator 仅来自 `all_of/any_of/none_of`。
6. 检查 normalization rule ID 非空、无首尾 whitespace 且全局唯一。
7. 检查 numeric bound 是 int 或 null，显式排除 bool，并保证 minimum 不大于 maximum。
8. 将可变 JSON 容器转换为 tuple、frozenset、frozen dataclass 和只读 mapping。

代码没有按 `HAREM` 名称分支；HAREM 禁止 `all_of` 完全来自配置中的
`allowed_operators`。

### `build_query(spec, rules)`

1. 要求输入分别是 `SemanticSpec` 和 `DomainRules`。
2. 对每个 tuple 检查元素类型、空字符串、首尾 whitespace 和重复值。
3. genres、tags、formats、status 和 tag group 必须精确命中对应 allowlist。
4. 检查 `all_of/any_of/none_of` 之间不能出现交叉重复。
5. 按配置检查每个 tag group 的 operator，再展开成真实 tags。
6. 显式 tag 与 group expansion 重复时直接报错，不自动去重。
7. 对 year/episodes 检查 int、bool、min/max 顺序和版本化 numeric rule。
8. soft preference 必须命中 approved vocabulary；builder 不会自动移动到 unresolved。
9. set-like 字段排序；reference、soft、unresolved 保持输入顺序。
10. 输出所有 Schema 字段；空列表和 null bound 不省略。

### `validate_query(query)`

1. 比较每层 key 的集合，不比较 JSON object key order。
2. 要求集合字段和文本字段为 JSON list，元素为非空字符串。
3. 拒绝带首尾 whitespace 的 canonical 字符串。
4. 拒绝列表内重复值和 set operator 之间的重叠。
5. 检查 range 类型、min/max 顺序以及 episodes bound 至少为 1。
6. 把 formats/status 视为普通 OR list，不接受 NOT 结构。
7. 不检查 taxonomy membership；该职责属于 builder。
8. 成功返回 `None`，且不修改调用方对象。

### `canonicalize_query(query)`

1. 首先调用 `validate_query()`。
2. 按常量定义重建顶层、hard constraints、operator 和 range 的键顺序。
3. 对 genres、tags、formats、status 排序。
4. 保持 reference、soft、unresolved 的值与顺序。
5. 返回全新 dict，保留空列表和 null bound。

### `dumps_query(query)`

1. 调用 `canonicalize_query()`，不维护第二套 validation。
2. 使用 `ensure_ascii=False` 保留 Unicode。
3. 使用紧凑 separators 和 `allow_nan=False` 输出稳定单行 JSON。

### `build_constraint_signature(query)`

1. 调用共享 `validate_query()`。
2. 只读取 hard constraints 是否活跃，不读取具体取值。
3. 按固定 `SIGNATURE_ORDER` 连接 token。
4. 没有 hard constraint 时返回 `NO_HARD_CONSTRAINT`。

## 已验证行为

- HAREM 正向进入 `tags.any_of`，负向进入 `tags.none_of`，`all_of` 被拒绝。
- 显式 tag 与 group expansion 重复会报错。
- reordered JSON keys 不影响合法性；serializer 恢复固定顺序。
- set-like 输入顺序不影响 canonical 输出。
- validator、serializer 和 signature 都拒绝首尾 whitespace。
- serializer 和 signature 复用同一个 validator。
- 当前完整测试为 23 个，全部通过。

运行命令：

```powershell
python -B -m unittest discover -s tests -v
```

## 尚未冻结或尚未实现

- `constraint_count` 的计算单位。
- year 的 basic reasonable range。
- approved soft preference vocabulary；当前为空。
- 完整 AniList taxonomy snapshot、fetch date/version/hash。
- 人工审核后的 executable tag subset。
- dataset record builder、semantic sampler、controlled language realization 和 split。
