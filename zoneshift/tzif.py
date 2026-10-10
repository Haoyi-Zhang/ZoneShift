"""Small, read-only reader for standard TZif transition formats (no zoneinfo calls).

A bounded reference component, not a general timezone implementation. Leap-aware
files remain unsupported. Common POSIX TZ footers (fixed offsets and M.m.w rules)
are expanded only through the declared 1970--2036 reference horizon.
"""
from __future__ import annotations
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import struct
from calendar import monthrange

EPOCH = datetime(1970, 1, 1)
MIN_TIME = 0
MAX_TIME = int((datetime(2037, 1, 1) - EPOCH).total_seconds())


def wall_seconds(wall: datetime) -> int:
    if wall.tzinfo is not None or wall.microsecond:
        raise ValueError('Reference labels must be naive whole-second datetimes')
    return int((wall - EPOCH).total_seconds())



def _posix_offset(text: str) -> int:
    """Return local-minus-UTC seconds from a POSIX TZ offset token."""
    m = re.fullmatch(r'(?P<sign>[+-]?)(?P<h>\d{1,3})(?::(?P<m>\d{1,2})(?::(?P<s>\d{1,2}))?)?', text)
    if not m:
        raise ValueError(f'Unsupported POSIX offset: {text}')
    seconds = int(m['h']) * 3600 + int(m['m'] or 0) * 60 + int(m['s'] or 0)
    # POSIX spells the amount added to local time to obtain UTC.
    return seconds if m['sign'] == '-' else -seconds


def _rule_seconds(text: str) -> tuple[int, int, int, int]:
    """Parse Mmonth.week.weekday[/time] into integer fields."""
    m = re.fullmatch(r'M(\d{1,2})\.(\d)\.(\d)(?:/([+-]?\d{1,3}(?::\d{1,2}(?::\d{1,2})?)?))?', text)
    if not m:
        raise ValueError(f'Unsupported POSIX transition rule: {text}')
    month, week, weekday = map(int, m.groups()[:3])
    if not (1 <= month <= 12 and 1 <= week <= 5 and 0 <= weekday <= 6):
        raise ValueError(f'Out-of-range POSIX transition rule: {text}')
    token = m.group(4) or '2'
    sign = -1 if token.startswith('-') else 1
    token = token.lstrip('+-')
    parts = [int(x) for x in token.split(':')]
    while len(parts) < 3:
        parts.append(0)
    seconds = sign * (parts[0] * 3600 + parts[1] * 60 + parts[2])
    return month, week, weekday, seconds


def _rule_local(year: int, rule: tuple[int, int, int, int]) -> datetime:
    month, week, weekday, seconds = rule
    first = datetime(year, month, 1)
    # Python Monday=0; POSIX Sunday=0.
    py_weekday = (weekday + 6) % 7
    day = 1 + (py_weekday - first.weekday()) % 7
    if week < 5:
        day += (week - 1) * 7
    else:
        day += ((monthrange(year, month)[1] - day) // 7) * 7
    return datetime(year, month, day) + timedelta(seconds=seconds)


@dataclass(frozen=True)
class Transition:
    utc: int
    before: int
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before


class TZif:
    def __init__(self, path: Path):
        self.path = Path(path)
        data = self.path.read_bytes()
        if len(data) < 44 or data[:4] != b'TZif':
            raise ValueError('Invalid TZif header')
        pos, width = 0, 4
        counts = struct.unpack_from('>6I', data, 20)
        if data[4:5] in (b'2', b'3', b'4'):
            gmt, std, leap, n, types, chars = counts
            pos = 44 + n*5 + types*6 + chars + leap*8 + std + gmt
            if data[pos:pos+4] != b'TZif':
                raise ValueError('Missing TZif 64-bit block')
            counts = struct.unpack_from('>6I', data, pos+20)
            width = 8
        gmt, std, leap, n, types, chars = counts
        if leap or not 1 <= types <= 256 or n > 100000:
            raise ValueError('Unsupported leap-aware or malformed TZif')
        pos += 44
        self.times = list(struct.unpack_from('>' + ('q' if width == 8 else 'i')*n, data, pos))
        pos += n*width
        self.indices = list(data[pos:pos+n]); pos += n
        self.types = [struct.unpack_from('>iBB', data, pos+6*i) for i in range(types)]
        pos += 6*types + chars + leap*(width+4) + std + gmt
        self.footer = data[pos:].strip(b'\n').decode('ascii')
        if self.times != sorted(set(self.times)) or any(i >= types for i in self.indices):
            raise ValueError('Invalid transition ordering/type index')
        if any(abs(t[0]) > 86400 for t in self.types):
            raise ValueError('Offsets beyond one day are out of scope')
        self.fixed_tail = None
        self.tail_initial = self.types[self.indices[-1]][0] if self.times else self.types[0][0]
        self.tail_transitions: list[Transition] = []
        abbr = r'(?:[A-Za-z]{3,}|<[^>]+>)'
        fixed = re.fullmatch(abbr + r'([+-]?\d{1,3}(?::\d{1,2}(?::\d{1,2})?)?)', self.footer)
        recurring = re.fullmatch(
            rf'(?P<std>{abbr})(?P<stdoff>[+-]?\d{{1,3}}(?::\d{{1,2}}(?::\d{{1,2}})?)?)'
            rf'(?P<dst>{abbr})(?P<dstoff>[+-]?\d{{1,3}}(?::\d{{1,2}}(?::\d{{1,2}})?)?)?,'
            rf'(?P<start>[^,]+),(?P<end>[^,]+)', self.footer)
        if fixed:
            self.fixed_tail = _posix_offset(fixed.group(1))
        elif recurring:
            std_offset = _posix_offset(recurring['stdoff'])
            dst_offset = (_posix_offset(recurring['dstoff'])
                          if recurring['dstoff'] else std_offset + 3600)
            start_rule = _rule_seconds(recurring['start'])
            end_rule = _rule_seconds(recurring['end'])
            last = self.times[-1] if self.times else MIN_TIME - 1
            initial, self.tail_transitions = _recurring_tail(
                std_offset, dst_offset, start_rule, end_rule, last)
            if not self.times:
                self.tail_initial = initial
        elif self.footer:
            raise ValueError(f'Unsupported dynamic POSIX TZif footer: {self.footer}')
        self.offsets = sorted({t[0] for t in self.types})
        if self.fixed_tail is not None:
            self.offsets = sorted(set(self.offsets + [self.fixed_tail]))
        for tr in self.tail_transitions:
            self.offsets = sorted(set(self.offsets + [tr.before, tr.after]))
        self.transitions = []
        previous = self.types[0][0]
        for t, idx in zip(self.times, self.indices):
            after = self.types[idx][0]
            if after != previous:
                self.transitions.append(Transition(t, previous, after))
            previous = after
        self.transitions.extend(self.tail_transitions)
        self.transitions.sort(key=lambda x: x.utc)

    def offset_at(self, utc: int | float) -> int:
        if utc < MIN_TIME or utc >= MAX_TIME:
            raise ValueError('Outside declared reference range 1970--2036')
        if not self.times or utc > self.times[-1]:
            if self.fixed_tail is not None:
                return self.fixed_tail
            if self.tail_transitions:
                points = [tr.utc for tr in self.tail_transitions]
                idx = bisect_right(points, utc) - 1
                return self.tail_transitions[idx].after if idx >= 0 else self.tail_initial
            raise ValueError('No footer rule covers the requested instant')
        idx = bisect_right(self.times, utc) - 1
        return self.types[self.indices[idx] if idx >= 0 else 0][0]

    def wall(self, utc: int | float) -> datetime:
        return EPOCH + timedelta(seconds=utc + self.offset_at(utc))

    def resolve(self, wall: datetime) -> list[int]:
        local = wall_seconds(wall)
        result = []
        for off in self.offsets:
            utc = local - off
            if MIN_TIME <= utc < MAX_TIME and self.offset_at(utc) == off:
                result.append(utc)
        return sorted(set(result))

    def gap_projection_map(self, wall: datetime) -> dict[str, int]:
        """Return deterministic projections for a missing civil label.

        ``shift_forward`` preserves the position inside the gap and lands after
        the transition.  ``shift_backward`` lands the same distance before the
        transition.  An empty mapping means the label is not in a gap.
        """
        local = wall_seconds(wall)
        for transition in self.transitions:
            lower = transition.utc + transition.before
            upper = transition.utc + transition.after
            if transition.delta > 0 and lower <= local < upper:
                return {
                    "shift_forward": local - transition.before,
                    "shift_backward": local - transition.after,
                }
        return {}

    def gap_projections(self, wall: datetime) -> list[int]:
        """Backward-compatible ordered projection list."""
        projections = self.gap_projection_map(wall)
        return [
            projections[key]
            for key in ("shift_forward", "shift_backward")
            if key in projections
        ]


def _recurring_tail(std_offset: int, dst_offset: int, start_rule, end_rule,
                    last: int) -> tuple[int, list[Transition]]:
    """Expand a bounded rule and infer the state before its first transition."""
    transitions: list[Transition] = []
    # A December civil rule can spill into January UTC. Include 1969 at the
    # lower boundary; the strict last/MAX_TIME filter keeps footer-only output bounded.
    first_year = max(1969, datetime.fromtimestamp(max(last, MIN_TIME), timezone.utc).year - 1)
    for year in range(first_year, 2038):
        start_utc = int((_rule_local(year, start_rule) - EPOCH).total_seconds()) - std_offset
        end_utc = int((_rule_local(year, end_rule) - EPOCH).total_seconds()) - dst_offset
        for tr in (Transition(start_utc, std_offset, dst_offset),
                   Transition(end_utc, dst_offset, std_offset)):
            if last < tr.utc < MAX_TIME:
                transitions.append(tr)
    transitions.sort(key=lambda tr: tr.utc)
    initial = transitions[0].before if transitions else std_offset
    return initial, transitions
