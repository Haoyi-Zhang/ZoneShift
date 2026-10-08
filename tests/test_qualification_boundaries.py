from datetime import datetime, timedelta
import pytest
from test_core import ref, trace
from zoneshift.contracts import Contract, qualify, policy_completion_frontier
from zoneshift.execution import load_zone, run_trace
import zoneshift.contracts as contracts
from zoneshift.__main__ import _upgrade


@pytest.mark.parametrize('fold', ['first', 'second', 'both'])
def test_weekly_reference_covers_observed_fold_filtered_horizon(fold):
    zone = load_zone('2024a', 'America/New_York')
    start = datetime(2024, 10, 1, tzinfo=zone).timestamp()
    times = []
    for i in range(8):
        label = datetime(2024, 10, 6, 1, 30) + timedelta(days=7*i)
        candidates = ref('America/New_York').resolve(label)
        times.extend(candidates if fold == 'both' else candidates[:1] if fold == 'first' else candidates[-1:])
    contract = Contract((1,), (30,), weekdays=(6,), gap='skip', fold=fold)
    assert qualify(ref('America/New_York'), contract, start, trace(times))['status'] == 'PASS'


def test_frontier_reuses_only_fold_independent_reference(monkeypatch):
    zone = load_zone('2024a', 'America/New_York')
    start = datetime(2024, 10, 1, tzinfo=zone).timestamp()
    times = [datetime(2024, 10, 6, 1, 30, tzinfo=zone).timestamp() + 7*86400*i for i in range(3)]
    contract = Contract((1,), (30,), weekdays=(6,))
    calls = []
    original = contracts.reference
    def counted(*args, **kwargs):
        calls.append(args[1].gap)
        return original(*args, **kwargs)
    monkeypatch.setattr(contracts, 'reference', counted)
    frontier = policy_completion_frontier(ref('America/New_York'), contract, start, trace(times))
    assert frontier['completion_count'] == 9
    assert sorted(calls) == ['shift_backward', 'shift_forward', 'skip']


@pytest.mark.parametrize('implementation', ['aps-3.11.0', 'aps-3.11.1', 'aps-3.11.2', 'aps-3.11.3',
                                         'croniter-1.3.10', 'croniter-2.0.1', 'croniter-6.2.4',
                                         'sentry-adapter', 'sentry-24.3.0'])
def test_all_declared_releases_execute_one_bounded_occurrence(implementation):
    zone = load_zone('2024a', 'Etc/UTC')
    result = run_trace(implementation, zone, Contract((0,), (30,), gap='skip', fold='first'),
                       datetime(2024, 1, 1, tzinfo=zone).timestamp(), count=1)
    assert result['error'] is None
    assert len(result['trace']) == 1


def test_upgrade_uses_one_start_instant_for_all_cells():
    config = dict(mode='upgrade', zone='America/Asuncion', start='2025-06-01T04:45',
                  count=1, old_implementation='aps-3.11.2', new_implementation='aps-3.11.2',
                  old_tzdb='2024a', new_tzdb='2025b', contract={'hours': list(range(24)), 'minutes': [30], 'gap': 'skip', 'fold': 'first'})
    result, _ = _upgrade(config)
    assert len({cell['start_instant'] for cell in result['cells'].values()}) == 1
    assert len({cell['trace'][0]['timestamp'] for cell in result['cells'].values()}) == 1
