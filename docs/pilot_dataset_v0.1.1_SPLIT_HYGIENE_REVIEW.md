# F1.1 Pilot Split Hygiene Review Bundle

## 阶段状态

F1 generation pipeline、semantic realization 和 record construction 没有修改。本轮只处理理论审查要求的 split-level duplicate/leakage hygiene。

## 修改文件

- `configs/pilot_pattern_manifest.v0.1.json`
- `src/anime_pref/data/pilot_dataset.py`
- `scripts/generate_pilot_dataset.py`
- `tests/test_pilot_dataset.py`
- `data/pilot/*.jsonl`
- `docs/pilot_dataset_audit_v0.1.md`
- `docs/pilot_dataset_v0.1.1_SPLIT_HYGIENE_IMPLEMENTATION.md`

## 最终 split hygiene

| Split pair | Exact user text | User text + Gold | SemanticSpec |
|---|---:|---:|---:|
| train↔validation | 0 | 0 | 2 |
| train↔test | 0 | 0 | 0 |
| validation↔test | 0 | 0 | 0 |

| Split | Exact user text duplicate excess | User text + Gold duplicate excess | SemanticSpec duplicate excess |
|---|---:|---:|---:|
| train | 66 | 66 | 66 |
| validation | 0 | 0 | 0 |
| test | 0 | 0 | 0 |

全数据层面的 duplicate counts 为：sample ID 0、exact user text 66、exact pair 66、SemanticSpec 68。额外两个 SemanticSpec duplicate 来自允许的 train↔validation semantic overlap。

## 合同实现

- exact user text 和 exact `(user_text, Gold)` 跨 split overlap 会让 split validator 失败；
- validation/test 内 exact text 和 exact pair duplicate 会失败；
- train 内重复允许保留并统计；
- SemanticSpec overlap 允许并报告；
- template ID 隔离、sample ID 不相交及 split union 原检查继续保留；
- evaluation 重复通过替换 manifest 显式 seed 清除，没有修改生成架构。

## 验证结果

最终验证结果：

```text
Generator: 240 records; train=180; validation=30; test=30; challenge=12
F1 targeted tests: 25 passed in 1.992s
Full project tests: 384 passed in 26.753s
compileall: PASS
git diff --check: PASS（仅报告两个既有文件的 LF/CRLF 提示）
skip / expectedFailure audit: PASS（无匹配）
```

## 请理论分支确认

1. 三组 split 的 exact user text 与 exact pair overlap 均为 0，是否满足 leakage hygiene？
2. validation/test 内部 exact pair duplicate 均为 0，train 内 66 条 duplicate excess 继续保留并报告，是否符合 pilot policy？
3. train↔validation 的 2 个 SemanticSpec overlap 是否按冻结结论允许？
4. F1 train/validation/test split 是否可以 PASS/FROZEN？
5. 若 F1.1 通过，是否正式授权进入 E0 baseline evaluation？

在理论侧授权前，工程侧不开始 E0。
