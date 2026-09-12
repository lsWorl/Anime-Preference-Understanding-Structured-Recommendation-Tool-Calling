# E2A. Domain-Conditioned Structural Support Contract v0.1 Review Bundle

## 审查范围

```text
validated D5A enabled support
+ D5B mechanics support
+ E1 domain bindability
        ↓
domain-bindable mechanics/signature tuples
```

无 RNG、无 probability conditioning、无 concrete values。

## 核心文件

- `src/anime_pref/sampling/domain_conditioned_support.py`
- `tests/test_domain_conditioned_support.py`
- `docs/domain_conditioned_support_v0.1_IMPLEMENTATION.md`

## 合同落实

- D4/D5A/D5B/D5C1/D5C2 均未修改。
- Mechanics support 从 D5B `mechanics_candidates()` 开始。
- E1 validator 是唯一 domain-bindability truth source。
- Mechanics 过滤保持 D5B canonical order。
- Signature support 只从 D5A `signature_probabilities()` 的 enabled keys 开始。
- Signature 过滤保持 D5A canonical order。
- Signature 当且仅当至少有一个 bindable mechanics 时保留。
- D5A-disabled signature 不会重新启用。
- Invalid resource/provenance 先抛错，不解释为 zero capacity。
- E1 `ValueError` 表示 candidate 不进入 support；其他异常不吞掉。
- Zero-capacity context 返回空 tuple。
- Candidate count 不转换成 weight。
- 无 fallback、retry、resampling 或 inactive-tag activation。

## Synthetic integration finding

当前 synthetic domain 下：

```text
normalization / 5_plus
signature = (genre_set, tag_set, tag_group_none)
```

因为 HAREM expansion 覆盖全部 active tags：

```text
bindable mechanics = 0
bindable signatures = 0
```

显式激活 approved `Ensemble Cast` 并更新 rules identity 后：

```text
bindable mechanics = 2
bindable signatures = 1
```

这证明 mechanics multiplicity 没有引入 signature weight semantics。

## 自动测试覆盖

- D5B mechanics candidate order preserved；
- E1 unique truth source；
- 仅 `ValueError` 被当作 unbindable；
- only D5A-enabled signatures considered；
- disabled-but-bindable signature remains absent；
- signature iff nonempty mechanics support；
- zero mechanics removes signature；
- zero signatures returns empty tuple；
- synthetic HAREM gap filtered；
- activating Ensemble Cast restores mechanics/signature；
- group-only normalization remains bindable；
- empty pool removes reference support；
- empty pool leaves non-reference support unchanged；
- numeric E1 failure filters relevant mechanics；
- deterministic immutable output/order；
- candidate multiplicity has no weight semantics；
- full D5A/domain/resource prebinding；
- no RNG/sampling/concrete values/downstream dependencies。

## 验收结果

```text
E2A 专项测试
Ran 19 tests in 8.862s
OK

完整工程测试
Ran 336 tests in 18.350s
OK

compileall: PASS
git diff --check: PASS
skip / expectedFailure 搜索结果: 0
```

`git diff --check` 仅显示两个既有工作区文件的 LF/CRLF 转换提示，退出码为 0，未发现 whitespace error：

- `src/anime_pref/sampling/config.py`
- `tests/test_categorical_value_sampler.py`

## 请理论侧确认

1. Mechanics support 与 signature support 的过滤起点和 canonical order 是否正确。
2. E1 `ValueError` 作为 zero-capacity candidate、其他异常继续传播的边界是否正确。
3. Synthetic `0 mechanics / 0 signatures` 与激活后 `2 mechanics / 1 signature` 是否符合预期。
4. E2A 是否可以判定 PASS，并授权后续 probability-conditioning contract。

## 未实现

- domain-conditioned probabilities 或 RNG sampler；
- concrete values 或 SemanticSpec assembly；
- higher-level fallback/resampling；
- catalog satisfiability；
- dataset generation。
