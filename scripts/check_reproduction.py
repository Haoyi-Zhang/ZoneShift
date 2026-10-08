#!/usr/bin/env python3
"""Compare scientific outputs while excluding execution-cost metadata only.

Scheduled timestamps, verdicts, classifications, trace ordering, source hashes and
all test inputs remain in the digest. The comparison therefore does not hide a
scheduler-output difference. Exclusions affect the canonical comparison only;
the source records retain their timings and runner metadata.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys

IGNORED_KEYS = {
    "elapsed_ns",
    "startup_ns",
    "after_elapsed_ns",
    "elapsed_seconds",
    "median_us",
    "p95_us",
    "boundary_median_us",
    "total_api_seconds",
    "utc_execution",
    "study_wall_seconds",
    "before_median_us",
    "after_median_us",
    "before_total_ms",
    "after_total_ms",
    "wall_seconds",
}

FILES = [
    "runs.jsonl",
    "historical.json",
    "upstream-inputs.json",
    "tzdb-update.json",
    "controls.json",
    "intervention.json",
    "mutations.json",
    "oracle-validation.json",
    "design.json",
    "benchmark-summary.json",
    "released-sentry.json",
    "direct-fold-replay.json",
    "analysis.json",
    "version-data-matrix.json",
    "policy-matrix.json",
    "mutation-study.json",
    "comparator-analysis.json",
    "integration-metrics.json",
    "current-release-scope.json",
    "current-release-holdout.json",
    "current-tzdb-holdout.json",
    "decision-records.jsonl",
    "regression-pack.json",
    "decision-record-summary.json",
    "extended-analysis.json",
    "rule-release-series.json",
    "release-series-decisions.jsonl",
    "release-series-validation.json",
    "signature-budget.json",
    "minimized-witnesses.json",
    "release-analysis.json",
    "policy-frontiers.json",
    "upgrade-sufficiency.json",
    "policy-attribution-summary.json",
]


def strip_runtime(value):
    if isinstance(value, dict):
        return {
            key: strip_runtime(item)
            for key, item in value.items()
            if key not in IGNORED_KEYS
        }
    if isinstance(value, list):
        return [strip_runtime(item) for item in value]
    return value


def load(path: Path):
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text().splitlines() if line]
    return json.loads(path.read_text())


def digest(root: Path) -> tuple[str, list[str]]:
    missing = [name for name in FILES if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing result files under {root}: {missing}")

    hasher = hashlib.sha256()
    for name in FILES:
        canonical = json.dumps(
            strip_runtime(load(root / name)),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(canonical)
        hasher.update(b"\0")
    return hasher.hexdigest(), FILES


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_reproduction.py ORIGINAL_RESULTS REPLAY_RESULTS")
    original, replay = map(Path, sys.argv[1:])
    first, files = digest(original)
    second, _ = digest(replay)
    result = {
        "original": first,
        "replay": second,
        "same_scientific_output": first == second,
        "compared_files": files,
        "ignored_keys": sorted(IGNORED_KEYS),
        "scheduled_timestamps_ignored": False,
    }
    print(json.dumps(result, indent=2))
    return 0 if first == second else 1


if __name__ == "__main__":
    raise SystemExit(main())
