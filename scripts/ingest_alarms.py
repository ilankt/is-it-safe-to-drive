from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.lib.data.ingest import run_ingest
from src.lib.data.normalize import CONFLICT_START_LOCAL


def _run_git(args: list[str], cwd: Path) -> str:
    command = ["git", *args]
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def sync_source_repo(source_dir: Path, repo_url: str) -> str:
    if not source_dir.exists():
        _run_git(["clone", "--depth", "1", repo_url, str(source_dir)], cwd=ROOT)
    if not (source_dir / ".git").exists():
        raise RuntimeError(f"{source_dir} exists but is not a git repository.")

    _run_git(["fetch", "origin"], cwd=source_dir)
    _run_git(["pull", "--ff-only"], cwd=source_dir)
    return _run_git(["rev-parse", "HEAD"], cwd=source_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest and normalize alarm data for latest conflict window."
    )
    parser.add_argument(
        "--source-dir",
        default=".tmp-alarms",
        help="Local git checkout path for source repository",
    )
    parser.add_argument(
        "--source-repo-url",
        default="https://github.com/yuval-harpaz/alarms.git",
        help="Git URL for source repository",
    )
    parser.add_argument(
        "--no-sync-source",
        action="store_true",
        help="Skip git fetch/pull before ingest",
    )
    parser.add_argument(
        "--raw-csv",
        default="",
        help="Optional explicit path to raw alarms.csv (defaults to <source-dir>/data/alarms.csv)",
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Directory for normalized outputs",
    )
    parser.add_argument(
        "--source-repo",
        default="yuval-harpaz/alarms",
        help="Source repository identifier",
    )
    parser.add_argument(
        "--source-commit",
        default="",
        help="Optional source repository commit hash override",
    )
    parser.add_argument(
        "--conflict-start",
        default=CONFLICT_START_LOCAL.strftime("%Y-%m-%d %H:%M:%S"),
        help="Local start datetime for conflict filter (YYYY-MM-DD HH:MM:SS)",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    source_commit = args.source_commit.strip()
    if not args.no_sync_source:
        source_commit = sync_source_repo(source_dir=source_dir, repo_url=args.source_repo_url)
    if not source_commit:
        try:
            source_commit = _run_git(["rev-parse", "HEAD"], cwd=source_dir)
        except Exception:
            source_commit = "unknown"

    raw_csv = Path(args.raw_csv) if args.raw_csv else (source_dir / "data" / "alarms.csv")
    if not raw_csv.exists():
        raise FileNotFoundError(f"Raw CSV not found: {raw_csv}")

    conflict_start = datetime.strptime(args.conflict_start, "%Y-%m-%d %H:%M:%S")
    result = run_ingest(
        raw_csv_path=raw_csv,
        output_dir=Path(args.output_dir),
        source_repo=args.source_repo,
        source_commit=source_commit,
        conflict_start=conflict_start,
        coord_csv_path=source_dir / "data" / "coord.csv",
    )

    print("INGEST_COMPLETE")
    print(raw_csv)
    print(result.normalized_events_path)
    print(result.city_lookup_path)
    print(result.aggregates_path)
    print(result.sqlite_path)
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
