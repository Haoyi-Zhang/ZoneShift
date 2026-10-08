"""APScheduler helper-function excerpts for dependency-isolated trigger execution.

The trigger/field/expression modules are upstream release sources. These helpers
copy their upstream behavior; only explicit ZoneInfo inputs and aware datetimes
are admitted by the harness. The tzlocal import is stubbed to fail if reached.
No scheduler algorithm is reimplemented in this support module.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
UTC = timezone.utc


def asint(text):
    if text is not None:
        return int(text)


def astimezone(obj):
    if not isinstance(obj, ZoneInfo):
        raise TypeError('The isolated harness requires an explicit pinned ZoneInfo')
    return obj


def convert_to_datetime(value, tz, arg_name):
    if value is None:
        return None
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value
    raise TypeError(f'{arg_name}: only aware datetime or None in isolated harness')


def datetime_ceil(dateval):
    if dateval.microsecond > 0:
        return dateval + timedelta(seconds=1, microseconds=-dateval.microsecond)
    return dateval


def datetime_utc_add(dateval, tdelta):
    original_tz = dateval.tzinfo
    if original_tz is None:
        return dateval + tdelta
    return (dateval.astimezone(UTC) + tdelta).astimezone(original_tz)


def datetime_ceil_312(dateval):
    if dateval.microsecond > 0:
        return datetime_utc_add(
            dateval, timedelta(seconds=1, microseconds=-dateval.microsecond)
        )
    return dateval


def datetime_repr(dateval):
    return dateval.strftime('%Y-%m-%d %H:%M:%S %Z') if dateval else 'None'
