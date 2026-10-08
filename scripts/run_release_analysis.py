#!/usr/bin/env python3
"""Release-series, signature-budget, and witness analyses for ZoneShift.

This driver adds three pieces that are intentionally distinct from simply
executing more correlated windows:

1. a stepwise IANA release-series holdout through 2026e using exact TZif bytes
   from the tagged Python tzdata distributions;
2. a de-correlated behavioural-signature/budget analysis over the already
   executed equal-budget pools; and
3. automatic reduction of blocked and accepted promotion witnesses to the
   shortest prefix that preserves the decision-relevant observation.

All outputs are deterministic except machine-time fields, which are reported
but excluded from reproduction digests.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import math
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zoneshift.contracts import Contract, qualify, reference, required
from zoneshift.execution import load_zone, run_trace
from zoneshift.tzif import TZif
from zoneshift.profiles import PROFILES

P = json.loads((ROOT / "configs/protocol.json").read_text())
UTC = timezone.utc

def dump(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def trace_values(run: dict) -> tuple[float, ...]:
    return tuple(x["timestamp"] for x in run["trace"])


def file_hash(version: str, zone: str) -> str:
    return hashlib.sha256((ROOT / "data/tzdb" / version / zone).read_bytes()).hexdigest()


def implementation_source_hash(implementation: str) -> str:
    """Hash the released calculation module actually loaded by the adapter."""
    if implementation.startswith("aps-"):
        version = implementation[4:]
        path = ROOT / "vendor" / f"apscheduler-{version}" / "apscheduler" / "triggers" / "cron" / "__init__.py"
    elif implementation.startswith("croniter-"):
        version = implementation[9:]
        path = ROOT / "vendor" / f"croniter-{version}" / "croniter.py"
    else:
        raise ValueError(f"unsupported witness implementation: {implementation}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def starts_for_pair(old: str, new: str, zone: str, year: int) -> list[tuple[int, str, int, int]]:
    """Union starts around all old/new transitions plus ordinary controls."""
    starts: dict[int, tuple[str, int, int]] = {}
    lo = int(datetime(year, 1, 1, tzinfo=UTC).timestamp())
    hi = int(datetime(year + 1, 1, 1, tzinfo=UTC).timestamp())
    for version in (old, new):
        tz = TZif(ROOT / "data/tzdb" / version / zone)
        for tr in tz.transitions:
            if lo <= tr.utc < hi:
                for offset in P["transition_anchor_offsets_seconds"]:
                    starts.setdefault(tr.utc + offset, ("transition", tr.delta, offset))
    for month in (1, 7):
        t = int(datetime(year, month, 15, 12, tzinfo=UTC).timestamp())
        starts.setdefault(t, ("ordinary", 0, 0))
    return [(t, *starts[t]) for t in sorted(starts)]


def release_series(out: Path) -> dict:
    """Execute each source-named consecutive tzdb release pair through 2026e."""
    cfg = P["rule_release_series"]
    rows: list[dict] = []
    begin = time.perf_counter_ns()
    for pair_index, spec in enumerate(cfg["pairs"]):
        old, new, zone = spec["old"], spec["new"], spec["zone"]
        versions = (old, new)
        refs = {v: TZif(ROOT / "data/tzdb" / v / zone) for v in versions}
        zones = {v: load_zone(v, zone) for v in versions}
        hashes = {v: file_hash(v, zone) for v in versions}
        pair_id = f"{old}->{new}:{zone}"
        for year in spec["years"]:
            for start, kind, delta, offset in starts_for_pair(old, new, zone, year):
                for profile in cfg["profiles"]:
                    contract = PROFILES[profile]
                    case_id = f"{pair_id}:{year}:{start}:{profile}"
                    for implementation in cfg["implementations"]:
                        for version in versions:
                            run = run_trace(implementation, zones[version], contract, start)
                            q = qualify(refs[version], contract, start, run["trace"], run["error"])
                            rows.append({
                                "pair_index": pair_index,
                                "pair_id": pair_id,
                                "source": spec["source"],
                                "case_id": case_id,
                                "zone": zone,
                                "year": year,
                                "profile": profile,
                                "start": start,
                                "kind": kind,
                                "transition_delta": delta,
                                "anchor_offset": offset,
                                "implementation": implementation,
                                "tzdb": version,
                                "zone_file_sha256": hashes[version],
                                **run,
                                "qualification": q,
                            })

    by = {(r["case_id"], r["implementation"], r["tzdb"]): r for r in rows}
    classifications: list[dict] = []
    counts = Counter()
    pair_counts = Counter()
    status_counts = Counter((r["tzdb"], r["implementation"], r["qualification"]["status"]) for r in rows)
    examples: dict[tuple, dict] = {}
    for spec in cfg["pairs"]:
        old, new, zone = spec["old"], spec["new"], spec["zone"]
        pair_id = f"{old}->{new}:{zone}"
        case_ids = sorted({r["case_id"] for r in rows if r["pair_id"] == pair_id})
        for case_id in case_ids:
            for implementation in cfg["implementations"]:
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
                record = {
                    "pair_id": pair_id,
                    "source": spec["source"],
                    "case_id": case_id,
                    "zone": zone,
                    "profile": a["profile"],
                    "start": a["start"],
                    "kind": a["kind"],
                    "transition_delta": a["transition_delta"],
                    "anchor_offset": a["anchor_offset"],
                    "implementation": implementation,
                    "implementation_source_sha256": implementation_source_hash(implementation),
                    "old": old,
                    "new": new,
                    "old_zone_file_sha256": a["zone_file_sha256"],
                    "new_zone_file_sha256": b["zone_file_sha256"],
                    "changed": changed,
                    "byte_changed": byte_changed,
                    "statuses": statuses,
                    "old_reasons": a["qualification"]["reasons"],
                    "new_reasons": b["qualification"]["reasons"],
                    "old_error": a["error"],
                    "new_error": b["error"],
                    "classification": cls,
                    "old_trace": a["trace"],
                    "new_trace": b["trace"],
                }
                classifications.append(record)
                counts[implementation, cls] += 1
                pair_counts[pair_id, implementation, cls] += 1
                examples.setdefault((pair_id, implementation, cls), record)

    decision_path = out / "release-series-decisions.jsonl"
    with decision_path.open("w", encoding="utf-8") as handle:
        for index, record in enumerate(classifications):
            decision = {
                "schema": "zoneshift.rule-release-decision",
                "record_id": f"rule-release-{index:05d}",
                "study": "rule-release-series",
                "contract": {
                    "profile": record["profile"],
                    "gap_policy": PROFILES[record["profile"]].gap,
                    "fold_policy": PROFILES[record["profile"]].fold,
                    "occurrences": P["occurrences_per_trace"],
                },
                **record,
            }
            handle.write(json.dumps(decision, sort_keys=True, ensure_ascii=False) + "\n")

    summary = {
        "design": cfg,
        "release_pairs": len(cfg["pairs"]),
        "decision_records": len(classifications),
        "affected_zones": len({x["zone"] for x in cfg["pairs"]}),
        "traces": len(rows),
        "api_calls": sum(r["calls"] for r in rows),
        "timeouts": sum(r["error"] == "timeout" for r in rows),
        "nonprogress": sum(r["error"] == "nonprogress" for r in rows),
        "status_counts": {"|".join(k): v for k, v in sorted(status_counts.items())},
        "classification_counts": {"|".join(k): v for k, v in sorted(counts.items())},
        "pair_classification_counts": {"|".join(k): v for k, v in sorted(pair_counts.items())},
        "representative_examples": list(examples.values()),
        "elapsed_seconds": (time.perf_counter_ns() - begin) / 1e9,
        "interpretation": (
            "Stepwise source-named release holdout through IANA 2026e. A release-note-supported "
            "difference is accepted only when both endpoint traces satisfy the declared contract; "
            "correlated windows are observations, not independent policy events."
        ),
    }
    dump(out / "rule-release-series.json", {"summary": summary, "classifications": classifications, "runs": rows})
    return summary



def release_series_conversion_validation(out: Path) -> dict:
    """Cross-check every retained release-series TZif transition with ZoneInfo.

    This is deliberately separate from the scheduler oracle: it checks the
    conversion layer at transition-1, transition, and transition+1 seconds.
    """
    cfg = P["rule_release_series"]
    inputs = sorted({(spec[side], spec["zone"]) for spec in cfg["pairs"] for side in ("old", "new")})
    lo = int(datetime(2022, 1, 1, tzinfo=UTC).timestamp())
    hi = int(datetime(2037, 1, 1, tzinfo=UTC).timestamp())
    checks = 0
    transitions = 0
    mismatches = []
    by_input = {}
    for version, zone_name in inputs:
        oracle = TZif(ROOT / "data/tzdb" / version / zone_name)
        library = load_zone(version, zone_name)
        local_checks = 0
        local_transitions = 0
        for tr in oracle.transitions:
            if not (lo <= tr.utc < hi):
                continue
            local_transitions += 1
            for instant in (tr.utc - 1, tr.utc, tr.utc + 1):
                expected = oracle.offset_at(instant)
                observed = int(datetime.fromtimestamp(instant, library).utcoffset().total_seconds())
                checks += 1
                local_checks += 1
                if expected != observed:
                    mismatches.append({
                        "version": version, "zone": zone_name, "instant": instant,
                        "expected_offset": expected, "zoneinfo_offset": observed,
                    })
        transitions += local_transitions
        by_input[f"{version}|{zone_name}"] = {
            "transition_records": local_transitions,
            "checks": local_checks,
            "zone_file_sha256": file_hash(version, zone_name),
        }
    result = {
        "inputs": len(inputs),
        "transition_records": transitions,
        "checks": checks,
        "mismatches": mismatches,
        "by_input": by_input,
        "horizon": [2022, 2037],
        "interpretation": "Exact-offset cross-check against ZoneInfo.from_file; shared TZif bytes remain a common dependency.",
    }
    dump(out / "release-series-validation.json", result)
    if mismatches:
        raise AssertionError(f"release-series conversion mismatches: {mismatches[:3]}")
    return result

def _first_mismatch(row: dict) -> tuple[str, int | str | None, int | None]:
    """Return normalized first mismatch kind, value and ordinal.

    Raw zone/year/time are intentionally excluded so equivalent scheduler
    behaviour at different transitions collapses to one behavioural signature.
    """
    if row["error"]:
        return "error", row["error"].split(":", 1)[0], len(row["trace"]) - 1
    zone = TZif(ROOT / "data/tzdb" / row["tzdb"] / row["zone"])
    contract = PROFILES[row["profile"]]
    events, _ = reference(zone, contract, row["start"], max(12, len(row["trace"]) + 4))
    expected = required(events, contract)
    actual = [x["timestamp"] for x in row["trace"]]
    for i, (a, e) in enumerate(zip(actual, expected)):
        if a != e:
            return "timestamp_delta", int(a - e), i
    if len(actual) < len(expected):
        # Qualification is finite-prefix based. Only label the first missing
        # required occurrence if it lies within the emitted coverage window.
        missing = row["qualification"].get("missing") or []
        if missing:
            try:
                ordinal = expected.index(missing[0])
            except ValueError:
                ordinal = len(actual)
            return "missing_required", "within_coverage", ordinal
    return "verdict_only", "+".join(row["qualification"]["reasons"]), None


def behaviour_signature(row: dict) -> str | None:
    if row["qualification"]["status"] != "VIOLATION":
        return None
    kind = "ordinary"
    if row["kind"] == "transition":
        if row["transition_delta"] > 0:
            kind = f"gap:{abs(row['transition_delta'])}"
        elif row["transition_delta"] < 0:
            kind = f"fold:{abs(row['transition_delta'])}"
        else:
            kind = "transition:0"
    mismatch, value, ordinal = _first_mismatch(row)
    payload = {
        "profile": row["profile"],
        "boundary": kind,
        "anchor_offset": row["anchor_offset"],
        "reasons": sorted(row["qualification"]["reasons"]),
        "mismatch": mismatch,
        "value": value,
        "ordinal": ordinal,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    pos = q * (len(values) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return float(values[lo])
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)


def signature_budget(out: Path) -> dict:
    """Describe violation/signature yield as a function of equal test budget."""
    cfg = P["signature_budget"]
    runs = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines()]
    for row in runs:
        row["signature"] = behaviour_signature(row)
    pools: dict[tuple, list[dict]] = defaultdict(list)
    for row in runs:
        pools[row["implementation"], row["strategy"], row["seed"]].append(row)

    curve = []
    full_pool = {}
    auc = {}
    for implementation in P["implementations"]:
        boundary = pools[implementation, "boundary", None]
        uniform_keys = sorted(k for k in pools if k[0] == implementation and k[1] == "uniform")
        full_pool[implementation] = {
            "boundary_cases": len(boundary),
            "boundary_violations": sum(x["signature"] is not None for x in boundary),
            "boundary_unique_signatures": len({x["signature"] for x in boundary if x["signature"]}),
            "uniform": [
                {
                    "seed": k[2],
                    "cases": len(pools[k]),
                    "violations": sum(x["signature"] is not None for x in pools[k]),
                    "unique_signatures": len({x["signature"] for x in pools[k] if x["signature"]}),
                }
                for k in uniform_keys
            ],
        }
        for strategy in ("boundary", "uniform"):
            means = []
            for budget in cfg["budgets"]:
                sig_counts, violations, detected = [], [], []
                for rep in range(cfg["resamples"]):
                    if strategy == "boundary":
                        pool = boundary
                    else:
                        pool = pools[uniform_keys[rep % len(uniform_keys)]]
                    if budget > len(pool):
                        raise ValueError(f"Budget {budget} exceeds pool {len(pool)}")
                    rng = random.Random(f"{cfg['seed']}|{implementation}|{strategy}|{budget}|{rep}")
                    sample = rng.sample(pool, budget)
                    sigs = {x["signature"] for x in sample if x["signature"]}
                    v = sum(x["signature"] is not None for x in sample)
                    sig_counts.append(len(sigs))
                    violations.append(v)
                    detected.append(1 if v else 0)
                row = {
                    "implementation": implementation,
                    "strategy": strategy,
                    "budget": budget,
                    "resamples": cfg["resamples"],
                    "detect_any_rate": statistics.mean(detected),
                    "violations_mean": statistics.mean(violations),
                    "violations_p05": _quantile(violations, 0.05),
                    "violations_p95": _quantile(violations, 0.95),
                    "unique_signatures_mean": statistics.mean(sig_counts),
                    "unique_signatures_p05": _quantile(sig_counts, 0.05),
                    "unique_signatures_p50": _quantile(sig_counts, 0.50),
                    "unique_signatures_p95": _quantile(sig_counts, 0.95),
                }
                curve.append(row)
                means.append((budget, row["unique_signatures_mean"]))
            area = 0.0
            for (x0, y0), (x1, y1) in zip(means, means[1:]):
                area += (x1 - x0) * (y0 + y1) / 2
            max_x = means[-1][0] - means[0][0]
            auc[f"{implementation}|{strategy}"] = area / max_x if max_x else means[0][1]

    result = {
        "design": cfg,
        "signature_definition": {
            "included": ["profile", "transition kind and magnitude", "anchor offset", "contract reasons", "first mismatch type/delta/ordinal"],
            "excluded": cfg["signature_excludes"],
            "claim_boundary": "Signatures are deterministic behavioural equivalence classes, not independently confirmed root causes or defect counts.",
        },
        "full_pool": full_pool,
        "budget_averaged_unique_signatures": auc,
        "normalized_auc_unique_signatures": auc,
        "curve": curve,
    }
    dump(out / "signature-budget.json", result)
    return result


def _minimize_violation(row: dict) -> dict:
    zone = TZif(ROOT / "data/tzdb" / row["tzdb"] / row["zone"])
    contract = PROFILES[row["profile"]]
    target_reasons = tuple(row["qualification"]["reasons"])
    trace = row["trace"]
    best = trace
    # An execution error is observed only after the last attempted step;
    # do not pretend a shorter prefix reproduces it.
    if not row["error"]:
        for n in range(1, len(trace) + 1):
            q = qualify(zone, contract, row["start"], trace[:n], None)
            if q["status"] == "VIOLATION" and set(target_reasons).intersection(q["reasons"]):
                best = trace[:n]
                break
    original_bytes = len(json.dumps(trace, sort_keys=True, separators=(",", ":")).encode())
    minimized_bytes = len(json.dumps(best, sort_keys=True, separators=(",", ":")).encode())
    return {
        "kind": "blocked_trace",
        "study": row["study"],
        "case_id": row["case_id"],
        "implementation": row["implementation"],
        "implementation_source_sha256": implementation_source_hash(row["implementation"]),
        "tzdb": row["tzdb"],
        "zone_file_sha256": file_hash(row["tzdb"], row["zone"]),
        "zone": row["zone"],
        "profile": row["profile"],
        "start": row["start"],
        "error": row["error"],
        "verdict": row["qualification"]["status"],
        "reasons": row["qualification"]["reasons"],
        "original_events": len(trace),
        "minimized_events": len(best),
        "original_bytes": original_bytes,
        "minimized_bytes": minimized_bytes,
        "trace": best,
        "prefix_of_executed_trace": best == trace[:len(best)],
    }


def minimized_witnesses(out: Path) -> dict:
    """Reduce one representative witness per decision-relevant behaviour."""
    datasets = []
    for study, filename in (
        ("current-release", "current-release-holdout.json"),
        ("current-tzdb", "current-tzdb-holdout.json"),
        ("release-series", "rule-release-series.json"),
    ):
        data = json.loads((out / filename).read_text())
        for row in data["runs"]:
            row = dict(row)
            row["study"] = study
            datasets.append(row)

    selected: dict[tuple, dict] = {}
    for row in datasets:
        if row["qualification"]["status"] != "VIOLATION":
            continue
        signature = behaviour_signature({
            **row,
            "kind": row.get("kind", "ordinary"),
            "transition_delta": row.get("transition_delta", 0),
            "anchor_offset": row.get("anchor_offset", 0),
        })
        key = (row["study"], row["implementation"], signature)
        selected.setdefault(key, _minimize_violation(row))

    # Accepted rule-data effects need a paired witness. Select one per release
    # pair/implementation and truncate at the first changed occurrence.
    paired = []
    for filename, study in (("current-tzdb-holdout.json", "current-tzdb"), ("rule-release-series.json", "release-series")):
        data = json.loads((out / filename).read_text())
        runs = data["runs"]
        if study == "current-tzdb":
            groups = defaultdict(dict)
            for r in runs:
                groups[r["case_id"], r["implementation"]][r["tzdb"]] = r
            version_for = lambda rmap: sorted(rmap)
            source_for = lambda _rmap: "IANA 2026a/2026b source-named holdout"
            pair_for = lambda versions, sample: f"{versions[0]}->{versions[1]}:{sample['zone']}"
        else:
            groups = defaultdict(dict)
            for r in runs:
                groups[r["case_id"], r["implementation"]][r["tzdb"]] = r
            version_for = lambda rmap: [next(iter(rmap.values()))["pair_id"].split(":",1)[0].split("->")[0], next(iter(rmap.values()))["pair_id"].split(":",1)[0].split("->")[1]]
            source_for = lambda rmap: next(iter(rmap.values()))["source"]
            pair_for = lambda versions, sample: sample["pair_id"]
        seen = set()
        for (case_id, implementation), rmap in sorted(groups.items()):
            versions = version_for(rmap)
            if len(versions) != 2 or any(v not in rmap for v in versions):
                continue
            a, b = rmap[versions[0]], rmap[versions[1]]
            if a["qualification"]["status"] != "PASS" or b["qualification"]["status"] != "PASS":
                continue
            av, bv = trace_values(a), trace_values(b)
            if av == bv:
                continue
            key = (study, pair_for(versions, a), implementation)
            if key in seen:
                continue
            seen.add(key)
            first = next(i for i, (x, y) in enumerate(zip(av, bv)) if x != y)
            n = first + 1
            old_trace, new_trace = a["trace"][:n], b["trace"][:n]
            full_bytes = len(json.dumps({"old": a["trace"], "new": b["trace"]}, sort_keys=True, separators=(",", ":")).encode())
            min_bytes = len(json.dumps({"old": old_trace, "new": new_trace}, sort_keys=True, separators=(",", ":")).encode())
            paired.append({
                "kind": "accepted_data_effect",
                "study": study,
                "pair_id": pair_for(versions, a),
                "source": source_for(rmap),
                "case_id": case_id,
                "implementation": implementation,
                "implementation_source_sha256": implementation_source_hash(implementation),
                "zone": a["zone"],
                "profile": a["profile"],
                "start": a["start"],
                "old_tzdb": versions[0],
                "new_tzdb": versions[1],
                "old_zone_file_sha256": file_hash(versions[0], a["zone"]),
                "new_zone_file_sha256": file_hash(versions[1], a["zone"]),
                "first_difference_ordinal": first,
                "original_events": len(a["trace"]) + len(b["trace"]),
                "minimized_events": len(old_trace) + len(new_trace),
                "original_bytes": full_bytes,
                "minimized_bytes": min_bytes,
                "old_trace": old_trace,
                "new_trace": new_trace,
                "prefixes_of_executed_traces": old_trace == a["trace"][:n] and new_trace == b["trace"][:n],
            })

    witnesses = list(selected.values()) + paired

    # Re-run every compact witness against the same pinned module and TZif bytes.
    # This validation checks faithful extraction; it is not counted as a new defect.
    replay_calls = 0
    for witness in witnesses:
        contract = PROFILES[witness["profile"]]
        if witness["kind"] == "blocked_trace":
            rerun = run_trace(
                witness["implementation"],
                load_zone(witness["tzdb"], witness["zone"]),
                contract,
                witness["start"],
            )
            replay_calls += rerun["calls"]
            witness["replayed_exactly"] = rerun["trace"][: len(witness["trace"])] == witness["trace"]
            q = qualify(
                TZif(ROOT / "data/tzdb" / witness["tzdb"] / witness["zone"]),
                contract,
                witness["start"],
                witness["trace"],
                witness["error"] if witness["error"] else None,
            )
            witness["minimized_prefix_qualification"] = q
            witness["decision_preserved"] = q["status"] == "VIOLATION" and bool(
                set(q["reasons"]).intersection(witness["reasons"])
            )
        else:
            old_run = run_trace(
                witness["implementation"],
                load_zone(witness["old_tzdb"], witness["zone"]),
                contract,
                witness["start"],
            )
            new_run = run_trace(
                witness["implementation"],
                load_zone(witness["new_tzdb"], witness["zone"]),
                contract,
                witness["start"],
            )
            replay_calls += old_run["calls"] + new_run["calls"]
            witness["replayed_exactly"] = (
                old_run["trace"][: len(witness["old_trace"])] == witness["old_trace"]
                and new_run["trace"][: len(witness["new_trace"])] == witness["new_trace"]
            )
            witness["decision_preserved"] = (
                witness["old_trace"] != witness["new_trace"]
                and witness["first_difference_ordinal"] < len(witness["old_trace"])
                and witness["first_difference_ordinal"] < len(witness["new_trace"])
            )

    event_reductions = [1 - w["minimized_events"] / w["original_events"] for w in witnesses if w["original_events"]]
    byte_reductions = [1 - w["minimized_bytes"] / w["original_bytes"] for w in witnesses if w["original_bytes"]]
    result = {
        "schema": "zoneshift.minimized-witnesses",
        "selection": "one blocked representative per study/implementation/behavioural signature and one accepted pair per release pair/implementation",
        "witnesses": witnesses,
        "summary": {
            "witnesses": len(witnesses),
            "blocked": sum(w["kind"] == "blocked_trace" for w in witnesses),
            "accepted_data_effects": sum(w["kind"] == "accepted_data_effect" for w in witnesses),
            "median_event_reduction": statistics.median(event_reductions) if event_reductions else 0,
            "median_byte_reduction": statistics.median(byte_reductions) if byte_reductions else 0,
            "all_preserve_real_executed_prefixes": all(
                w.get("prefix_of_executed_trace", w.get("prefixes_of_executed_traces", False))
                for w in witnesses
            ),
            "all_replayed_exactly": all(w["replayed_exactly"] for w in witnesses),
            "all_decisions_preserved": all(w["decision_preserved"] for w in witnesses),
            "replay_validation_api_calls": replay_calls,
            "interpretation": "Reduction minimizes evidence prefixes, not semantic inputs or root causes; an execution error is retained at its observed full prefix.",
        },
    }
    dump(out / "minimized-witnesses.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    release = release_series(args.output)
    conversion_validation = release_series_conversion_validation(args.output)
    signatures = signature_budget(args.output)
    minimized = minimized_witnesses(args.output)
    aggregate = {
        "release_series": release,
        "release_series_conversion_validation": conversion_validation,
        "signature_budget": {
            "full_pool": signatures["full_pool"],
            "budget_averaged_unique_signatures": signatures["budget_averaged_unique_signatures"],
        },
        "minimized_witnesses": minimized["summary"],
    }
    dump(args.output / "release-analysis.json", aggregate)
    print(json.dumps(aggregate, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
