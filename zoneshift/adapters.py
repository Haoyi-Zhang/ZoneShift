"""Run unmodified released trigger modules under a small explicit-zone harness."""
from functools import lru_cache
from pathlib import Path
from datetime import datetime
import importlib, sys, types
from . import vendor_support
ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=4)
def aps_class(version: str):
    if version not in {'3.11.0', '3.11.1', '3.11.2', '3.11.3'}:
        raise ValueError(version)
    for name in list(sys.modules):
        if name == 'apscheduler' or name.startswith('apscheduler.'):
            del sys.modules[name]
    package=types.ModuleType('apscheduler')
    package.__path__=[str(ROOT/'vendor'/f'apscheduler-{version}'/'apscheduler')]
    sys.modules['apscheduler']=package
    util=types.ModuleType('apscheduler.util')
    for name in ('asint','astimezone','convert_to_datetime','datetime_ceil',
                 'datetime_utc_add','datetime_repr'):
        setattr(util,name,getattr(vendor_support,name))
    if version in {'3.11.2', '3.11.3'}: util.datetime_ceil=vendor_support.datetime_ceil_312
    sys.modules['apscheduler.util']=util
    tzlocal=types.ModuleType('tzlocal')
    def no_ambient_zone():
        raise RuntimeError('Ambient timezone access forbidden; specify a pinned zone')
    tzlocal.get_localzone=no_ambient_zone
    sys.modules['tzlocal']=tzlocal
    return importlib.import_module('apscheduler.triggers.cron').CronTrigger


def croniter_class(version: str = '2.0.1'):
    if version not in {'1.3.10', '2.0.1', '6.2.4'}:
        raise ValueError(version)
    name='zoneshift_croniter_'+version.replace('.', '_')
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name, ROOT/'vendor'/f'croniter-{version}'/'croniter.py')
        module=importlib.util.module_from_spec(spec)
        sys.modules[name]=module
        spec.loader.exec_module(module)
    return sys.modules[name].croniter


def sentry_next(reference_ts, crontab, version='2.0.1'):
    """Reconstruct Sentry 24.3.0 get_next_schedule's crontab branch.

    Sentry 24.3.0 pins croniter 1.3.10; pass version="1.3.10" for that release.
    The default 2.0.1 preserves the frozen later-version comparison.
    This is a local integration adapter, not a running Sentry deployment.
    Source: src/sentry/monitors/schedule.py, Git blob d7bdb37da6a20fda41b2413db3bd48c40d034bad.
    """
    iterator=croniter_class(version)(crontab, reference_ts)
    return iterator.get_next(datetime).replace(second=0, microsecond=0)
