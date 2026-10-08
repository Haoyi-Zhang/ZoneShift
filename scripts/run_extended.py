#!/usr/bin/env python3
"""Extended, bounded robustness and two-axis update experiments.

The script reuses the frozen released calculation modules and byte-pinned TZif
files in the artifact.  It adds: (1) a code-version x rule-data matrix,
(2) executable policy-branch checks, (3) mutation sensitivity/specificity, and
(4) comparator accounting over the already executed boundary corpus.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zoneshift.contracts import (
    COMPLETE_FOLD_POLICIES,
    COMPLETE_GAP_POLICIES,
    Contract,
    policy_completion_frontier,
    qualify,
    reference,
    required,
)
from zoneshift.execution import load_zone, run_trace
from zoneshift.tzif import EPOCH, TZif
from zoneshift.profiles import PROFILES

P = json.loads((ROOT / "configs/protocol.json").read_text())
UTC = timezone.utc

def dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def trace_values(run: dict) -> tuple[float, ...]:
    return tuple(x["timestamp"] for x in run["trace"])


def all_zones() -> list[str]:
    """Original 16-zone corpus shared by the 2024a/2025b factorial matrix."""
    return sorted(set(P["discovery_zones"] + P["extension_zones"] +
                      P["negative_control_zones"] + [P["rule_change_zone"]]))


def file_hash(version: str, zone: str) -> str:
    return hashlib.sha256((ROOT / "data/tzdb" / version / zone).read_bytes()).hexdigest()


def transition_starts(zone: str, year: int) -> list[tuple[int, str, int, int]]:
    """Union transition-sensitive starts across both pinned rule snapshots."""
    starts: dict[int, tuple[str, int, int]] = {}
    lo = int(datetime(year, 1, 1, tzinfo=UTC).timestamp())
    hi = int(datetime(year + 1, 1, 1, tzinfo=UTC).timestamp())
    for version in (P["tzdb_main"], P["tzdb_update"]):
        tz = TZif(ROOT / "data/tzdb" / version / zone)
        for tr in tz.transitions:
            if lo <= tr.utc < hi:
                for offset in P["transition_anchor_offsets_seconds"]:
                    starts.setdefault(tr.utc + offset, ("transition", tr.delta, offset))
    for month in (1, 4, 7, 10):
        stamp = int(datetime(year, month, 15, 12, tzinfo=UTC).timestamp())
        starts.setdefault(stamp, ("ordinary", 0, 0))
    return [(t, *starts[t]) for t in sorted(starts)]


def factorial_matrix(out: Path) -> dict:
    rows = []
    begin = time.perf_counter_ns()
    zones = all_zones()
    ref_cache = {
        (version, zone): TZif(ROOT / "data/tzdb" / version / zone)
        for version in (P["tzdb_main"], P["tzdb_update"])
        for zone in zones
    }
    zone_cache = {
        (version, zone): load_zone(version, zone)
        for version in (P["tzdb_main"], P["tzdb_update"])
        for zone in zones
    }
    for zone in zones:
        hashes = {v: file_hash(v, zone) for v in (P["tzdb_main"], P["tzdb_update"])}
        for year in P["factorial_years"]:
            for start, kind, delta, offset in transition_starts(zone, year):
                for profile in P["factorial_profiles"]:
                    contract = PROFILES[profile]
                    case_id = f"{zone}:{year}:{start}:{profile}"
                    for implementation in P["implementations"]:
                        for tzdb in (P["tzdb_main"], P["tzdb_update"]):
                            z = zone_cache[tzdb, zone]
                            ref = ref_cache[tzdb, zone]
                            run = run_trace(implementation, z, contract, start)
                            q = qualify(ref, contract, start, run["trace"], run["error"])
                            rows.append(
                                {
                                    "case_id": case_id,
                                    "zone": zone,
                                    "year": year,
                                    "profile": profile,
                                    "start": start,
                                    "kind": kind,
                                    "transition_delta": delta,
                                    "anchor_offset": offset,
                                    "implementation": implementation,
                                    "tzdb": tzdb,
                                    "zone_file_sha256": hashes[tzdb],
                                    **run,
                                    "qualification": q,
                                }
                            )
    by = {(r["case_id"], r["implementation"], r["tzdb"]): r for r in rows}
    data_counts = Counter()
    zone_counts = Counter()
    for case_id, implementation in sorted({(r["case_id"], r["implementation"]) for r in rows}):
        a = by[case_id, implementation, P["tzdb_main"]]
        b = by[case_id, implementation, P["tzdb_update"]]
        changed = trace_values(a) != trace_values(b)
        byte_changed = a["zone_file_sha256"] != b["zone_file_sha256"]
        statuses = (a["qualification"]["status"], b["qualification"]["status"])
        if changed and statuses == ("PASS", "PASS"):
            cls = "accepted_data_effect"
        elif changed:
            cls = "changed_with_violation_or_uncertainty"
        elif byte_changed:
            cls = "byte_change_no_observed_behavior_change"
        else:
            cls = "identical_bytes_and_behavior"
        data_counts[implementation, cls] += 1
        zone_counts[a["zone"], cls] += 1

    code_pairs = (("aps-3.11.0", "aps-3.11.2"), ("croniter-1.3.10", "croniter-2.0.1"))
    code_counts = Counter()
    interactions = []
    for left, right in code_pairs:
        for case_id in sorted({r["case_id"] for r in rows}):
            differences = {}
            statuses = {}
            for tzdb in (P["tzdb_main"], P["tzdb_update"]):
                x, y = by[case_id, left, tzdb], by[case_id, right, tzdb]
                differences[tzdb] = trace_values(x) != trace_values(y)
                statuses[tzdb] = (x["qualification"]["status"], y["qualification"]["status"])
                code_counts[left, right, tzdb, "different" if differences[tzdb] else "same"] += 1
                code_counts[left, right, tzdb, *statuses[tzdb]] += 1
            data_left = trace_values(by[case_id, left, P["tzdb_main"]]) != trace_values(by[case_id, left, P["tzdb_update"]])
            data_right = trace_values(by[case_id, right, P["tzdb_main"]]) != trace_values(by[case_id, right, P["tzdb_update"]])
            interaction = differences[P["tzdb_main"]] != differences[P["tzdb_update"]] or data_left != data_right
            if interaction:
                base = by[case_id, left, P["tzdb_main"]]
                interactions.append(
                    {
                        "case_id": case_id,
                        "zone": base["zone"],
                        "profile": base["profile"],
                        "left": left,
                        "right": right,
                        "code_difference_by_tzdb": differences,
                        "data_effect_left": data_left,
                        "data_effect_right": data_right,
                        "statuses": statuses,
                    }
                )

    summary = {
        "design": {
            "zones": len(zones),
            "years": P["factorial_years"],
            "profiles": P["factorial_profiles"],
            "implementations": P["implementations"],
            "tzdb_versions": [P["tzdb_main"], P["tzdb_update"]],
            "same_utc_start_across_cells": True,
            "unit": "bounded next-occurrence trace; generated windows are not independent defects",
        },
        "traces": len(rows),
        "api_calls": sum(r["calls"] for r in rows),
        "timeouts": sum(r["error"] == "timeout" for r in rows),
        "elapsed_seconds": (time.perf_counter_ns() - begin) / 1e9,
        "data_effect_counts": {"|".join(k): v for k, v in sorted(data_counts.items())},
        "zone_effect_counts": {"|".join(k): v for k, v in sorted(zone_counts.items())},
        "code_effect_counts": {"|".join(k): v for k, v in sorted(code_counts.items())},
        "interaction_count": len(interactions),
        "interactions": interactions,
        "source_scope": {
            "America/Asuncion": "2025a NEWS documents permanent -03 and future changes beginning 2025-03-22",
            "other_byte_differences": "treated as byte changes only unless the measured future trace changes and a source explanation is available",
        },
    }
    dump(out / "version-data-matrix.json", {"summary": summary, "runs": rows})
    return summary



def _starts_for_versions(versions: list[str], zone: str, year: int) -> list[tuple[int, str, int, int]]:
    """Transition starts from a union of pinned rule snapshots plus ordinary controls."""
    starts: dict[int, tuple[str, int, int]] = {}
    lo = int(datetime(year, 1, 1, tzinfo=UTC).timestamp())
    hi = int(datetime(year + 1, 1, 1, tzinfo=UTC).timestamp())
    for version in versions:
        tz = TZif(ROOT / "data/tzdb" / version / zone)
        for tr in tz.transitions:
            if lo <= tr.utc < hi:
                for offset in P["transition_anchor_offsets_seconds"]:
                    starts.setdefault(tr.utc + offset, ("transition", tr.delta, offset))
    for month in (1, 7):
        stamp = int(datetime(year, month, 15, 12, tzinfo=UTC).timestamp())
        starts.setdefault(stamp, ("ordinary", 0, 0))
    return [(t, *starts[t]) for t in sorted(starts)]


def current_release_holdout(out: Path) -> dict:
    """Execute current releases on zones excluded from source-led discovery."""
    cfg = P["current_release_holdout"]
    pairs = {
        "aps-3.11.3": "aps-3.11.2",
        "croniter-6.2.4": "croniter-2.0.1",
    }
    implementations = [x for pair in pairs.items() for x in pair]
    # Preserve order while removing duplicates.
    implementations = list(dict.fromkeys(implementations))
    rows = []
    begin = time.perf_counter_ns()
    ref_cache = {z: TZif(ROOT / "data/tzdb" / cfg["tzdb"] / z) for z in cfg["zones"]}
    zone_cache = {z: load_zone(cfg["tzdb"], z) for z in cfg["zones"]}
    for zone in cfg["zones"]:
        ref, zinfo = ref_cache[zone], zone_cache[zone]
        for year in cfg["years"]:
            for start, kind, delta, offset in _starts_for_versions([cfg["tzdb"]], zone, year):
                for profile in P["profiles"]:
                    contract = PROFILES[profile]
                    case_id = f"{zone}:{year}:{start}:{profile}"
                    for implementation in implementations:
                        run = run_trace(implementation, zinfo, contract, start)
                        q = qualify(ref, contract, start, run["trace"], run["error"])
                        rows.append({
                            "case_id": case_id, "zone": zone, "year": year,
                            "profile": profile, "start": start, "kind": kind,
                            "transition_delta": delta, "anchor_offset": offset,
                            "implementation": implementation, "tzdb": cfg["tzdb"],
                            **run, "qualification": q,
                        })
    by = {(r["case_id"], r["implementation"]): r for r in rows}
    statuses = Counter((r["implementation"], r["qualification"]["status"]) for r in rows)
    reasons = Counter()
    for r in rows:
        for reason in r["qualification"]["reasons"]:
            reasons[r["implementation"], reason] += 1
    comparisons = {}
    for current, predecessor in pairs.items():
        c = Counter()
        for case_id in sorted({r["case_id"] for r in rows}):
            a, b = by[case_id, predecessor], by[case_id, current]
            changed = trace_values(a) != trace_values(b)
            st = (a["qualification"]["status"], b["qualification"]["status"])
            c["cases"] += 1
            c["changed"] += changed
            c[f"status:{st[0]}:{st[1]}"] += 1
        comparisons[f"{predecessor}->{current}"] = dict(c)
    summary = {
        "design": cfg,
        "comparison_predecessors": pairs,
        "traces": len(rows),
        "api_calls": sum(r["calls"] for r in rows),
        "timeouts": sum(r["error"] == "timeout" for r in rows),
        "nonprogress": sum(r["error"] == "nonprogress" for r in rows),
        "status_counts": {"|".join(k): v for k, v in sorted(statuses.items())},
        "reason_counts": {"|".join(k): v for k, v in sorted(reasons.items())},
        "release_comparisons": comparisons,
        "elapsed_seconds": (time.perf_counter_ns() - begin) / 1e9,
        "interpretation": "Time-separated release holdout on non-discovery zones; generated windows are observations, not independent defects.",
    }
    dump(out / "current-release-holdout.json", {"summary": summary, "runs": rows})
    return summary


def current_tzdb_holdout(out: Path) -> dict:
    """Evaluate zones named by IANA 2026a/2026b release notes before outcome inspection."""
    cfg = P["current_tzdb_holdout"]
    rows = []
    begin = time.perf_counter_ns()
    ref_cache = {(v, z): TZif(ROOT / "data/tzdb" / v / z)
                 for v in cfg["versions"] for z in cfg["zones"]}
    zone_cache = {(v, z): load_zone(v, z)
                  for v in cfg["versions"] for z in cfg["zones"]}
    for zone in cfg["zones"]:
        for year in cfg["years"]:
            for start, kind, delta, offset in _starts_for_versions(cfg["versions"], zone, year):
                for profile in P["profiles"]:
                    contract = PROFILES[profile]
                    case_id = f"{zone}:{year}:{start}:{profile}"
                    for implementation in cfg["implementations"]:
                        for version in cfg["versions"]:
                            run = run_trace(implementation, zone_cache[version, zone], contract, start)
                            q = qualify(ref_cache[version, zone], contract, start, run["trace"], run["error"])
                            rows.append({
                                "case_id": case_id, "zone": zone, "year": year,
                                "profile": profile, "start": start, "kind": kind,
                                "transition_delta": delta, "anchor_offset": offset,
                                "implementation": implementation, "tzdb": version,
                                "zone_file_sha256": file_hash(version, zone),
                                **run, "qualification": q,
                            })
    by = {(r["case_id"], r["implementation"], r["tzdb"]): r for r in rows}
    effects = Counter(); zone_effects = Counter(); examples = []
    old, new = cfg["versions"]
    for case_id, implementation in sorted({(r["case_id"], r["implementation"]) for r in rows}):
        a, b = by[case_id, implementation, old], by[case_id, implementation, new]
        changed = trace_values(a) != trace_values(b)
        byte_changed = a["zone_file_sha256"] != b["zone_file_sha256"]
        statuses = (a["qualification"]["status"], b["qualification"]["status"])
        if changed and statuses == ("PASS", "PASS"):
            cls = "accepted_data_effect"
        elif changed:
            cls = "changed_with_violation_or_uncertainty"
        elif byte_changed:
            cls = "byte_change_no_observed_behavior_change"
        else:
            cls = "identical_bytes_and_behavior"
        effects[implementation, cls] += 1
        zone_effects[a["zone"], cls] += 1
        if changed and len(examples) < 24:
            examples.append({
                "case_id": case_id, "implementation": implementation,
                "zone": a["zone"], "statuses": statuses, "classification": cls,
                "old_trace": trace_values(a), "new_trace": trace_values(b),
            })
    summary = {
        "design": cfg,
        "traces": len(rows),
        "api_calls": sum(r["calls"] for r in rows),
        "timeouts": sum(r["error"] == "timeout" for r in rows),
        "effect_counts": {"|".join(k): v for k, v in sorted(effects.items())},
        "zone_effect_counts": {"|".join(k): v for k, v in sorted(zone_effects.items())},
        "changed_examples": examples,
        "elapsed_seconds": (time.perf_counter_ns() - begin) / 1e9,
        "release_note_scope": {
            "Europe/Chisinau": "IANA 2026a corrected Moldova transition times since 2022",
            "America/Vancouver": "IANA 2026b modeled British Columbia permanent -07 after the 2026 transition",
        },
        "interpretation": "Locally executable 2025b-to-2026b rule-data holdout; it does not cover later 2026c-2026e releases.",
    }
    dump(out / "current-tzdb-holdout.json", {"summary": summary, "runs": rows})
    return summary


def decision_records(out: Path) -> dict:
    """Emit compact, machine-checkable promotion records and replay witnesses."""
    sources = [
        ("current-release", json.loads((out / "current-release-holdout.json").read_text())["runs"]),
        ("current-tzdb", json.loads((out / "current-tzdb-holdout.json").read_text())["runs"]),
    ]
    vendor = {r["path"]: r for r in json.loads((ROOT / "vendor/MANIFEST.json").read_text())}
    records = []
    representatives = {}
    for study, runs in sources:
        for r in runs:
            trace_bytes = json.dumps(r["trace"], sort_keys=True, separators=(",", ":")).encode()
            contract = PROFILES[r["profile"]]
            impl = r["implementation"]
            if impl.startswith("aps-"):
                source_path = f"vendor/apscheduler-{impl[4:]}/apscheduler/triggers/cron/__init__.py"
            else:
                source_path = f"vendor/croniter-{impl[9:]}/croniter.py"
            record = {
                "schema": "zoneshift.decision-record",
                "study": study,
                "case_id": r["case_id"],
                "implementation": impl,
                "implementation_source_sha256": vendor[source_path]["sha256"],
                "tzdb": r["tzdb"],
                "zone": r["zone"],
                "zone_file_sha256": file_hash(r["tzdb"], r["zone"]),
                "contract": {
                    "hours": list(contract.hours), "minutes": list(contract.minutes),
                    "gap": contract.gap, "fold": contract.fold,
                },
                "start": r["start"],
                "trace_sha256": hashlib.sha256(trace_bytes).hexdigest(),
                "calls": r["calls"],
                "error": r["error"],
                "verdict": r["qualification"]["status"],
                "reasons": r["qualification"]["reasons"],
            }
            records.append(record)
            reason = record["reasons"][0] if record["reasons"] else "none"
            key = (study, impl, record["verdict"], reason)
            representatives.setdefault(key, {
                **record,
                "expected_trace": r["trace"],
                "replay": f"python scripts/replay_record.py --study {study} --case-id {r['case_id']} --implementation {impl}",
            })
    with (out / "decision-records.jsonl").open("w") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    pack = {
        "schema": "zoneshift.regression-pack",
        "selection": "first deterministic representative per study, implementation, verdict, and first reason",
        "records": list(representatives.values()),
    }
    dump(out / "regression-pack.json", pack)
    result = {
        "records": len(records),
        "representatives": len(pack["records"]),
        "decision_record_sha256": hashlib.sha256((out / "decision-records.jsonl").read_bytes()).hexdigest(),
        "regression_pack_sha256": hashlib.sha256((out / "regression-pack.json").read_bytes()).hexdigest(),
    }
    dump(out / "decision-record-summary.json", result)
    return result

def event_trace(timestamps: list[float], zone: TZif) -> list[dict]:
    return [
        {"timestamp": t, "iso": zone.wall(t).isoformat(), "fold": 0}
        for t in timestamps
    ]


def minute_inside(lo: int, hi: int) -> datetime:
    """Choose a whole-minute civil label in [lo, hi)."""
    value = ((lo + 59) // 60) * 60
    if value >= hi:
        value = lo
    return EPOCH + timedelta(seconds=value)


def policy_matrix(out: Path) -> dict:
    """Exercise every complete gap/fold policy and incomplete-policy frontier."""
    fold_rows: list[dict] = []
    gap_rows: list[dict] = []
    for zone_name in all_zones():
        zone = TZif(ROOT / "data/tzdb" / P["tzdb_main"] / zone_name)
        for transition in zone.transitions:
            year = datetime.fromtimestamp(transition.utc, UTC).year
            if year not in P["years"]:
                continue
            start = transition.utc - 2 * 86400
            if transition.delta < 0:
                label = minute_inside(
                    transition.utc + transition.after,
                    transition.utc + transition.before,
                )
                variants: dict[str, list[dict]] = {}
                for policy in COMPLETE_FOLD_POLICIES:
                    contract = Contract(
                        (label.hour,),
                        (label.minute,),
                        gap="skip",
                        fold=policy,
                    )
                    events, _ = reference(zone, contract, start, 10)
                    variants[policy] = event_trace(required(events, contract)[:8], zone)
                for expected_policy, trace in variants.items():
                    for checked_policy in (*COMPLETE_FOLD_POLICIES, "unspecified"):
                        contract = Contract(
                            (label.hour,),
                            (label.minute,),
                            gap="skip",
                            fold=checked_policy,
                        )
                        result = qualify(zone, contract, start, trace)
                        fold_rows.append(
                            {
                                "zone": zone_name,
                                "transition": transition.utc,
                                "label": label.isoformat(),
                                "trace_policy": expected_policy,
                                "checked_policy": checked_policy,
                                "status": result["status"],
                                "reasons": result["reasons"],
                                "passing_completions": result.get("policy_frontier", {}).get(
                                    "passing_completions", []
                                ),
                            }
                        )
            elif transition.delta > 0:
                label = minute_inside(
                    transition.utc + transition.before,
                    transition.utc + transition.after,
                )
                variants = {}
                for policy in COMPLETE_GAP_POLICIES:
                    contract = Contract(
                        (label.hour,),
                        (label.minute,),
                        gap=policy,
                        fold="both",
                    )
                    events, _ = reference(zone, contract, start, 10)
                    variants[policy] = event_trace(required(events, contract)[:8], zone)
                for expected_policy, trace in variants.items():
                    for checked_policy in (*COMPLETE_GAP_POLICIES, "unspecified"):
                        contract = Contract(
                            (label.hour,),
                            (label.minute,),
                            gap=checked_policy,
                            fold="both",
                        )
                        result = qualify(zone, contract, start, trace)
                        gap_rows.append(
                            {
                                "zone": zone_name,
                                "transition": transition.utc,
                                "label": label.isoformat(),
                                "trace_policy": expected_policy,
                                "checked_policy": checked_policy,
                                "status": result["status"],
                                "reasons": result["reasons"],
                                "passing_completions": result.get("policy_frontier", {}).get(
                                    "passing_completions", []
                                ),
                            }
                        )

    fold_counts = Counter(
        (row["trace_policy"], row["checked_policy"], row["status"])
        for row in fold_rows
    )
    gap_counts = Counter(
        (row["trace_policy"], row["checked_policy"], row["status"])
        for row in gap_rows
    )
    result = {
        "fold_cases": len(fold_rows),
        "gap_cases": len(gap_rows),
        "fold_counts": {"|".join(key): value for key, value in sorted(fold_counts.items())},
        "gap_counts": {"|".join(key): value for key, value in sorted(gap_counts.items())},
        "complete_gap_policies": list(COMPLETE_GAP_POLICIES),
        "complete_fold_policies": list(COMPLETE_FOLD_POLICIES),
        "interpretation": (
            "Self-consistency and policy-discrimination check of the bounded contract; "
            "not independent evidence of scheduler correctness"
        ),
        "fold_rows": fold_rows,
        "gap_rows": gap_rows,
    }
    dump(out / "policy-matrix.json", result)
    return result


def mutation_study(out: Path) -> dict:
    rows = []
    benign = []
    for zone_name in all_zones():
        zone = TZif(ROOT / "data/tzdb" / P["tzdb_main"] / zone_name)
        for year in (2023, 2024):
            starts = transition_starts(zone_name, year)
            # One deterministic boundary/ordinary start per zone-year-profile.
            start = next((x[0] for x in starts if x[1] == "transition" and x[3] == -86400), starts[0][0])
            for profile, contract in PROFILES.items():
                events, _ = reference(zone, contract, start, 10)
                vals = required(events, contract)[:9]
                if len(vals) < 9:
                    continue
                base = event_trace(vals[:8], zone)
                qbase = qualify(zone, contract, start, base)
                benign.append({"zone": zone_name, "year": year, "profile": profile, "kind": "valid", "status": qbase["status"]})
                metadata_only = [dict(x, iso="ignored-metadata", fold=1 - int(bool(x.get("fold", 0)))) for x in base]
                qmeta = qualify(zone, contract, start, metadata_only)
                benign.append({"zone": zone_name, "year": year, "profile": profile, "kind": "metadata_only", "status": qmeta["status"]})
                qprefix = qualify(zone, contract, start, base[:5])
                benign.append({"zone": zone_name, "year": year, "profile": profile, "kind": "valid_prefix", "status": qprefix["status"]})

                source9 = event_trace(vals, zone)
                mutants = {
                    "drop_middle": source9[:3] + source9[4:],
                    "repeat_previous": base[:3] + [dict(base[2])] + base[4:],
                    "swap_pair": base[:3] + [dict(base[4]), dict(base[3])] + base[5:],
                    "shift_37_seconds": base[:3] + [dict(base[3], timestamp=base[3]["timestamp"] + 37)] + base[4:],
                    "replace_with_start": base[:2] + [dict(base[2], timestamp=start)] + base[3:],
                }
                for operator, trace in mutants.items():
                    q = qualify(zone, contract, start, trace)
                    rows.append(
                        {
                            "zone": zone_name,
                            "year": year,
                            "profile": profile,
                            "operator": operator,
                            "status": q["status"],
                            "reasons": q["reasons"],
                        }
                    )

    # Dedicated forbidden-fold-branch mutations.
    for zone_name in all_zones():
        zone = TZif(ROOT / "data/tzdb" / P["tzdb_main"] / zone_name)
        fold = next((t for t in zone.transitions if t.delta < 0 and datetime.fromtimestamp(t.utc, UTC).year in P["years"]), None)
        if not fold:
            continue
        label = minute_inside(fold.utc + fold.after, fold.utc + fold.before)
        start = fold.utc - 86400
        both = Contract((label.hour,), (label.minute,), gap="skip", fold="both")
        events, _ = reference(zone, both, start, 10)
        second_trace = event_trace(required(events, Contract(both.hours, both.minutes, gap="skip", fold="second"))[:8], zone)
        q = qualify(zone, Contract(both.hours, both.minutes, gap="skip", fold="first"), start, second_trace)
        rows.append({"zone": zone_name, "year": datetime.fromtimestamp(fold.utc, UTC).year, "profile": "fold_label", "operator": "wrong_fold_branch", "status": q["status"], "reasons": q["reasons"]})

    op_counts = Counter((x["operator"], x["status"]) for x in rows)
    reason_counts = Counter((x["operator"], reason) for x in rows for reason in x["reasons"])
    benign_counts = Counter((x["kind"], x["status"]) for x in benign)
    result = {
        "mutants": len(rows),
        "detected": sum(x["status"] == "VIOLATION" for x in rows),
        "operator_counts": {"|".join(k): v for k, v in sorted(op_counts.items())},
        "reason_counts": {"|".join(k): v for k, v in sorted(reason_counts.items())},
        "benign_cases": len(benign),
        "benign_counts": {"|".join(k): v for k, v in sorted(benign_counts.items())},
        "interpretation": "Trace-level sensitivity test; mutants are not independent real defects and share the checker that defines the contract",
        "rows": rows,
        "benign": benign,
    }
    dump(out / "mutation-study.json", result)
    return result


def comparator_analysis(out: Path) -> dict:
    runs = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines()]
    boundary = [x for x in runs if x["strategy"] == "boundary"]
    policy_blind = Counter()
    full = Counter()
    for x in boundary:
        status = x["qualification"]["status"]
        alarm = bool(x["policy_blind_alarm"])
        policy_blind["alarms"] += alarm
        policy_blind["actionable_alarms"] += alarm and status == "VIOLATION"
        policy_blind["false_alarms_on_pass"] += alarm and status == "PASS"
        policy_blind["alarms_on_underspecified"] += alarm and status == "UNDERSPECIFIED"
        policy_blind["missed_violations"] += (not alarm) and status == "VIOLATION"
        full["violations"] += status == "VIOLATION"
        full["passes"] += status == "PASS"
        full["underspecified"] += status == "UNDERSPECIFIED"

    pairs = defaultdict(dict)
    for x in boundary:
        pairs[x["case_id"]][x["implementation"]] = x

    def differential(left: str, right: str) -> dict:
        c = Counter()
        examples = []
        for case_id, p in pairs.items():
            if left not in p or right not in p:
                continue
            a, b = p[left], p[right]
            alarm = trace_values(a) != trace_values(b)
            statuses = (a["qualification"]["status"], b["qualification"]["status"])
            has_violation = "VIOLATION" in statuses
            unresolved_only = not has_violation and "UNDERSPECIFIED" in statuses
            c["pairs"] += 1
            c["alarms"] += alarm
            c["actionable_alarms"] += alarm and has_violation
            c["false_alarms_both_pass"] += alarm and statuses == ("PASS", "PASS")
            c["alarms_with_only_uncertainty"] += alarm and unresolved_only
            c["shared_or_equal_missed_violations"] += (not alarm) and has_violation
            c[f"status:{statuses[0]}:{statuses[1]}"] += 1
            if len(examples) < 12 and (alarm or has_violation):
                examples.append({"case_id": case_id, "alarm": alarm, "statuses": statuses})
        return {"counts": dict(c), "examples": examples}

    upstream = json.loads((out / "upstream-inputs.json").read_text())
    targeted = Counter()
    for x in upstream:
        targeted[x["version"], "pass" if x["passed"] else "fail"] += 1

    summary = json.loads((out / "benchmark-summary.json").read_text())
    uniform = {}
    for impl in P["implementations"]:
        b = next(x for x in summary if x["implementation"] == impl and x["strategy"] == "boundary")
        u = [x["violation"] for x in summary if x["implementation"] == impl and x["strategy"] == "uniform"]
        uniform[impl] = {
            "boundary_violations": b["violation"],
            "uniform_mean_violations": statistics.mean(u),
            "uniform_min": min(u),
            "uniform_max": max(u),
            "equal_windows": b["n"],
        }

    result = {
        "unit": "selected bounded case/module observation; not a population estimate",
        "policy_blind_first_branch": dict(policy_blind),
        "policy_aware_three_way": dict(full),
        "naive_cross_library": differential("aps-3.11.2", "croniter-2.0.1"),
        "release_differential_aps": differential("aps-3.11.0", "aps-3.11.2"),
        "release_differential_croniter": differential("croniter-1.3.10", "croniter-2.0.1"),
        "targeted_upstream_inputs": {"|".join(k): v for k, v in sorted(targeted.items())},
        "sampling_yield": uniform,
    }
    dump(out / "comparator-analysis.json", result)
    return result


def integration_metrics(out: Path) -> dict:
    paths = [
        ROOT / "zoneshift/contracts.py",
        ROOT / "zoneshift/tzif.py",
        ROOT / "zoneshift/adapters.py",
        ROOT / "zoneshift/vendor_support.py",
        ROOT / "zoneshift/execution.py",
        ROOT / "zoneshift/repair.py",
        ROOT / "zoneshift/attribution.py",
        ROOT / "zoneshift/profiles.py",
        ROOT / "zoneshift/__main__.py",
        ROOT / "zoneshift/__init__.py",
    ]
    def sloc(path: Path) -> int:
        return sum(1 for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#"))
    result = {
        "core_python_sloc_nonblank_noncomment": {p.relative_to(ROOT).as_posix(): sloc(p) for p in paths},
        "core_total_sloc": sum(sloc(p) for p in paths),
        "protocol_top_level_fields": len(P),
        "pinned_zone_files": len(json.loads((ROOT / "data/tzdb/manifest.json").read_text())),
        "notes": "SLOC is an observable artifact measure, not engineer effort or adoption cost",
    }
    dump(out / "integration-metrics.json", result)
    return result


def current_release_scope(out: Path) -> dict:
    result = {
        "checked_on": "2026-10-04",
        "apscheduler": {
            "release": "3.11.3",
            "published_at": "2026-06-28T19:39:26Z",
            "release_url": "https://github.com/agronholm/apscheduler/releases/tag/3.11.3",
            "source_blob_sha1": "028262fad3d0b95d77c151541ca3d780c19a0721",
            "direct_path_change_from_3.11.2": "documentation-only weekday warning in CronTrigger.from_crontab",
            "experiment_status": "executed in current-release, current-tzdb, and stepwise IANA-release holdouts",
        },
        "croniter": {
            "release": "6.2.4",
            "published_at": "2026-07-10T09:55:08Z",
            "release_url": "https://github.com/pallets-eco/croniter/releases/tag/6.2.4",
            "upstream_source_blob_sha1": "30c42608bc436de892f957c0109a21647d0ef457",
            "experiment_status": "executed in current-release, current-tzdb, and stepwise IANA-release holdouts; historical Sentry replay remains pinned to 1.3.10",
        },
        "tzdb": {
            "executed_current_holdout": "2026e",
            "executed_release_chain": ["2025b", "2026a", "2026b", "2026c", "2026d", "2026e"],
            "latest_verified_release_at_check": "2026e",
            "latest_release_date": "2026-09-29",
            "scope_note": "The stepwise source-named holdout executes exact TZif bytes from tagged Python tzdata 2025.2 and 2026.1--2026.5 distributions; the historical core remains fixed to 2024a/2025b.",
        },
        "interpretation": "Source metadata plus separately reported historical, current-module, and stepwise rule-release executions; no release-note-only behavior is counted as empirical evidence.",
    }
    dump(out / "current-release-scope.json", result)
    return result

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    out = args.output
    out.mkdir(exist_ok=True, parents=True)
    start = time.perf_counter()
    results = {
        "factorial": factorial_matrix(out),
        "policy": {k: v for k, v in policy_matrix(out).items() if not k.endswith("rows")},
        "mutation": {k: v for k, v in mutation_study(out).items() if k not in {"rows", "benign"}},
        "comparators": comparator_analysis(out),
        "integration": integration_metrics(out),
        "current_release": current_release_holdout(out),
        "current_tzdb": current_tzdb_holdout(out),
        "decision_records": decision_records(out),
        "current_release_scope": current_release_scope(out),
    }
    results["wall_seconds"] = time.perf_counter() - start
    dump(out / "extended-analysis.json", results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
