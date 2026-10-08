from datetime import datetime
import multiprocessing
import time

from zoneshift.contracts import Contract
from zoneshift.execution import _run_process, load_zone


def _hanging_factory(implementation, zone, contract, start):
    def step():
        time.sleep(30)
    return step


def test_owned_worker_timeout_is_bounded_and_reaped():
    zone = load_zone('2024a', 'Etc/UTC')
    start = datetime(2024, 1, 1, tzinfo=zone).timestamp()
    before_children = {child.pid for child in multiprocessing.active_children()}
    before = time.monotonic()
    result = _run_process('croniter-2.0.1', zone, Contract((5,), (0,)), start, 1,
                          factory=_hanging_factory)
    assert result['error'] == 'timeout'
    assert result['calls'] == 1
    assert result['trace'] == []
    assert time.monotonic() - before < 12
    assert {child.pid for child in multiprocessing.active_children()} == before_children


def test_process_uses_pinned_timezone_and_retains_state():
    zone = load_zone('2024a', 'Etc/UTC')
    start = datetime(2024, 1, 1, tzinfo=zone).timestamp()
    result = _run_process('croniter-2.0.1', zone, Contract((5,), (0,)), start, 2)
    assert result['error'] is None
    assert result['trace'][1]['timestamp'] - result['trace'][0]['timestamp'] == 86400
    assert result['startup_ns'] > 0
