"""Bounded deterministic calls into real upstream next-occurrence APIs."""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import multiprocessing
import signal,time
from weakref import WeakKeyDictionary
from .adapters import aps_class,croniter_class,sentry_next,ROOT
from .contracts import Contract


class CallTimeout(TimeoutError):pass

_ZONE_FILES = WeakKeyDictionary()
_CALL_SECONDS = .25


def _alarm(signum,frame):raise CallTimeout('next-occurrence call exceeded 0.25 seconds')


def load_zone(version, name):
    path=ROOT/'data/tzdb'/version/name
    with path.open('rb') as f:
        zone = ZoneInfo.from_file(f,key=name)
    _ZONE_FILES[zone] = path.resolve()
    return zone


def _make_step(implementation, zone, contract, start):
    now=datetime.fromtimestamp(start+0.000001,zone)
    if implementation.startswith('aps-'):
        trigger=aps_class(implementation[4:])(**contract.aps_kwargs(),timezone=zone)
        previous=None
        def step():
            nonlocal previous,now
            value=trigger.get_next_fire_time(previous,now)
            previous=now=value
            return value
    elif implementation in {'croniter-1.3.10','croniter-2.0.1','croniter-6.2.4'}:
        iterator=croniter_class(implementation[9:])(contract.cron(),datetime.fromtimestamp(start,zone))
        def step():return iterator.get_next(datetime)
    elif implementation in {'sentry-adapter','sentry-24.3.0'}:
        now=datetime.fromtimestamp(start,zone)
        def step():
            nonlocal now
            now=sentry_next(now,contract.cron(), '1.3.10' if implementation=='sentry-24.3.0' else '2.0.1')
            return now
    else:raise ValueError(implementation)
    return step


def _collect_steps(step, start, count, arm=lambda: None, disarm=lambda: None):
    trace=[];error=None;calls=0
    try:
        prior=start
        for _ in range(count):
            calls+=1
            arm()
            value=step()
            disarm()
            if value is None:
                error='unexpected_end';break
            t=value.timestamp()
            trace.append({'timestamp':t,'iso':value.isoformat(),'fold':value.fold})
            if t<=prior:
                error='nonprogress';break
            prior=t
    except CallTimeout:
        error='timeout'
    except Exception as exc:
        error=f'{type(exc).__name__}: {exc}'
    finally:
        disarm()
    return {'trace':trace,'error':error,'calls':calls}


def _step_worker(connection, implementation, zone_path, key, contract, start, factory):
    """One stateful trace per owned process; no host timezone fallback."""
    try:
        with Path(zone_path).open('rb') as stream:
            zone = ZoneInfo.from_file(stream, key=key)
        step = factory(implementation, zone, contract, start)
        connection.send(('ready', None))
        while connection.recv() == 'step':
            try:
                value = step()
                connection.send(('value', None if value is None else
                                 {'timestamp': value.timestamp(), 'iso': value.isoformat(), 'fold': value.fold}))
            except CallTimeout:
                connection.send(('error', 'timeout'))
            except Exception as exc:
                connection.send(('error', f'{type(exc).__name__}: {exc}'))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            connection.send(('init_error', f'{type(exc).__name__}: {exc}'))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        connection.close()


def _run_process(implementation, zone, contract, start, count, factory=_make_step):
    path = _ZONE_FILES.get(zone)
    if path is None:
        raise ValueError('Process runner requires a zone returned by load_zone')
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    worker = context.Process(target=_step_worker,
        args=(child, implementation, str(path), zone.key, contract, start, factory))
    trace=[];error=None;calls=0
    before = time.perf_counter_ns()
    worker.start()
    child.close()
    startup_ns = 0
    try:
        if not parent.poll(10):
            error = 'worker_startup_timeout'
        else:
            status, detail = parent.recv()
            startup_ns = time.perf_counter_ns() - before
            if status != 'ready':
                error = detail or 'worker_initialization_error'
            else:
                prior = start
                for _ in range(count):
                    calls += 1
                    parent.send('step')
                    if not parent.poll(_CALL_SECONDS):
                        error = 'timeout'; break
                    status, value = parent.recv()
                    if status == 'error':
                        error = value; break
                    if value is None:
                        error = 'unexpected_end'; break
                    trace.append(value)
                    if value['timestamp'] <= prior:
                        error = 'nonprogress'; break
                    prior = value['timestamp']
    except (EOFError, BrokenPipeError, OSError) as exc:
        error = f'worker_error: {type(exc).__name__}'
    finally:
        try:
            if worker.is_alive() and error != 'timeout':
                parent.send('stop')
        except (EOFError, BrokenPipeError, OSError):
            pass
        worker.join(.5)
        if worker.is_alive():
            worker.terminate()
            worker.join(2)
        if worker.is_alive():
            worker.kill()
            worker.join(2)
        parent.close()
        worker.close()
    return {'trace':trace,'error':error,'calls':calls,
            'elapsed_ns':time.perf_counter_ns()-before,
            'runner':'spawned-process', 'startup_ns':startup_ns}


def run_trace(implementation: str, zone: ZoneInfo, contract: Contract, start: float, count=8):
    if not 1 <= count <= 256:raise ValueError('Unbounded call count')
    if implementation not in {'aps-3.11.0','aps-3.11.2','croniter-1.3.10',
                              'croniter-2.0.1','croniter-6.2.4','sentry-adapter','sentry-24.3.0'}:
        raise ValueError(implementation)
    if not hasattr(signal, 'SIGALRM') or not hasattr(signal, 'setitimer'):
        return _run_process(implementation, zone, contract, start, count)
    before=time.perf_counter_ns()
    step = _make_step(implementation, zone, contract, start)
    old=signal.signal(signal.SIGALRM,_alarm)
    try:
        result = _collect_steps(step, start, count,
                               lambda: signal.setitimer(signal.ITIMER_REAL,_CALL_SECONDS),
                               lambda: signal.setitimer(signal.ITIMER_REAL,0))
    finally:
        signal.signal(signal.SIGALRM,old)
    return {**result,'elapsed_ns':time.perf_counter_ns()-before}
