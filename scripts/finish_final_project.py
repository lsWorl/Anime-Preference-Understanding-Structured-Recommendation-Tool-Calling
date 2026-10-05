"""Sequential post-training acceptance: no re-training or hyperparameter search."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def run(script,*args):
    print('RUN',script,*args,flush=True)
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/script),*args],cwd=ROOT,check=True)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--wait-for-training',action='store_true')
    args=parser.parse_args();deadline=time.monotonic()+7200
    manifest=ROOT/'artifacts/final/adapter_manifest.json'
    while not manifest.exists():
        if not args.wait_for_training:raise RuntimeError('train_final.py must finish first')
        if time.monotonic()>deadline:raise RuntimeError('training wait timed out; inspect saved logs')
        time.sleep(15)
    # Every invocation is a new OS process: no trained in-memory model can leak
    # into smoke, demos or evaluation. All raw outputs stay on disk.
    run('check_final_adapter.py')
    run('run_demo_cases.py')
    run('recommend.py','悬疑或者科幻都可以，不要后宫。','--top-k','3')
    for model in ('final','base','s1'):
        out=ROOT/'artifacts/final/evaluation'/model
        if not all((out/f'{s}_predictions.jsonl').exists() for s in ('validation','test','challenge','legacy_challenge')):
            run('run_final_evaluation.py','--model',model)
    run('verify_final_data.py')
    with (ROOT/'artifacts/final/tests.txt').open('w',encoding='utf-8') as log:
        subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests'],cwd=ROOT,
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    subprocess.run([sys.executable,'-m','compileall','-q','src','scripts','tests'],cwd=ROOT,check=True)
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    (ROOT/'artifacts/final/checks.txt').write_text('compileall: PASS\ngit diff --check: PASS\n',encoding='utf-8')
    run('report_final_project.py')
    print('FINAL ACCEPTANCE PIPELINE FINISHED; inspect review status and real metrics.',flush=True)

if __name__=='__main__':main()
