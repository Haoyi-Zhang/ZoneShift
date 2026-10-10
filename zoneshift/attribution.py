"""Verdict-level attribution for a two-coordinate upgrade square."""
from __future__ import annotations

from collections.abc import Mapping

CellName = str

_REQUIRED = (
    "old_code_old_data",
    "new_code_old_data",
    "old_code_new_data",
    "new_code_new_data",
)


def minimal_sufficient_changes(statuses: Mapping[CellName, str]) -> list[list[str]]:
    """Return inclusion-minimal coordinate changes that reach PASS.

    The baseline is ``old_code_old_data``.  The result is descriptive for the
    measured case and does not claim general causal identification.
    """

    if set(_REQUIRED) - set(statuses):
        missing = sorted(set(_REQUIRED) - set(statuses))
        raise ValueError(f"Missing upgrade cells: {missing}")

    candidates: list[frozenset[str]] = []
    if statuses["old_code_old_data"] == "PASS":
        candidates.append(frozenset())
    if statuses["new_code_old_data"] == "PASS":
        candidates.append(frozenset({"code"}))
    if statuses["old_code_new_data"] == "PASS":
        candidates.append(frozenset({"data"}))
    if statuses["new_code_new_data"] == "PASS":
        candidates.append(frozenset({"code", "data"}))

    minimal = [
        candidate
        for candidate in candidates
        if not any(other < candidate for other in candidates)
    ]
    return [sorted(candidate) for candidate in sorted(minimal, key=lambda item: (len(item), sorted(item)))]


def classify_upgrade_square(
    statuses: Mapping[CellName, str],
    traces: Mapping[CellName, tuple[float, ...]] | None = None,
) -> dict[str, object]:
    """Build a promotion certificate with a sequence-inequality-presence flag.

    ``noncommutative_observation`` compares whether sequence differences exist
    along parallel edges, not their magnitudes or their qualification. Cell
    statuses and minimal passing changes remain separate verdict information.
    """

    minimal = minimal_sufficient_changes(statuses)
    baseline = statuses["old_code_old_data"]
    target = statuses["new_code_new_data"]

    if baseline == "PASS" and target == "PASS":
        decision = "baseline_already_passes"
    elif baseline != "PASS" and target == "PASS":
        normalized = {tuple(changes) for changes in minimal}
        if normalized == {("code",)}:
            decision = "code_change_sufficient"
        elif normalized == {("data",)}:
            decision = "data_change_sufficient"
        elif normalized == {("code",), ("data",)}:
            decision = "either_single_change_sufficient"
        elif normalized == {("code", "data")}:
            decision = "both_changes_required"
        else:
            decision = "passing_target_with_mixed_sufficiency"
    elif baseline == "PASS" and target != "PASS":
        decision = "promotion_regression"
    else:
        decision = "no_passing_target"

    result: dict[str, object] = {
        "baseline_status": baseline,
        "target_status": target,
        "minimal_sufficient_changes": minimal,
        "decision": decision,
    }

    if traces is not None:
        if set(_REQUIRED) - set(traces):
            raise ValueError("Trace map must contain the complete 2x2 square")
        code_diff_old_data = traces["old_code_old_data"] != traces["new_code_old_data"]
        code_diff_new_data = traces["old_code_new_data"] != traces["new_code_new_data"]
        data_diff_old_code = traces["old_code_old_data"] != traces["old_code_new_data"]
        data_diff_new_code = traces["new_code_old_data"] != traces["new_code_new_data"]
        result.update(
            {
                "code_effect_by_data": {
                    "old_data": code_diff_old_data,
                    "new_data": code_diff_new_data,
                },
                "data_effect_by_code": {
                    "old_code": data_diff_old_code,
                    "new_code": data_diff_new_code,
                },
                "noncommutative_observation": (
                    code_diff_old_data != code_diff_new_data
                    or data_diff_old_code != data_diff_new_code
                ),
            }
        )
    return result
