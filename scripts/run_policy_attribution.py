#!/usr/bin/env python3
"""Execute policy-completion and two-coordinate attribution analyses."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zoneshift.attribution import classify_upgrade_square
from zoneshift.contracts import Contract, policy_completion_frontier
from zoneshift.execution import load_zone, run_trace
from zoneshift.tzif import EPOCH, TZif

UTC = timezone.utc
P = json.loads((ROOT / "configs/protocol.json").read_text())
IMPLEMENTATIONS = (
    "aps-3.11.0",
    "aps-3.11.1",
    "aps-3.11.2",
    "aps-3.11.3",
    "croniter-1.3.10",
    "croniter-2.0.1",
    "croniter-6.2.4",
)


def dump(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def minute_inside(lower: int, upper: int) -> datetime:
    value = ((lower + 59) // 60) * 60
    if value >= upper:
        value = lower
    return EPOCH + timedelta(seconds=value)


def corpus_zones() -> list[str]:
    return sorted(
        set(
            P["discovery_zones"]
            + P["extension_zones"]
            + P["negative_control_zones"]
            + [P["rule_change_zone"]]
        )
    )


def policy_frontier_study(out: Path) -> dict[str, object]:
    """Run real schedulers on labels whose behavior depends on gap/fold policy."""

    begin = time.perf_counter_ns()
    rows: list[dict[str, object]] = []
    zone_cache = {zone: load_zone(P["tzdb_main"], zone) for zone in corpus_zones()}
    reference_cache = {
        zone: TZif(ROOT / "data/tzdb" / P["tzdb_main"] / zone)
        for zone in corpus_zones()
    }

    for zone_name, reference_zone in reference_cache.items():
        runtime_zone = zone_cache[zone_name]
        for transition in reference_zone.transitions:
            year = datetime.fromtimestamp(transition.utc, UTC).year
            if year not in P["years"] or transition.delta == 0:
                continue
            start = transition.utc - 2 * 86400
            if transition.delta < 0:
                kind = "fold"
                label = minute_inside(
                    transition.utc + transition.after,
                    transition.utc + transition.before,
                )
                contract = Contract(
                    (label.hour,),
                    (label.minute,),
                    gap="skip",
                    fold="unspecified",
                )
            else:
                kind = "gap"
                label = minute_inside(
                    transition.utc + transition.before,
                    transition.utc + transition.after,
                )
                contract = Contract(
                    (label.hour,),
                    (label.minute,),
                    gap="unspecified",
                    fold="both",
                )

            for implementation in IMPLEMENTATIONS:
                run = run_trace(implementation, runtime_zone, contract, start)
                frontier = policy_completion_frontier(
                    reference_zone,
                    contract,
                    start,
                    run["trace"],
                    run["error"],
                )
                support = [
                    f"{item['gap']}+{item['fold']}"
                    for item in frontier["passing_completions"]
                ]
                rows.append(
                    {
                        "case_id": f"{zone_name}:{transition.utc}:{kind}:{label.isoformat()}",
                        "zone": zone_name,
                        "year": year,
                        "transition": transition.utc,
                        "transition_delta": transition.delta,
                        "kind": kind,
                        "label": label.isoformat(),
                        "start": start,
                        "implementation": implementation,
                        "contract": contract.to_dict(),
                        "trace": run["trace"],
                        "error": run["error"],
                        "calls": run["calls"],
                        "frontier": frontier,
                        "support_pattern": support,
                    }
                )

    counts = Counter(
        (str(row["implementation"]), str(row["kind"]), str(row["frontier"]["classification"]))
        for row in rows
    )
    support_counts = Counter(
        (
            str(row["implementation"]),
            str(row["kind"]),
            ",".join(row["support_pattern"]) or "none",
        )
        for row in rows
    )
    summary = {
        "design": {
            "tzdb": P["tzdb_main"],
            "zones": len(corpus_zones()),
            "years": P["years"],
            "implementations": list(IMPLEMENTATIONS),
            "selection": "one whole-minute label inside every measured gap or fold",
            "unit": "one executed scheduler trace and its finite policy-completion frontier",
        },
        "traces": len(rows),
        "api_calls": sum(int(row["calls"]) for row in rows),
        "timeouts": sum(row["error"] == "timeout" for row in rows),
        "classification_counts": {
            "|".join(key): value for key, value in sorted(counts.items())
        },
        "support_pattern_counts": {
            "|".join(key): value for key, value in sorted(support_counts.items())
        },
        "elapsed_seconds": (time.perf_counter_ns() - begin) / 1e9,
        "interpretation": (
            "A policy-sensitive trace is not a defect until the application selects a completion; "
            "a robust violation fails every admissible completion."
        ),
    }
    result = {"summary": summary, "runs": rows}
    dump(out / "policy-frontiers.json", result)
    return summary


def upgrade_sufficiency_study(out: Path) -> dict[str, object]:
    """Derive verdict-level sufficiency certificates from the executed 2x2 matrix."""

    matrix = json.loads((out / "version-data-matrix.json").read_text())
    runs = matrix["runs"]
    by = {
        (row["case_id"], row["implementation"], row["tzdb"]): row
        for row in runs
    }
    pairs = (
        ("aps-3.11.0", "aps-3.11.2"),
        ("croniter-1.3.10", "croniter-2.0.1"),
    )
    rows: list[dict[str, object]] = []
    counts = Counter()

    for old_code, new_code in pairs:
        case_ids = sorted(
            {
                row["case_id"]
                for row in runs
                if row["implementation"] in {old_code, new_code}
            }
        )
        for case_id in case_ids:
            cell_rows = {
                "old_code_old_data": by[case_id, old_code, P["tzdb_main"]],
                "new_code_old_data": by[case_id, new_code, P["tzdb_main"]],
                "old_code_new_data": by[case_id, old_code, P["tzdb_update"]],
                "new_code_new_data": by[case_id, new_code, P["tzdb_update"]],
            }
            statuses = {
                name: str(row["qualification"]["status"])
                for name, row in cell_rows.items()
            }
            traces = {
                name: tuple(float(event["timestamp"]) for event in row["trace"])
                for name, row in cell_rows.items()
            }
            certificate = classify_upgrade_square(statuses, traces)
            sample = cell_rows["old_code_old_data"]
            record = {
                "case_id": case_id,
                "zone": sample["zone"],
                "year": sample["year"],
                "profile": sample["profile"],
                "old_code": old_code,
                "new_code": new_code,
                "old_data": P["tzdb_main"],
                "new_data": P["tzdb_update"],
                "statuses": statuses,
                **certificate,
            }
            rows.append(record)
            counts[(f"{old_code}->{new_code}", str(certificate["decision"]))] += 1

    summary = {
        "certificates": len(rows),
        "decision_counts": {
            "|".join(key): value for key, value in sorted(counts.items())
        },
        "noncommutative_observations": sum(
            bool(row["noncommutative_observation"]) for row in rows
        ),
        "interpretation": (
            "Minimal sufficient coordinate sets describe the executed square only; "
            "they do not claim population-level causal identification."
        ),
    }
    result = {"summary": summary, "certificates": rows}
    dump(out / "upgrade-sufficiency.json", result)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = {
        "policy_frontiers": policy_frontier_study(args.output),
        "upgrade_sufficiency": upgrade_sufficiency_study(args.output),
    }
    dump(args.output / "policy-attribution-summary.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
