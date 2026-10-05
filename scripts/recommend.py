"""CLI: user text -> final adapter -> validated query -> offline recommendations."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from anime_pref.inference.final_parser import make_service

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('text',nargs='?');parser.add_argument('--interactive',action='store_true')
    parser.add_argument('--top-k',type=int,default=10);parser.add_argument('--model',choices=('base','s1','final'),default='final')
    args=parser.parse_args()
    if not args.text and not args.interactive: parser.error('supply user text or --interactive')
    if not 1<=args.top_k<=100: parser.error('top-k must be 1..100')
    service=make_service(ROOT,args.model)
    def show(text):
        print(json.dumps(service.recommend_anime(text,args.top_k),ensure_ascii=False,indent=2))
    if args.text: show(args.text)
    if args.interactive:
        while True:
            try: text=input('\n动画偏好（exit退出）> ').strip()
            except (EOFError,KeyboardInterrupt): break
            if text.lower() in ('exit','quit'): break
            if text: show(text)

if __name__=='__main__':main()
