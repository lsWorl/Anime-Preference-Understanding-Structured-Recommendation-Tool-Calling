"""Ten real model-to-catalog demos, with raw JSON retained as evidence."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from anime_pref.inference.final_parser import make_service
from anime_pref.data.catalog import write_json

DEMO_CASES=(
 '想看2018年及以后的悬疑动画，最多24集。',
 '悬疑或者科幻都可以，不要后宫。',
 '想找类似《Steins;Gate》的作品。',
 '想看同时有科幻和悬疑题材的TV动画。',
 '想看已经完结、有异世界标签的动画。',
 '不要恋爱题材。',
 '2010年及以前的科幻作品。',
 '最多12集的作品。',
 '想找带时间循环标签的作品。',
 '2015年及以后、最多24集、悬疑或者科幻、不要后宫。')

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    service=make_service(ROOT)
    results=[]
    for text in DEMO_CASES:
        result=service.recommend_anime(text,5);results.append(result)
        print(text,result['status'],'recommendations=',len(result['recommendations']),flush=True)
    write_json(ROOT/'artifacts/final/demo_results.json',{'cases':results,'model_identity':service.parser.runtime_identity})
    print('Demos with recommendations:',sum(r['status']=='ok' for r in results),'/10',flush=True)

if __name__=='__main__':main()
