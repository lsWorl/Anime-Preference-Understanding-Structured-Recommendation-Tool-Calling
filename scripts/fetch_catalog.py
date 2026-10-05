"""Fetch real taxonomy and a bounded catalog; resume from saved raw pages."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from anime_pref.data.catalog import fetch_catalog_snapshot, graphql
from anime_pref.data.taxonomy_client import TAXONOMY_QUERY
from anime_pref.data.taxonomy_snapshot import write_taxonomy_snapshot_bundle

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=2.2)
    args = parser.parse_args()
    taxonomy_dir = ROOT / "data/domain/taxonomy_v0.2"
    if not (taxonomy_dir / "manifest.json").exists():
        write_taxonomy_snapshot_bundle(graphql(TAXONOMY_QUERY), output_dir=taxonomy_dir,
            fetched_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    print(fetch_catalog_snapshot(ROOT / "data/catalog", args.delay))

if __name__ == "__main__":
    main()
