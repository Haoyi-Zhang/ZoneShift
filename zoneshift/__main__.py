"""Offline CLI for single-trace and two-coordinate civil-time qualification."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .adapters import ROOT
from .attribution import classify_upgrade_square
from .contracts import Contract, qualify
from .execution import load_zone, run_trace
from .tzif import TZif

STATUS_EXIT = {"PASS": 0, "VIOLATION": 1, "UNDERSPECIFIED": 2}
COMMON_FIELDS = {"mode", "zone", "start", "start_fold", "count", "contract"}
SINGLE_FIELDS = COMMON_FIELDS | {"implementation", "tzdb"}
UPGRADE_FIELDS = COMMON_FIELDS | {
    "old_implementation",
    "new_implementation",
    "old_tzdb",
    "new_tzdb",
}


def _contract(raw: dict[str, Any]) -> Contract:
    values = dict(raw)
    for field in ("hours", "minutes", "weekdays"):
        if field in values:
            values[field] = tuple(values[field])
    return Contract(**values)


def _manifest_pairs() -> set[tuple[str, str]]:
    manifest = json.loads((ROOT / "data/tzdb/manifest.json").read_text())
    return {(row["version"], row["zone"]) for row in manifest}


def _start(cfg: dict[str, Any], zone) -> datetime:
    value = datetime.fromisoformat(cfg["start"])
    if value.tzinfo is not None:
        raise ValueError("Use a naive local start label plus start_fold")
    fold = cfg.get("start_fold", 0)
    if type(fold) is not int or fold not in (0, 1):
        raise ValueError("start_fold must be 0 or 1")
    value = value.replace(tzinfo=zone, fold=fold)
    return value


def _execute_cell(
    implementation: str,
    tzdb: str,
    zone_name: str,
    start_label: dict[str, Any],
    contract: Contract,
    count: int,
) -> dict[str, Any]:
    if (tzdb, zone_name) not in _manifest_pairs():
        raise ValueError(f"Zone/version not in pinned manifest: {tzdb}/{zone_name}")
    zone = load_zone(tzdb, zone_name)
    start = _start(start_label, zone)
    oracle = TZif(ROOT / "data/tzdb" / tzdb / zone_name)
    if start.timestamp() not in oracle.resolve(start.replace(tzinfo=None)):
        raise ValueError("Starting label is nonexistent; choose a valid start instant")
    run = run_trace(implementation, zone, contract, start.timestamp(), count)
    run["qualification"] = qualify(
        oracle,
        contract,
        start.timestamp(),
        run["trace"],
        run["error"],
    )
    return run


def _single(cfg: dict[str, Any]) -> tuple[dict[str, Any], int]:
    unknown = set(cfg) - SINGLE_FIELDS
    if unknown:
        raise ValueError(f"Unknown single-check fields: {sorted(unknown)}")
    contract = _contract(cfg["contract"])
    run = _execute_cell(
        cfg["implementation"],
        cfg["tzdb"],
        cfg["zone"],
        cfg,
        contract,
        int(cfg.get("count", 8)),
    )
    result = {"mode": "single", "input": cfg, **run}
    return result, STATUS_EXIT[run["qualification"]["status"]]


def _upgrade(cfg: dict[str, Any]) -> tuple[dict[str, Any], int]:
    unknown = set(cfg) - UPGRADE_FIELDS
    if unknown:
        raise ValueError(f"Unknown upgrade-check fields: {sorted(unknown)}")
    contract = _contract(cfg["contract"])
    count = int(cfg.get("count", 8))
    coordinates = {
        "old_code_old_data": (cfg["old_implementation"], cfg["old_tzdb"]),
        "new_code_old_data": (cfg["new_implementation"], cfg["old_tzdb"]),
        "old_code_new_data": (cfg["old_implementation"], cfg["new_tzdb"]),
        "new_code_new_data": (cfg["new_implementation"], cfg["new_tzdb"]),
    }
    cells = {
        name: _execute_cell(
            implementation,
            tzdb,
            cfg["zone"],
            cfg,
            contract,
            count,
        )
        for name, (implementation, tzdb) in coordinates.items()
    }
    statuses = {
        name: cell["qualification"]["status"] for name, cell in cells.items()
    }
    traces = {
        name: tuple(float(event["timestamp"]) for event in cell["trace"])
        for name, cell in cells.items()
    }
    certificate = classify_upgrade_square(statuses, traces)
    result = {
        "mode": "upgrade",
        "input": cfg,
        "coordinates": {
            name: {"implementation": value[0], "tzdb": value[1]}
            for name, value in coordinates.items()
        },
        "cells": cells,
        "certificate": certificate,
    }
    target_status = statuses["new_code_new_data"]
    return result, STATUS_EXIT[target_status]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Finite qualification JSON")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        cfg = json.loads(args.config.read_text())
        mode = cfg.get("mode", "single")
        if mode == "single":
            result, exit_code = _single(cfg)
        elif mode == "upgrade":
            result, exit_code = _upgrade(cfg)
        else:
            raise ValueError("mode must be 'single' or 'upgrade'")
        rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered)
        print(rendered, end="")
        return exit_code
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(
            json.dumps({"status": "CONFIGURATION_ERROR", "message": str(exc)}),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
