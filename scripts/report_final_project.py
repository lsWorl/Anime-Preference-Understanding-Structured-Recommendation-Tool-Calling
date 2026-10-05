"""Verify retained predictions and write the single final engineering review."""
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from anime_pref.data.catalog import write_json
from anime_pref.data.query_builder import build_query, load_domain_rules
from anime_pref.schemas.preference_query import (
    SemanticSpec as S, SetConstraintSpec as C, RangeConstraintSpec as R)
from anime_pref.retrieval.executor import execute_query
from anime_pref.data.catalog import load_catalog
from anime_pref.evaluation.e0_baseline import (load_e0_inputs,evaluate_raw_prediction,
    build_e0_metrics_bundle,compute_e0_metrics)
from anime_pref.inference.final_parser import final_inference_config


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def jsonl(path):return tuple(json.loads(l) for l in path.read_text(encoding='utf-8').splitlines())


def audit_demo_fidelity(demos):
    """Compare the ten saved demos with explicit intended semantics, without repair.

    A valid executable Query does not prove faithful extraction. These expected
    specs are manual interpretations of the demo inputs; no NLP validator is
    claimed. Preserve both exact-schema agreement and the limited equivalence
    of a singleton ANY with a singleton ALL. Neither changes E0's frozen metric.
    """
    from copy import deepcopy
    from run_demo_cases import DEMO_CASES
    specs=(
        S(genres=C(all_of=("Mystery",)),year=R(min=2018),episodes=R(max=24)),
        S(genres=C(any_of=("Mystery","Sci-Fi")),tag_groups=C(none_of=("HAREM",))),
        S(reference_titles=("Steins;Gate",)),
        S(genres=C(all_of=("Mystery","Sci-Fi")),formats=("TV",)),
        S(tags=C(all_of=("Isekai",)),status=("FINISHED",)),
        S(genres=C(none_of=("Romance",))),
        S(genres=C(all_of=("Sci-Fi",)),year=R(max=2010)),
        S(episodes=R(max=12)),
        S(tags=C(all_of=("Time Loop",))),
        S(genres=C(any_of=("Mystery","Sci-Fi")),year=R(min=2015),
          episodes=R(max=24),tag_groups=C(none_of=("HAREM",))))
    rules=load_domain_rules(ROOT/'configs/domain_rules.v0.2.json')
    catalog=load_catalog(ROOT/'data/catalog/anilist_catalog_v0.1.jsonl')
    def singleton_form(query):
        result=deepcopy(query)
        if result is not None:
            for field in ('genres','tags'):
                clause=result['hard_constraints'][field]
                if len(clause['any_of'])==1:
                    clause['all_of']=sorted(set(clause['all_of']+clause['any_of']))
                    clause['any_of']=[]
        return result
    rows=[]
    for text,spec,case in zip(DEMO_CASES,specs,demos['cases'],strict=True):
        if case['user_text']!=text:raise ValueError('demo input changed')
        expected=build_query(spec,rules)
        allowed={row['id'] for row in execute_query(expected,catalog)}
        # Also verify returned facts satisfy the intended hard clauses, rather
        # than merely the possibly incomplete Query produced by the model.
        violations=[row['id'] for row in case['recommendations'] if row['id'] not in allowed]
        rows.append({'user_text':text,'expected_query':expected,
            'exact_query_match':case['parsed_query']==expected,
            'semantic_match_allowing_singleton_any_all':singleton_form(case['parsed_query'])==singleton_form(expected),
            'recommendation_ids_violating_intended_hard_constraints':violations})
    audit={'pipeline_success_count':sum(c['status']=='ok' for c in demos['cases']),
        'exact_query_match_count':sum(c['exact_query_match'] for c in rows),
        'semantic_match_count':sum(c['semantic_match_allowing_singleton_any_all'] for c in rows),
        'count':len(rows),'cases':rows,
        'scope':'Manual expected demo semantics; singleton ANY/ALL equivalence only. Does not alter E0 metrics or model outputs.'}
    write_json(ROOT/'artifacts/final/demo_fidelity_audit.json',audit)
    return audit


def build_comparison():
    """Re-evaluate every raw output; never trust metrics copied from a console."""
    rules=load_domain_rules(ROOT/'configs/domain_rules.v0.2.json');config=final_inference_config(ROOT)
    predictions={};metrics={};identities={};failures={};legacy={}
    for model in ('base','s1','final'):
        folder=ROOT/'artifacts/final/evaluation'/model
        predictions[model]={};identities[model]={};failures[model]={}
        for split in ('validation','test','challenge','legacy_challenge'):
            source=ROOT/f'data/final/{split}.v0.2.jsonl' if split!='legacy_challenge' else ROOT/'data/pilot/challenge.v0.1.jsonl'
            inputs=load_e0_inputs(source,'challenge' if split=='legacy_challenge' else split)
            rows=jsonl(folder/f'{split}_predictions.jsonl')
            identity=read(folder/f'{split}_identity.json');identities[model][split]=identity
            if identity['dataset_sha256']!=sha256(source.read_bytes()).hexdigest():raise ValueError('evaluation input identity drift')
            if identity['inference_config']!=asdict(config) or identity['rules_hash']!=rules.rules_hash:raise ValueError('inference contract drift')
            if identity.get('fresh_process_per_split') is not True or identity.get('effective_batch_size')!=1:
                raise ValueError('evaluation isolation/batch contract drift')
            if identity.get('release_unused_cuda_cache_between_calls') is not True:
                raise ValueError('evaluation memory policy drift')
            if len(rows)!=len(inputs):raise ValueError('prediction count mismatch')
            for record,row in zip(inputs,rows,strict=True):
                expected=json.loads(json.dumps(asdict(evaluate_raw_prediction(record,row['raw_model_output'],rules,config,config.revision))))
                if expected!=row:raise ValueError(f'saved prediction does not re-evaluate: {model}/{split}/{record.sample_id}')
            predictions[model][split]=rows
            failures[model][split]=[r for r in rows if not r['exact_match']]
        metrics[model]=build_e0_metrics_bundle(*(predictions[model][s] for s in ('validation','test','challenge')))
        legacy[model]=compute_e0_metrics(predictions[model]['legacy_challenge'])
    for split in ('validation','test','challenge','legacy_challenge'):
        ids=[identities[m][split] for m in ('base','s1','final')]
        for name in ('system_prompt_sha256','chat_template_sha256','dataset_sha256','rules_hash'):
            if len({r[name] for r in ids})!=1:raise ValueError(f'comparison identity mismatch: {name}')
    transitions={}
    for baseline in ('base','s1'):
        transitions[baseline]={}
        for split in ('test','challenge','legacy_challenge'):
            before=predictions[baseline][split];after=predictions['final'][split]
            transitions[baseline][split]={
                'fixed':[a['sample_id'] for b,a in zip(before,after) if not b['exact_match'] and a['exact_match']],
                'regressed':[a['sample_id'] for b,a in zip(before,after) if b['exact_match'] and not a['exact_match']],
                'still_failed':[a['sample_id'] for b,a in zip(before,after) if not b['exact_match'] and not a['exact_match']]}
    result={'protocol':'same v0.2 prompt / real domain / splits / BF16 base / greedy / batch one / fresh process per split for all three models',
        'historical_e0_s1_metrics_are_a_different_protocol':True,'metrics':metrics,
        'legacy_challenge':legacy,'failures':failures,'transitions':transitions,'identities':identities,
        'verification':'every saved raw output re-evaluated; all inputs and common inference identities match'}
    write_json(ROOT/'artifacts/final/comparison.json',result)
    return result


def file_tree():
    """List source, configs and evidence while omitting caches and virtualenv."""
    lines=[ROOT.name+'/']
    for parent,dirs,files in os.walk(ROOT):
        dirs[:]=sorted(d for d in dirs if d not in ('.git','.venv','__pycache__','review_bundle') and not d.endswith('.egg-info'))
        depth=len(Path(parent).relative_to(ROOT).parts)
        if depth:lines.append('  '*depth+Path(parent).name+'/')
        for name in sorted(files):
            path=Path(parent)/name
            lines.append('  '*(depth+1)+name)
    return '\n'.join(lines)


def generate_review(comparison):
    audit=read(ROOT/'data/final/audit.json');catalog=read(ROOT/'data/catalog/manifest.json')
    taxonomy=read(ROOT/'data/domain/taxonomy_v0.2/manifest.json')
    subset=read(ROOT/'data/domain/subset_v0.2/manifest.json')
    identity=read(ROOT/'artifacts/final/run_identity.json');state=read(ROOT/'artifacts/final/trainer/trainer_state.json')
    adapter=read(ROOT/'artifacts/final/adapter_manifest.json');demos=read(ROOT/'artifacts/final/demo_results.json')
    demo_audit=audit_demo_fidelity(demos)
    rows=['# Final Project Engineering Review Bundle','',
        '## 状态与证据边界','',
        '核心工程链已运行。数据和模型指标以本报告及 comparison.json 的实际记录为准；模型会产生错误，应用通过严格 validation 拒绝非法 Query，不静默修复。',
        '没有运行额外的 test-informed 调参训练。Final 从冻结 base 新建 LoRA，未从 S1 adapter 继续训练。',
        '第一次连续多 split 的 batch=2 运行中，Base challenge 出现重复乱码；同一输入新进程复核恢复正常，因此旧批量结果保留为诊断材料，不纳入最终比较。三模型最终都用 batch=1、每 split 独立进程重新生成，未筛选更好的单条答案。异常根因未确定。',
        '每次生成返回 CPU 文本后统一释放未使用 CUDA 缓存，并在 runtime identity 记录该政策；不改变权重、prompt 或解码参数。',
        '', '## 系统架构','', '```text',
        'User → Qwen3-4B + saved LoRA → raw JSON → strict parser → schema/domain validator',
        '     → local AniList catalog filter → deterministic ranker → CLI recommendations','```','',
        '## 数据与来源','',f'- Real catalog: {catalog["record_count"]} anime; SHA-256 `{catalog["catalog_sha256"]}`.',
        f'- Taxonomy: real AniList snapshot; subset {audit["approved_tag_count"]} tags, reference pool {audit["reference_pool_count"]} titles.',
        f'- Catalog fetched at UTC: `{catalog["fetched_at_utc"]}`; full-site crawl: false.',
        '### Snapshot / executable identity','',
        '```json',json.dumps({'taxonomy_manifest':taxonomy,'subset_manifest':subset,
            'rules_hash':audit['rules_hash'],'dataset_version':audit['dataset_version']},ensure_ascii=False,indent=2),'```','',
        '- Tag decisions are explicitly selected by the engineering assistant under user delegation; not represented as independent human audit.',
        f'- Dataset: {audit["count"]}; splits {audit["splits"]}; challenge {audit["challenge_count"]}; {audit["controlled_styles"]} controlled styles.',
        '- Cross-split exact text/pair overlap: 0. Complexity 1–5 plus reference-only; multi-value format/status OR covered.',
        '- Taxonomy/subset/rules/dataset/model revisions have separate identities. Synthetic fixtures remain only in historical tests/pilot.',
        '', '## 最终 QLoRA 配置','', '```json',json.dumps(identity['training_config'],ensure_ascii=False,indent=2),'```','',
        '### 真实 token / labels 证据','', '```json',json.dumps(identity['token_length_summary'],indent=2),'```','',
        '```json',json.dumps(identity['masking_evidence'],ensure_ascii=False,indent=2),'```','',
        f'- Saved best adapter: `{adapter["adapter_sha256"]}`; best checkpoint `{adapter["best_checkpoint"]}`.',
        '- All evaluation model variants are loaded in separate processes after training, with BF16 base and saved adapter; no merge.',
        '', '### Train/validation loss','', '| Step | Epoch | Train loss | Eval loss | LR |', '|---:|---:|---:|---:|---:|']
    for log in state['log_history']:
        if 'loss' in log or 'eval_loss' in log:
            rows.append(f"| {log.get('step')} | {log.get('epoch')} | {log.get('loss','')} | {log.get('eval_loss','')} | {log.get('learning_rate','')} |")
    rows+=['','## Base vs S1 vs Final：同一 v0.2 协议','',
        '这些是重新在同一 enlarged-vocabulary prompt 和新数据集上生成的指标，不能直接当作历史 E0/S1 v0.1 的纵向提升。',
        '', '| Split | Model | N | JSON | Schema | Domain | Exact | Hard P | Hard R | Hard F1 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for split in ('validation','test','challenge'):
        for model in ('base','s1','final'):
            m=comparison['metrics'][model][split]['overall']
            keys=('json_parse_rate','schema_valid_rate','domain_valid_rate','exact_match_rate','hard_constraint_precision','hard_constraint_recall','hard_constraint_f1')
            rows.append(f'| {split} | {model} | {m["total"]} | '+' | '.join(f'{100*m[k]:.1f}%' for k in keys)+' |')
    rows+=['',
        'Exact 与 Hard P/R/F1 沿用冻结 evaluator：集合排序不影响结果，但不折叠 singleton ANY/ALL。部分 WRONG_OPERATOR 因而是表达合同差异，即使执行器过滤结果相同；完整失败 Query 保留供复盘。这条说明不改变任何指标。',
        '', '### Field accuracy (Final)','', '| Split | Field | Accuracy |','|---|---|---:|']
    for split in ('test','challenge'):
        for field,value in comparison['metrics']['final'][split]['overall']['field_accuracy'].items():
            rows.append(f'| {split} | {field} | {value:.1%} |')
    rows+=['','### 剩余失败与回归','',
        '所有模型在 test/challenge 的完整失败 Query、raw output 和 error taxonomy 保存在 `artifacts/final/comparison.json.failures`。',
        '下面保留 Final 的逐条失败；invalid-domain 时冻结 evaluator 采用 fail-closed metrics，不额外给部分分。','']
    for split in ('test','challenge','legacy_challenge'):
        for failure in comparison['failures']['final'][split]:
            rows+=['### '+split+' / '+failure['sample_id'],'',failure['user_text'],'',
                   'Gold:','```json',json.dumps(failure['gold_query'],ensure_ascii=False),'```',
                   'Raw model output:','```text',failure['raw_model_output'],'```',
                   'Errors: '+', '.join(failure['error_labels']),'']
    rows+=['','### 历史 challenge_009 probe（新公共 prompt）','']
    for model in ('base','s1','final'):
        path=ROOT/f'artifacts/final/evaluation/{model}/legacy_challenge_predictions.jsonl'
        row=next(r for r in jsonl(path) if r['sample_id']=='challenge_009')
        rows += [f'- {model}: exact={row["exact_match"]}; errors={row["error_labels"]}.','```text',row['raw_model_output'],'```']
    rows+=['','## 十个真实端到端 demos','',
        '下面的 Query 来自已保存 Final adapter 的真实 GPU inference；推荐来自 1544 条本地 AniList snapshot。',
        f'Pipeline success: {demo_audit["pipeline_success_count"]}/10; intended-query exact: {demo_audit["exact_query_match_count"]}/10; semantic match allowing singleton ANY/ALL equivalence: {demo_audit["semantic_match_count"]}/10.',
        'Demo 1 漏抽 Mystery；Demo 7 漏抽 Sci-Fi。结构/domain validation 无法检测这种漏抽，不能将 status=ok 描述为语义全对。Demo 9 使用 singleton ANY 而预期为 ALL，过滤语义相同但 strict Exact 不同。',
        '完整人工预期、逐条 Query 对照和推荐违反预期约束的 ID 保存在 `artifacts/final/demo_fidelity_audit.json`。','']
    for i,case in enumerate(demos['cases'],1):
        fidelity=demo_audit['cases'][i-1]
        rows += [f'### Demo {i}', '',case['user_text'], '',f'Status: {case["status"]}',
                 f'Intended semantics matched: {fidelity["semantic_match_allowing_singleton_any_all"]}; recommendation IDs violating intended hard constraints: {fidelity["recommendation_ids_violating_intended_hard_constraints"]}.',
                 '```json',json.dumps(case['parsed_query'],ensure_ascii=False,indent=2),'```','',
                 '| Title | Year | Format | Episodes | Score |','|---|---:|---|---:|---:|']
        for r in case['recommendations']:
            rows.append(f'| {r["title"].replace("|","/")} | {r["year"]} | {r["format"]} | {r["episodes"]} | {r["score"]:.4f} |')
    rows += ['','## 测试与可复现命令','',
        '完整最新测试输出见 `artifacts/final/tests.txt`；语法编译与 diff whitespace 检查见 `artifacts/final/checks.txt`。',
        '落盘 provenance 审核见 `artifacts/final/provenance_audit.json`：train/validation/test 的完整 DatasetRecord 与既有 validator 重新核对；challenge 保持原 E0 challenge shape，以作者显式 SemanticSpec 重建 Gold 比较。','',
        '```text',(ROOT/'artifacts/final/tests.txt').read_text(encoding='utf-8')[-1600:].strip(),
        (ROOT/'artifacts/final/checks.txt').read_text(encoding='utf-8').strip(),'```','',
        '```powershell', r'.\.venv\Scripts\python.exe scripts/fetch_catalog.py',
        r'.\.venv\Scripts\python.exe scripts/build_final_data.py',
        r'.\.venv\Scripts\python.exe scripts/verify_final_data.py',
        r'.\.venv\Scripts\python.exe scripts/prepare_final_config.py',
        r'.\.venv\Scripts\python.exe scripts/train_final.py --train',
        r'.\.venv\Scripts\python.exe scripts/run_final_evaluation.py --model base',
        r'.\.venv\Scripts\python.exe scripts/run_final_evaluation.py --model s1',
        r'.\.venv\Scripts\python.exe scripts/run_final_evaluation.py --model final',
        r'.\.venv\Scripts\python.exe scripts/run_demo_cases.py',
        r'.\.venv\Scripts\python.exe scripts/recommend.py "悬疑或者科幻都可以，不要后宫。"',
        r'.\.venv\Scripts\python.exe scripts/recommend.py --interactive','```','',
        '训练与 evaluation 拒绝覆盖已有结果。以上训练命令用于新实验目录；当前已完成环境直接运行 recommend 即可。',
        '', '## 调用链 / 文档','',
        '- `README.md`: installation, training, evaluation, CLI, limitations.',
        '- `docs/project_summary.md`: project explanation, resume bullets, interview questions.',
        '- `docs/code_walkthrough.md`: source navigation in data→training→inference order.',
        '', '## 已知局限与 optional items','',
        '- Bounded catalog is neither exhaustive nor continuously updated; 0 matches is returned without relaxing constraints.',
        '- Tag subset has delegated engineering review, not independent expert/user audit; flags exclude adult/spoiler concepts.',
        '- Controlled text is easier than unconstrained user language; challenge failures are retained, not hidden.',
        '- Reference lookup is exact after Unicode/case normalization; ambiguous/unmatched references only warn.',
        '- Reference source itself may remain among recommendations; reference is ranking-only.',
        '- Tag rank thresholds / simple scoring are explicit engineering policies, not learned recommendation quality.',
        '- No LLM paraphrase, trainable ranker, web frontend, FastAPI, vector DB, adapter merge or distributed training.',
        '- No claim of production robustness or causal improvement independent of the new data/prompt protocol.',
        '- Frozen training prompt still lists Hentai from the legacy genre line; active v0.2 DomainRules rejects it. This discrepancy is retained transparently, not silently edited after evaluation.',
        '', '## 最终文件树','', '```text',file_tree(),'```','']
    bundle=ROOT/'review_bundle/final_project';bundle.mkdir(parents=True,exist_ok=True)
    (bundle/'REVIEW.md').write_text('\n'.join(rows),encoding='utf-8')
    (ROOT/'docs/final_metrics.md').write_text('\n'.join(rows[rows.index('## Base vs S1 vs Final：同一 v0.2 协议'):rows.index('## 十个真实端到端 demos')]),encoding='utf-8')
    # Put the headline comparison in README as well as in the full evidence.
    # Idempotent markers keep re-generating the report from duplicating content.
    headline=['<!-- FINAL_METRICS_START -->','## 本轮真实结果（同一 v0.2 协议）','',
        '| Metric | Base | S1 | Final |','|---|---:|---:|---:|']
    for split in ('test','challenge'):
        for label,key in (('Exact','exact_match_rate'),('Hard F1','hard_constraint_f1'),('Domain','domain_valid_rate')):
            headline.append(f'| {split} {label} | '+' | '.join(f'{comparison["metrics"][m][split]["overall"][key]:.1%}' for m in ('base','s1','final'))+' |')
    headline+=['','完整 JSON/schema validity、field accuracy、所有失败与协议差异见 [最终指标](docs/final_metrics.md)。','<!-- FINAL_METRICS_END -->']
    readme=ROOT/'README.md';text=readme.read_text(encoding='utf-8')
    start=text.find('<!-- FINAL_METRICS_START -->');end=text.find('<!-- FINAL_METRICS_END -->')
    if start!=-1 and end!=-1:text=text[:start]+text[end+len('<!-- FINAL_METRICS_END -->'):]
    readme.write_text(text.rstrip()+'\n\n'+'\n'.join(headline)+'\n',encoding='utf-8')
    write_json(bundle/'completion.json',{'demo_success_count':sum(c['status']=='ok' for c in demos['cases']),
        'demo_count':len(demos['cases']),'demo_exact_query_match_count':demo_audit['exact_query_match_count'],
        'demo_semantic_match_count':demo_audit['semantic_match_count'],
        'adapter_manifest':adapter,'dataset_audit':audit})
    # Portable review bundle contains evidence and source, never large model weights.
    archive=ROOT/'review_bundle/final_project_review.zip'
    included=[]
    for directory in ('src','scripts','configs','tests','docs','data/final','data/domain','data/catalog','data/pilot','artifacts/e0','artifacts/s1/evaluation','artifacts/final/evaluation_bulk_interrupted'):
        for p in (ROOT/directory).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.bin','.pt','.safetensors'):
                included.append(p)
    included += [ROOT/'.gitignore',ROOT/'README.md',ROOT/'pyproject.toml',ROOT/'requirements-s1.txt',ROOT/'requirements-e0.txt']
    included += list((ROOT/'artifacts/final').glob('*.json'))+list((ROOT/'artifacts/final').glob('*.txt'))
    included += list((ROOT/'artifacts/final/evaluation').rglob('*.json'))+list((ROOT/'artifacts/final/evaluation').rglob('*.jsonl'))
    included += [ROOT/'artifacts/final/trainer/trainer_state.json',ROOT/'artifacts/final/adapter/adapter_config.json',bundle/'REVIEW.md',bundle/'completion.json']
    included += [ROOT/'artifacts/s1/run_identity.json',ROOT/'artifacts/s1/comparison.json']
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(set(included)):z.write(path,path.relative_to(ROOT))
    print('Review:',bundle/'REVIEW.md','portable:',archive,flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    generate_review(build_comparison())
