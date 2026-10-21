"""Small real requalification fixtures; stop before optional native execution."""
import json
from pathlib import Path
import shutil
import sys

import pytest

from scripts import run_native_comparison as runner
from scripts.run_policy_attribution import upgrade_sufficiency_study
from zoneshift.contracts import Contract, policy_completion_frontier, qualify
from zoneshift.profiles import PROFILES
from zoneshift.tzif import TZif

ARTIFACT = Path(__file__).resolve().parents[1]


class NativeBoundaryReached(RuntimeError):
    pass


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def snapshot(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes()
            for p in directory.rglob("*") if p.is_file()}


def history_fixture(tmp_path, monkeypatch, *, explicit=False):
    root = tmp_path / "artifact"
    source = root / ("selected-history" if explicit else "results")
    for version in ("2024a", "2025b"):
        destination = root / "data/tzdb" / version / "Etc/UTC"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ARTIFACT / "data/tzdb" / version / "Etc/UTC", destination)
    oracle = TZif(root / "data/tzdb/2024a/Etc/UTC")
    start = 1704153600 if explicit else 1704067200
    trace = [{"timestamp": start + 5 * 3600, "iso": "fixture", "fold": 0}]
    contract = PROFILES["five_am"]
    qualification = qualify(oracle, contract, start, trace)
    assert qualification["status"] == "PASS"
    row = {"case_id": "routing-fixture", "zone": "Etc/UTC", "year": 2024,
           "profile": "five_am", "start": start, "trace": trace, "error": None,
           "calls": 1, "qualification": qualification, "tzdb": "2024a"}
    matrix = {"runs": [dict(row, implementation=code, tzdb=data)
              for code in ("aps-3.11.0", "aps-3.11.2")
              for data in ("2024a", "2025b")]}
    incomplete = Contract((5,), (0,))
    frontier = policy_completion_frontier(oracle, incomplete, start, trace)
    frontier_row = dict(row, implementation="aps-3.11.2", kind="ordinary_fixture",
                        contract=incomplete.to_dict(), frontier=frontier)
    write_json(source / "policy-frontiers.json", {"summary": {}, "runs": [frontier_row]})
    write_json(source / "version-data-matrix.json", matrix)
    write_json(source / "design.json", {"case_specification": [row]})
    baseline_rows = [dict(row, implementation=implementation, strategy="boundary", seed=None)
                     for implementation in ("aps-3.11.2", "croniter-1.3.10", "croniter-2.0.1")]
    (source / "runs.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in baseline_rows), encoding="utf-8")
    write_json(source / "released-sentry.json", {"runs": []})
    if explicit:
        # Any lingering ROOT/results reader must fail, not accidentally pass.
        write_json(root / "results/design.json", {"wrong-source": True})
        write_json(root / "results/policy-frontiers.json", {"wrong-source": True})
        (root / "results/runs.jsonl").write_text("not-json\n", encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", root)
    return root, source, row


def stop_at_native_boundary(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "cronsim_class", lambda: None)

    def stop(implementation, zone, contract, start, *, count):
        calls.append((implementation, zone.key, contract, start, count))
        raise NativeBoundaryReached("native-call-boundary")

    monkeypatch.setattr(runner, "run_trace", stop)
    return calls


@pytest.mark.parametrize("entry", ["recommended", "defaults", "explicit_input"])
def test_new_output_requalifies_then_reaches_native_boundary(tmp_path, monkeypatch, entry):
    root, source, row = history_fixture(tmp_path, monkeypatch, explicit=entry == "explicit_input")
    before = snapshot(source)
    output = root / "results/native-comparison-new" if entry != "explicit_input" else root / "fresh/native"
    args = ["run_native_comparison.py"]
    if entry != "defaults":
        args += ["--output", str(output)]
    if entry == "explicit_input":
        args += ["--input-results", str(source)]
    calls = stop_at_native_boundary(monkeypatch)
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(NativeBoundaryReached, match="native-call-boundary"):
        runner.main()
    assert calls == [("cronsim-2.6", "Etc/UTC", PROFILES["five_am"], row["start"], 8)]
    after = snapshot(source)
    if output.is_relative_to(source):
        after = {k: v for k, v in after.items() if not k.startswith("native-comparison-new/")}
    assert after == before
    verification = json.loads((output / "policy-model-requalification.json").read_text())
    assert verification["frontier_traces_requalified"] == 1
    assert verification["matrix_traces_requalified"] == 4
    assert verification["main_traces_requalified"] == 3
    assert verification["matrix_qualification_changes"] == []
    assert verification["main_qualification_changes"] == []
    assert verification["certificates_recomputed"] == 1
    assert verification["new_scheduler_calls"] == 0
    assert {p.name for p in output.iterdir()} == {
        "policy-frontiers.json", "upgrade-sufficiency.json",
        "policy-attribution-summary.json", "policy-model-requalification.json"}
    recomputed = json.loads((output / "policy-frontiers.json").read_text())
    assert len(recomputed["runs"][0]["frontier"]["passing_completions"]) == 12
    assert recomputed["summary"]["execution_basis"].startswith("Retained 1 executed traces;")


def test_explicit_input_smoke_reaches_boundary_without_requalifying(tmp_path, monkeypatch):
    root, source, row = history_fixture(tmp_path, monkeypatch, explicit=True)
    before = snapshot(source)
    output = root / "smoke-new"
    calls = stop_at_native_boundary(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["runner", "--input-results", str(source),
                                    "--output", str(output), "--limit", "1"])
    with pytest.raises(NativeBoundaryReached):
        runner.main()
    assert len(calls) == 1 and calls[0][3] == row["start"]
    assert snapshot(source) == before
    assert list(output.iterdir()) == []


def test_requalify_only_uses_history_without_optional_dependency_or_native_result(tmp_path, monkeypatch):
    root, source, _ = history_fixture(tmp_path, monkeypatch, explicit=True)
    before = snapshot(source)
    output = root / "requalification-new"

    def forbidden(*args, **kwargs):
        raise AssertionError("No optional dependency or scheduler calls")

    monkeypatch.setattr(runner, "cronsim_class", forbidden)
    monkeypatch.setattr(runner, "run_trace", forbidden)
    monkeypatch.setattr(sys, "argv", ["runner", "--input-results", str(source),
                                    "--output", str(output), "--requalify-only"])
    runner.main()
    assert snapshot(source) == before
    assert not (output / "native-cronsim-comparison.json").exists()
    assert json.loads((output / "policy-model-requalification.json").read_text())["new_scheduler_calls"] == 0


def test_requalify_helper_default_reads_retained_results(tmp_path, monkeypatch):
    root, source, _ = history_fixture(tmp_path, monkeypatch)
    before = snapshot(source)
    output = root / "helper-new"
    output.mkdir()
    verification, frontiers = runner.requalify(output)
    assert verification["certificates_recomputed"] == 1 and len(frontiers) == 1
    assert snapshot(source) == before
    assert not (output / "version-data-matrix.json").exists()


def test_missing_optional_dependency_does_not_create_output(tmp_path, monkeypatch):
    root, source, _ = history_fixture(tmp_path, monkeypatch)
    before = snapshot(source)
    output = root / "dependency-unavailable-new"

    def unavailable():
        raise ModuleNotFoundError("fixture: optional comparator is absent")

    monkeypatch.setattr(runner, "cronsim_class", unavailable)
    monkeypatch.setattr(sys, "argv", ["runner", "--output", str(output)])
    with pytest.raises(ModuleNotFoundError, match="optional comparator"):
        runner.main()
    assert not output.exists() and snapshot(source) == before


@pytest.mark.parametrize("target", ["history", "default", "explicit"])
def test_existing_output_is_rejected_before_dependency_or_writes(tmp_path, monkeypatch, target):
    root, source, _ = history_fixture(tmp_path, monkeypatch)
    output = source if target == "history" else root / ("results/native-comparison-new" if target == "default" else "user-output")
    output.mkdir(parents=True, exist_ok=True)
    (output / "user-owned.txt").write_text("keep exactly", encoding="utf-8")
    before = snapshot(root)

    def forbidden(*args, **kwargs):
        raise AssertionError("Output rejection must precede optional dependency checks")

    monkeypatch.setattr(runner, "cronsim_class", forbidden)
    monkeypatch.setattr(sys, "argv", ["runner"] + ([] if target == "default" else ["--output", str(output)]))
    with pytest.raises(FileExistsError):
        runner.main()
    assert snapshot(root) == before


@pytest.mark.parametrize("dataset", ["version-data-matrix.json", "runs.jsonl"])
def test_changed_historical_qualification_still_blocks_native_execution(tmp_path, monkeypatch, dataset):
    root, source, _ = history_fixture(tmp_path, monkeypatch)
    path = source / dataset
    if dataset.endswith(".jsonl"):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["qualification"] = {"status": "VIOLATION", "reasons": [], "missing": []}
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    else:
        data = json.loads(path.read_text())
        data["runs"][0]["qualification"]["status"] = "VIOLATION"
        write_json(path, data)
    before = snapshot(source)
    monkeypatch.setattr(runner, "run_trace", lambda *a, **k: pytest.fail("Native call must remain blocked"))
    monkeypatch.setattr(sys, "argv", ["runner", "--output", str(root / "blocked-new"), "--requalify-only"])
    with pytest.raises(RuntimeError, match="Retained (matrix|benchmark) changed"):
        runner.main()
    assert snapshot(source) == before


def test_sufficiency_legacy_output_as_input_default_stays_compatible(tmp_path, monkeypatch):
    _, source, _ = history_fixture(tmp_path, monkeypatch)
    summary = upgrade_sufficiency_study(source)
    assert summary["certificates"] == 1
    assert json.loads((source / "upgrade-sufficiency.json").read_text())["summary"] == summary


@pytest.mark.parametrize('limit', ['0', '-1'])
def test_nonpositive_smoke_limit_fails_before_output_or_native_setup(tmp_path, monkeypatch, limit):
    root,source,_=history_fixture(tmp_path,monkeypatch)
    before=snapshot(root)
    monkeypatch.setattr(runner,'cronsim_class',lambda: pytest.fail('bad limit must fail before dependency setup'))
    monkeypatch.setattr(sys,'argv',['runner','--limit',limit])
    with pytest.raises(SystemExit) as error:runner.main()
    assert error.value.code==2
    assert snapshot(root)==before
