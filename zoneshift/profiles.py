"""Named complete contracts shared by every experiment driver."""
from __future__ import annotations

from .contracts import Contract

PROFILES: dict[str, Contract] = {
    "midnight": Contract((0,), (0,), gap="skip", fold="both"),
    "five_am": Contract((5,), (0,), gap="skip", fold="both"),
    "hourly_30": Contract(tuple(range(24)), (30,), gap="skip", fold="both"),
    "half_hourly": Contract(
        tuple(range(24)),
        (0, 30),
        gap="skip",
        fold="both",
    ),
}
