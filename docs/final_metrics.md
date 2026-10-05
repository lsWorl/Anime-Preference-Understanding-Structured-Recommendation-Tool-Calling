## Base vs S1 vs Final：同一 v0.2 协议

这些是重新在同一 enlarged-vocabulary prompt 和新数据集上生成的指标，不能直接当作历史 E0/S1 v0.1 的纵向提升。

| Split | Model | N | JSON | Schema | Domain | Exact | Hard P | Hard R | Hard F1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| validation | base | 150 | 94.0% | 94.0% | 87.3% | 51.3% | 86.2% | 64.2% | 73.6% |
| validation | s1 | 150 | 100.0% | 100.0% | 94.7% | 82.0% | 96.8% | 88.7% | 92.6% |
| validation | final | 150 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| test | base | 150 | 90.7% | 90.0% | 88.0% | 54.0% | 90.0% | 70.0% | 78.8% |
| test | s1 | 150 | 100.0% | 100.0% | 98.7% | 86.0% | 97.9% | 93.2% | 95.5% |
| test | final | 150 | 100.0% | 100.0% | 99.3% | 99.3% | 100.0% | 99.5% | 99.7% |
| challenge | base | 40 | 85.0% | 85.0% | 82.5% | 42.5% | 86.0% | 63.6% | 73.1% |
| challenge | s1 | 40 | 100.0% | 100.0% | 92.5% | 65.0% | 90.5% | 74.0% | 81.4% |
| challenge | final | 40 | 100.0% | 100.0% | 97.5% | 67.5% | 89.0% | 84.4% | 86.7% |

Exact 与 Hard P/R/F1 沿用冻结 evaluator：集合排序不影响结果，但不折叠 singleton ANY/ALL。部分 WRONG_OPERATOR 因而是表达合同差异，即使执行器过滤结果相同；完整失败 Query 保留供复盘。这条说明不改变任何指标。

### Field accuracy (Final)

| Split | Field | Accuracy |
|---|---|---:|
| test | genres | 99.3% |
| test | tags | 99.3% |
| test | year | 99.3% |
| test | episodes | 99.3% |
| test | formats | 99.3% |
| test | status | 99.3% |
| test | reference_titles | 99.3% |
| test | soft_preferences | 99.3% |
| test | unresolved_preferences | 99.3% |
| challenge | genres | 87.5% |
| challenge | tags | 82.5% |
| challenge | year | 97.5% |
| challenge | episodes | 97.5% |
| challenge | formats | 97.5% |
| challenge | status | 97.5% |
| challenge | reference_titles | 97.5% |
| challenge | soft_preferences | 97.5% |
| challenge | unresolved_preferences | 92.5% |

### 剩余失败与回归

所有模型在 test/challenge 的完整失败 Query、raw output 和 error taxonomy 保存在 `artifacts/final/comparison.json.failures`。
下面保留 Final 的逐条失败；invalid-domain 时冻结 evaluator 采用 fail-closed metrics，不额外给部分分。

### test / sample_6f6da97b248f3241eb1284ae5a90f21343877a8dd876d61db23cb2db94890831

推荐一些满足这些条件的作品：标签为教育或足球中的任一种；状态为正在连载；找类似《JUJUTSU KAISEN》的作品。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["RELEASING"], "tags": {"all_of": [], "any_of": ["Educational", "Football"], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": ["JUJUTSU KAISEN"], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Education","Football"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["RELEASING"]},"reference_titles":["JUJUTSU KAISEN"],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: DOMAIN_ERROR

### challenge / final_challenge_001

只要悬疑题材，最多二十四集。

Gold:
```json
{"hard_constraints": {"episodes": {"max": 24, "min": null}, "formats": [], "genres": {"all_of": ["Mystery"], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Mystery"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":24},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_005

2013年及以前的科幻作品。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": ["Sci-Fi"], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": 2013, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":2013},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT

### challenge / final_challenge_008

至少十五集，可以长一些。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": 15}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": ["可以长一些"]}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":15,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: 

### challenge / final_challenge_014

想看异世界题材的已完结作品。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": ["FINISHED"], "tags": {"all_of": ["Isekai"], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":["Isekai"],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":["FINISHED"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: DOMAIN_ERROR

### challenge / final_challenge_016

包含时间循环标签的动画。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Time Loop"], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Time Loop"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_027

2022年及以后，至少六集，喜剧TV动画且已经完结。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": 6}, "formats": ["TV"], "genres": {"all_of": ["Comedy"], "any_of": [], "none_of": []}, "status": ["FINISHED"], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": 2022}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Comedy"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":2022,"max":null},"episodes":{"min":6,"max":null},"formats":["TV"],"status":["FINISHED"]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_029

战斗不作要求，只要机甲题材。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": ["Mecha"], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Mecha"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_030

有哲学标签，至少十集。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": 10}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Philosophy"], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Philosophy"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":10,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_031

找群像TV动画，不要后宫。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": ["TV"], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Ensemble Cast"], "any_of": [], "none_of": ["Female Harem", "Male Harem", "Mixed Gender Harem"]}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":["TV"],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, WRONG_VALUE, NORMALIZATION_ERROR

### challenge / final_challenge_032

我想看死亡游戏标签的作品。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Death Game"], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Death Game"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_038

给我治愈系标签的动画，年份不晚于2019年。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Iyashikei"], "any_of": [], "none_of": []}, "year": {"max": 2019, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Iyashikei"],"none_of":[]},"year":{"min":null,"max":2019},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_039

推荐带露营标签的作品，至少两集。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": 2}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": ["Camping"], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": []}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":["Camping"],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":2,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: MISSING_CONSTRAINT, HALLUCINATED_CONSTRAINT, WRONG_OPERATOR, WRONG_VALUE

### challenge / final_challenge_040

想找节奏紧凑的作品。

Gold:
```json
{"hard_constraints": {"episodes": {"max": null, "min": null}, "formats": [], "genres": {"all_of": [], "any_of": [], "none_of": []}, "status": [], "tags": {"all_of": [], "any_of": [], "none_of": []}, "year": {"max": null, "min": null}}, "reference_titles": [], "soft_preferences": [], "unresolved_preferences": ["节奏紧凑"]}
```
Raw model output:
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":[]},"year":{"min":null,"max":null},"episodes":{"min":null,"max":null},"formats":[],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
Errors: 


### 历史 challenge_009 probe（新公共 prompt）

- base: exact=False; errors=['MISSING_CONSTRAINT'].
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":[],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":2010,"max":null},"episodes":{"min":null,"max":24},"formats":["TV"],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
- s1: exact=True; errors=[].
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Mystery","Sci-Fi"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":2010,"max":null},"episodes":{"min":null,"max":24},"formats":["TV"],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
- final: exact=True; errors=[].
```text
{"hard_constraints":{"genres":{"all_of":[],"any_of":["Mystery","Sci-Fi"],"none_of":[]},"tags":{"all_of":[],"any_of":[],"none_of":["Female Harem","Male Harem","Mixed Gender Harem"]},"year":{"min":2010,"max":null},"episodes":{"min":null,"max":24},"formats":["TV"],"status":[]},"reference_titles":[],"soft_preferences":[],"unresolved_preferences":[]}
```
