"""Build the real domain and 1500-row controlled dataset v0.2."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from anime_pref.data.final_dataset import generate_final_dataset
if __name__ == "__main__":
    print(generate_final_dataset(ROOT))
