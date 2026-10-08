from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from zoneshift import adapters, execution
from zoneshift.__main__ import _execute_cell, _start, main
from zoneshift.attribution import classify_upgrade_square, minimal_sufficient_changes
from zoneshift.contracts import Contract
from zoneshift.execution import load_zone, run_trace

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Contract((5,), (0,), gap="skip", fold="both")


def test_adapter_version_guards_and_sentry_branch():
    with pytest.raises(ValueError):
        adapters.aps_class("0")
    with pytest.raises(ValueError):
        adapters.croniter_class("0")

    zone = load_zone("2024a", "Etc/UTC")
    reference = datetime(2024, 1, 1, tzinfo=zone)
    assert adapters.sentry_next(reference, "0 5 * * *", "1.3.10").hour == 5


@pytest.mark.parametrize("implementation", ["croniter-2.0.1", "sentry-adapter", "sentry-24.3.0"])
def test_execution_branches_produce_bounded_traces(implementation):
    zone = load_zone("2024a", "Etc/UTC")
    start = datetime(2024, 1, 1, tzinfo=zone).timestamp()
    result = run_trace(implementation, zone, CONTRACT, start, count=2)
    assert result["error"] is None
    assert result["calls"] == 2
    assert [event["iso"][11:16] for event in result["trace"]] == ["05:00", "05:00"]


def test_execution_input_guards():
    zone = load_zone("2024a", "Etc/UTC")
    start = datetime(2024, 1, 1, tzinfo=zone).timestamp()
    with pytest.raises(ValueError, match="Unbounded"):
        run_trace("aps-3.11.2", zone, CONTRACT, start, count=0)
    with pytest.raises(ValueError, match="unknown"):
        run_trace("unknown", zone, CONTRACT, start, count=1)


class _Trigger:
    def __init__(self, outcome):
        self.outcome = outcome

    def get_next_fire_time(self, previous, now):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        if self.outcome == "timeout":
            execution._alarm(0, None)
        return self.outcome


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (None, "unexpected_end"),
        (RuntimeError("boom"), "RuntimeError: boom"),
        ("timeout", "timeout"),
    ],
)
def test_execution_error_capture(monkeypatch, outcome, expected):
    zone = load_zone("2024a", "Etc/UTC")
    start = datetime(2024, 1, 1, tzinfo=zone).timestamp()

    def fake_class(version):
        return lambda **kwargs: _Trigger(outcome)

    monkeypatch.setattr(execution, "aps_class", fake_class)
    step = execution._make_step("aps-3.11.2", zone, CONTRACT, start)
    result = execution._collect_steps(step, start, count=1)
    assert result["error"] == expected
    assert result["calls"] == 1


def test_cli_start_and_manifest_guards():
    zone = load_zone("2024a", "Etc/UTC")
    with pytest.raises(ValueError, match="naive"):
        _start({"start": "2024-01-01T00:00:00+00:00"}, zone)
    with pytest.raises(ValueError, match="start_fold"):
        _start({"start": "2024-01-01T00:00:00", "start_fold": 2}, zone)
    with pytest.raises(ValueError, match="pinned manifest"):
        _execute_cell(
            "aps-3.11.2",
            "missing",
            "Etc/UTC",
            {"start": "2024-01-01T00:00:00"},
            CONTRACT,
            1,
        )
    with pytest.raises(ValueError, match="nonexistent"):
        _execute_cell(
            "aps-3.11.2",
            "2024a",
            "America/New_York",
            {"start": "2024-03-10T02:30:00"},
            Contract((2,), (30,), gap="skip", fold="both"),
            1,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "other"},
        {
            "mode": "single",
            "implementation": "aps-3.11.2",
            "tzdb": "2024a",
            "zone": "Etc/UTC",
            "start": "2024-01-01T00:00:00",
            "contract": {"hours": [5], "minutes": [0], "gap": "skip", "fold": "both"},
            "extra": True,
        },
        {
            "mode": "upgrade",
            "old_implementation": "aps-3.11.0",
            "new_implementation": "aps-3.11.2",
            "old_tzdb": "2024a",
            "new_tzdb": "2025b",
            "zone": "America/Asuncion",
            "start": "2024-01-01T00:00:00",
            "contract": {"hours": [0], "minutes": [0], "gap": "skip", "fold": "both"},
            "extra": True,
        },
    ],
)
def test_cli_configuration_errors(tmp_path, capsys, payload):
    config = tmp_path / "bad.json"
    config.write_text(json.dumps(payload))
    assert main([str(config)]) == 3
    captured = capsys.readouterr()
    assert "CONFIGURATION_ERROR" in captured.err


def test_upgrade_attribution_guards_and_decisions():
    with pytest.raises(ValueError, match="Missing upgrade cells"):
        minimal_sufficient_changes({})

    baseline = {
        "old_code_old_data": "PASS",
        "new_code_old_data": "PASS",
        "old_code_new_data": "PASS",
        "new_code_new_data": "PASS",
    }
    assert classify_upgrade_square(baseline)["decision"] == "baseline_already_passes"

    data_only = {
        "old_code_old_data": "VIOLATION",
        "new_code_old_data": "VIOLATION",
        "old_code_new_data": "PASS",
        "new_code_new_data": "PASS",
    }
    assert classify_upgrade_square(data_only)["decision"] == "data_change_sufficient"

    either = {
        "old_code_old_data": "VIOLATION",
        "new_code_old_data": "PASS",
        "old_code_new_data": "PASS",
        "new_code_new_data": "PASS",
    }
    traces = {
        "old_code_old_data": (1.0,),
        "new_code_old_data": (2.0,),
        "old_code_new_data": (1.0,),
        "new_code_new_data": (1.0,),
    }
    cert = classify_upgrade_square(either, traces)
    assert cert["decision"] == "either_single_change_sufficient"
    assert cert["noncommutative_observation"] is True

    regression = dict(baseline)
    regression["new_code_new_data"] = "VIOLATION"
    assert classify_upgrade_square(regression)["decision"] == "promotion_regression"

    no_target = dict(data_only)
    no_target["old_code_new_data"] = "VIOLATION"
    no_target["new_code_new_data"] = "VIOLATION"
    assert classify_upgrade_square(no_target)["decision"] == "no_passing_target"

    with pytest.raises(ValueError, match="complete"):
        classify_upgrade_square(either, {"old_code_old_data": (1.0,)})
