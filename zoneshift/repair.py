"""Local policy-aware wall-clock adapter used in the downstream replay.

The adapter is deliberately small and independent of the TZif reference
checker.  It enumerates civil labels and relies on a pinned ``ZoneInfo`` object
for round-trip validation and gap/fold resolution.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .contracts import Contract


def _resolve_label(label: datetime, zone, contract: Contract) -> list[datetime]:
    resolved: dict[float, datetime] = {}
    roundtrips: dict[float, datetime] = {}
    for fold in (0, 1):
        candidate = label.replace(tzinfo=zone, fold=fold)
        roundtrip = datetime.fromtimestamp(candidate.timestamp(), zone)
        roundtrips[candidate.timestamp()] = roundtrip
        if roundtrip.replace(tzinfo=None) == label:
            resolved[candidate.timestamp()] = roundtrip

    if resolved:
        timestamps = sorted(resolved)
        if contract.fold == "first":
            timestamps = timestamps[:1]
        elif contract.fold == "second":
            timestamps = timestamps[-1:]
        elif contract.fold != "both":
            raise ValueError("Adapter intervention requires explicit fold intent")
        return [resolved[timestamp] for timestamp in timestamps]

    if contract.gap == "skip":
        return []
    if contract.gap not in {"shift_forward", "shift_backward"}:
        raise ValueError("Adapter intervention requires explicit gap intent")

    deltas = [
        (roundtrip.replace(tzinfo=None) - label, timestamp, roundtrip)
        for timestamp, roundtrip in roundtrips.items()
    ]
    if contract.gap == "shift_forward":
        candidates = [item for item in deltas if item[0] > timedelta(0)]
        if not candidates:
            raise ValueError("No forward gap projection supplied by ZoneInfo")
        return [min(candidates, key=lambda item: item[0])[2]]

    candidates = [item for item in deltas if item[0] < timedelta(0)]
    if not candidates:
        raise ValueError("No backward gap projection supplied by ZoneInfo")
    return [max(candidates, key=lambda item: item[0])[2]]


def wall_next(previous: datetime, contract: Contract) -> datetime:
    """Return the next occurrence under an explicit finite civil-time policy."""

    if previous.tzinfo is None:
        raise ValueError("Aware, pinned-zone datetime required")
    if not contract.complete:
        raise ValueError("Adapter intervention requires explicit gap/fold intent")

    start = previous.timestamp()
    zone = previous.tzinfo
    candidates: list[datetime] = []
    reached: int | None = None

    for step in range(64):
        day = previous.date() + timedelta(days=step - 1)
        if day.weekday() in contract.weekdays:
            for hour in contract.hours:
                for minute in contract.minutes:
                    label = datetime(day.year, day.month, day.day, hour, minute)
                    candidates.extend(
                        occurrence
                        for occurrence in _resolve_label(label, zone, contract)
                        if occurrence.timestamp() > start
                    )
        if candidates and reached is None:
            reached = step
        if reached is not None and step >= reached + 2:
            return min(candidates, key=lambda occurrence: occurrence.timestamp())

    raise ValueError("No occurrence in bounded 64-day adapter horizon")
