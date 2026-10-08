"""Bounded civil-time contracts, reference enumeration, and qualification.

The reference implementation intentionally supports a small recurrence subset.
It does not call any scheduler under test.  Policy is explicit: a missing local
label may be skipped or shifted across the gap, and a repeated label may select
the first branch, the second branch, or both.  Incomplete policies are evaluated
through a finite completion frontier rather than silently defaulted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

from .tzif import TZif

GapPolicy = Literal["skip", "shift_forward", "shift_backward", "unspecified"]
FoldPolicy = Literal["both", "first", "second", "unspecified"]

COMPLETE_GAP_POLICIES: tuple[GapPolicy, ...] = (
    "skip",
    "shift_forward",
    "shift_backward",
)
COMPLETE_FOLD_POLICIES: tuple[FoldPolicy, ...] = ("both", "first", "second")


@dataclass(frozen=True)
class Contract:
    """A finite wall-clock recurrence contract.

    ``hours``, ``minutes``, and ``weekdays`` describe the supported recurrence
    subset.  ``gap`` and ``fold`` are independent semantic choices.  The
    ``unspecified`` value is permitted so that the checker can return a policy
    completion frontier rather than inventing intent.
    """

    hours: tuple[int, ...]
    minutes: tuple[int, ...]
    weekdays: tuple[int, ...] = tuple(range(7))  # Python weekday: Monday=0
    gap: GapPolicy = "unspecified"
    fold: FoldPolicy = "unspecified"
    recurrence: str = "wall"

    def __post_init__(self) -> None:
        for values, upper in (
            (self.hours, 24),
            (self.minutes, 60),
            (self.weekdays, 7),
        ):
            valid = (
                bool(values)
                and list(values) == sorted(set(values))
                and all(type(value) is int and 0 <= value < upper for value in values)
            )
            if not valid:
                raise ValueError("Nonempty sorted distinct integer fields required")
        if self.gap not in {*COMPLETE_GAP_POLICIES, "unspecified"}:
            raise ValueError(f"Unsupported gap policy: {self.gap}")
        if self.fold not in {*COMPLETE_FOLD_POLICIES, "unspecified"}:
            raise ValueError(f"Unsupported fold policy: {self.fold}")
        if self.recurrence != "wall":
            raise ValueError("Elapsed intervals must use the separate elapsed reference")

    @property
    def complete(self) -> bool:
        return self.gap != "unspecified" and self.fold != "unspecified"

    def completions(self) -> tuple["Contract", ...]:
        gaps = COMPLETE_GAP_POLICIES if self.gap == "unspecified" else (self.gap,)
        folds = COMPLETE_FOLD_POLICIES if self.fold == "unspecified" else (self.fold,)
        return tuple(replace(self, gap=gap, fold=fold) for gap in gaps for fold in folds)

    def matches(self, wall: datetime) -> bool:
        return (
            wall.hour in self.hours
            and wall.minute in self.minutes
            and wall.weekday() in self.weekdays
            and wall.second == 0
            and wall.microsecond == 0
        )

    def aps_kwargs(self) -> dict[str, object]:
        return {
            "hour": ",".join(map(str, self.hours)),
            "minute": ",".join(map(str, self.minutes)),
            "day_of_week": ",".join(map(str, self.weekdays)),
            "second": 0,
        }

    def cron(self) -> str:
        # Cron uses Sunday=0; Python uses Monday=0.
        days = ",".join(map(str, sorted({(value + 1) % 7 for value in self.weekdays})))
        minutes = ",".join(map(str, self.minutes))
        hours = ",".join(map(str, self.hours))
        return f"{minutes} {hours} * * {days}"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def reference(
    zone: TZif,
    contract: Contract,
    start: float,
    count: int = 8,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Enumerate a bounded prefix without invoking a scheduler under test.

    The second return value records every missing civil label encountered and
    both deterministic projection candidates.  When a complete gap policy
    selects a projection, the projected instant is also included in ``events``.
    """

    if not 1 <= count <= 1024:
        raise ValueError("Count outside bounded reference domain")

    first_day = zone.wall(start).date() - timedelta(days=1)
    events: list[dict[str, object]] = []
    gaps: list[dict[str, object]] = []
    reached: int | None = None

    for day_index in range(64):
        day = first_day + timedelta(days=day_index)
        if day.weekday() in contract.weekdays:
            for hour in contract.hours:
                for minute in contract.minutes:
                    label = datetime(day.year, day.month, day.day, hour, minute)
                    candidates = zone.resolve(label)
                    if candidates:
                        for branch, timestamp in enumerate(candidates):
                            if timestamp > start:
                                events.append(
                                    {
                                        "timestamp": timestamp,
                                        "label": label.isoformat(),
                                        "multiplicity": len(candidates),
                                        "branch": branch,
                                        "origin": "valid_label",
                                    }
                                )
                    else:
                        projections = zone.gap_projection_map(label)
                        if projections:
                            gap = {"label": label.isoformat(), **projections}
                            gaps.append(gap)
                            selected = projections.get(contract.gap)
                            if selected is not None and selected > start:
                                events.append(
                                    {
                                        "timestamp": selected,
                                        "label": label.isoformat(),
                                        "multiplicity": 1,
                                        "branch": 0,
                                        "origin": contract.gap,
                                    }
                                )

        if reached is None and len(events) >= count:
            reached = day_index
        # Two extra local dates plus the one-day offset bound are sufficient to
        # establish UTC order for this limited recurrence domain.
        if reached is not None and day_index >= reached + 2:
            break
    else:
        raise ValueError("Reference horizon exhausted")

    events.sort(key=lambda event: (float(event["timestamp"]), str(event["label"])))
    unique_gaps = {gap["label"]: gap for gap in gaps}
    return events, [unique_gaps[key] for key in sorted(unique_gaps)]


def required(events: list[dict[str, object]], contract: Contract) -> list[float]:
    """Select required instants from a complete reference event sequence."""

    if contract.fold == "unspecified":
        raise ValueError("required() needs an explicit fold policy")

    result: list[float] = []
    for event in events:
        multiplicity = int(event["multiplicity"])
        branch = int(event["branch"])
        timestamp = float(event["timestamp"])
        if event.get("origin") != "valid_label" or multiplicity == 1:
            result.append(timestamp)
        elif contract.fold == "both":
            result.append(timestamp)
        elif contract.fold == "first" and branch == 0:
            result.append(timestamp)
        elif contract.fold == "second" and branch == multiplicity - 1:
            result.append(timestamp)
    return result


def _qualify_complete(
    zone: TZif,
    contract: Contract,
    start: float,
    trace: list[dict[str, object]],
    error: str | None = None,
) -> dict[str, object]:
    if not contract.complete:
        raise ValueError("Explicit gap and fold policies are required")

    values = [float(item["timestamp"]) for item in trace]
    reasons: list[str] = []
    if error:
        return {"status": "VIOLATION", "reasons": [error], "missing": []}
    if not values:
        return {"status": "VIOLATION", "reasons": ["empty_trace"], "missing": []}

    previous = start
    for timestamp in values:
        if timestamp <= previous:
            reasons.append("nonprogress")
            break
        previous = timestamp

    events, _ = reference(zone, contract, start, max(8, len(values)))
    expected: dict[float, list[dict[str, object]]] = {}
    for event in events:
        expected.setdefault(float(event["timestamp"]), []).append(event)

    observed = set(values)
    for timestamp in values:
        candidates = expected.get(timestamp)
        if not candidates:
            reasons.append("off_recurrence")
            continue
        valid_fold_events = [
            event
            for event in candidates
            if event.get("origin") == "valid_label" and int(event["multiplicity"]) > 1
        ]
        if valid_fold_events:
            permitted = False
            for event in valid_fold_events:
                branch = int(event["branch"])
                multiplicity = int(event["multiplicity"])
                if contract.fold == "both":
                    permitted = True
                elif contract.fold == "first" and branch == 0:
                    permitted = True
                elif contract.fold == "second" and branch == multiplicity - 1:
                    permitted = True
            if not permitted:
                reasons.append("forbidden_fold_branch")

    end = max(values)
    missing = [
        timestamp
        for timestamp in required(events, contract)
        if timestamp <= end and timestamp not in observed
    ]
    if missing:
        reasons.append("missing_required_occurrence")

    return {
        "status": "VIOLATION" if reasons else "PASS",
        "reasons": sorted(set(reasons)),
        "missing": missing[:8],
    }


def policy_completion_frontier(
    zone: TZif,
    contract: Contract,
    start: float,
    trace: list[dict[str, object]],
    error: str | None = None,
) -> dict[str, object]:
    """Return the finite set of complete policies consistent with a trace.

    The frontier is an actionable ambiguity certificate.  A trace is robustly
    passing only when every admissible completion passes, robustly violating
    only when every completion violates, and policy-sensitive otherwise.
    """

    rows: list[dict[str, object]] = []
    for completion in contract.completions():
        result = _qualify_complete(zone, completion, start, trace, error)
        rows.append(
            {
                "gap": completion.gap,
                "fold": completion.fold,
                "status": result["status"],
                "reasons": result["reasons"],
                "missing": result["missing"],
            }
        )

    passing = [
        {"gap": row["gap"], "fold": row["fold"]}
        for row in rows
        if row["status"] == "PASS"
    ]
    statuses = {str(row["status"]) for row in rows}
    if statuses == {"PASS"}:
        classification = "robust_pass"
    elif statuses == {"VIOLATION"}:
        classification = "robust_violation"
    else:
        classification = "policy_sensitive"

    return {
        "classification": classification,
        "completions": rows,
        "passing_completions": passing,
        "completion_count": len(rows),
    }


def qualify(
    zone: TZif,
    contract: Contract,
    start: float,
    trace: list[dict[str, object]],
    error: str | None = None,
) -> dict[str, object]:
    """Return PASS, VIOLATION, or UNDERSPECIFIED for a finite trace."""

    if contract.complete:
        return _qualify_complete(zone, contract, start, trace, error)

    frontier = policy_completion_frontier(zone, contract, start, trace, error)
    if frontier["classification"] == "robust_pass":
        return {
            "status": "PASS",
            "reasons": [],
            "missing": [],
            "policy_frontier": frontier,
        }
    if frontier["classification"] == "robust_violation":
        rows = frontier["completions"]
        reason_sets = [set(row["reasons"]) for row in rows]
        common = set.intersection(*reason_sets) if reason_sets else set()
        reasons = sorted(common) or ["policy_invariant_violation"]
        missing = sorted(
            {
                float(timestamp)
                for row in rows
                for timestamp in row.get("missing", [])
            }
        )[:8]
        return {
            "status": "VIOLATION",
            "reasons": reasons,
            "missing": missing,
            "policy_frontier": frontier,
        }
    return {
        "status": "UNDERSPECIFIED",
        "reasons": ["policy_completion_required"],
        "missing": [],
        "policy_frontier": frontier,
    }


def elapsed_reference(start: float, interval_seconds: int, count: int) -> list[float]:
    if interval_seconds <= 0 or not 1 <= count <= 1024:
        raise ValueError("Invalid elapsed interval/count")
    return [start + interval_seconds * index for index in range(1, count + 1)]
