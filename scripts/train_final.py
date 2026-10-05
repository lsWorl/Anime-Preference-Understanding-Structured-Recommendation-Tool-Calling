"""Run the separate final v0.2 training experiment; S1 artifacts stay frozen."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from anime_pref.training.final_training import train_final
if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--train",action="store_true")
    args=parser.parse_args();train_final(ROOT,args.train)
