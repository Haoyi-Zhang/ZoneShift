"""Benign policy regressions over retained TZif inputs and optional cronsim."""
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import pytest

from zoneshift.contracts import Contract, policy_completion_frontier, qualify, reference, required
from zoneshift.execution import load_zone, run_trace
from zoneshift.repair import wall_next
from zoneshift.tzif import TZif
from scripts.run_native_comparison import native_contract, unsupported_native_transitions

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name,start,hour,minute,expected', [
    ('America/New_York', '2024-03-09T02:30', 2, 30, '2024-03-10T03:00:00-04:00'),
    ('Australia/Lord_Howe', '2024-10-05T02:15', 2, 15, '2024-10-06T02:30:00+11:00'),
    ('Pacific/Apia', '2011-12-29T05:00', 5, 0, '2011-12-31T00:00:00+14:00'),
])
def test_clamp_reference_and_separate_zoneinfo_intervention(name, start, hour, minute, expected):
    zone = load_zone('2024a', name)
    oracle = TZif(ROOT / 'data/tzdb/2024a' / name)
    previous = datetime.fromisoformat(start).replace(tzinfo=zone)
    contract = Contract((hour,), (minute,), gap='clamp_forward', fold='both')
    events, _ = reference(oracle, contract, previous.timestamp(), 8)
    timestamp = required(events, contract)[0]
    assert datetime.fromtimestamp(timestamp, zone).isoformat() == expected
    assert wall_next(previous, contract).timestamp() == timestamp
    run = [{'timestamp': value} for value in required(events, contract)[:8]]
    assert qualify(oracle, contract, previous.timestamp(), run)['status'] == 'PASS'
    frontier = policy_completion_frontier(oracle, replace(contract, gap='unspecified'), previous.timestamp(), run)
    assert frontier['classification'] == 'policy_sensitive'
    assert {'gap': 'clamp_forward', 'fold': 'both'} in frontier['passing_completions']
    assert {'gap': 'shift_forward', 'fold': 'both'} not in frontier['passing_completions']


def test_clamp_coalesces_instants_and_still_rejects_duplicate_delivery_trace():
    oracle = TZif(ROOT / 'data/tzdb/2024a/America/New_York')
    zone = load_zone('2024a', 'America/New_York')
    start = datetime(2024, 3, 10, 1, 59, tzinfo=zone).timestamp()
    contract = Contract((2, 3), (0, 30), gap='clamp_forward', fold='both')
    events, _ = reference(oracle, contract, start, 8)
    expected = required(events, contract)
    assert expected == sorted(set(expected))
    assert datetime.fromtimestamp(expected[0], zone).hour == 3
    assert qualify(oracle, contract, start, [{'timestamp': x} for x in expected[:8]])['status'] == 'PASS'
    assert qualify(oracle, contract, start, [{'timestamp': expected[0]}] * 2)['status'] == 'VIOLATION'


def test_unknown_policy_domain_is_not_a_robust_defect_or_a_promotion_pass():
    oracle = TZif(ROOT / 'data/tzdb/2024a/Etc/UTC')
    start = 1704067200
    for contract in (Contract((5,), (0,), policy_scope='open'),
                     Contract((5,), (0,), gap='skip', fold='both', policy_scope='open')):
        result = qualify(oracle, contract, start, [{'timestamp': start + 37}])
        assert result['status'] == 'UNDERSPECIFIED'
        assert result['reasons'] == ['unsupported_policy_domain']
        assert result['policy_frontier']['classification'] == 'unresolved_policy_domain'
    with pytest.raises(ValueError, match='Unsupported gap'):
        Contract((5,), (0,), gap='unknown_vendor_option')
    with pytest.raises(ValueError, match='explicit gap/fold'):
        wall_next(datetime(2024, 1, 1, tzinfo=load_zone('2024a', 'Etc/UTC')), contract)


@pytest.mark.parametrize('implementation', ['cronsim-2.6', 'sentry-cronsim-2.6'])
def test_native_daily_gap_passes_clamp_not_shift_or_skip(implementation):
    pytest.importorskip('cronsim')
    zone = load_zone('2024a', 'America/New_York')
    oracle = TZif(ROOT / 'data/tzdb/2024a/America/New_York')
    contract = Contract((2,), (30,))
    start = datetime(2024, 3, 9, 2, 30, tzinfo=zone).timestamp()
    run = run_trace(implementation, zone, contract, start, count=8)
    assert run['error'] is None
    assert run['trace'][0]['iso'] == '2024-03-10T03:00:00-04:00'
    frontier = policy_completion_frontier(oracle, replace(contract, fold='first'), start, run['trace'])
    assert frontier['passing_completions'] == [{'gap': 'clamp_forward', 'fold': 'first'}]
    assert qualify(oracle, native_contract(contract, contract.cron(native_wildcards=True)), start, run['trace'])['status'] == 'PASS'


def test_native_expression_wildcard_not_set_cardinality_selects_dst_mode():
    native = pytest.importorskip('cronsim')
    zone = load_zone('2024a', 'America/New_York')
    start = datetime(2024, 11, 3, 0, 30, tzinfo=zone)
    contract = Contract(tuple(range(24)), (30,))
    explicit = native.CronSim(contract.cron(), start)
    wildcard = native.CronSim(contract.cron(native_wildcards=True), start)
    assert explicit.fixup_tz is zone
    assert wildcard.fixup_tz is None
    explicit_times = [next(explicit).timestamp() for _ in range(3)]
    wildcard_times = [next(wildcard).timestamp() for _ in range(3)]
    assert explicit_times != wildcard_times
    assert native_contract(contract, contract.cron()).fold == 'first'
    assert native_contract(contract, contract.cron(native_wildcards=True)).fold == 'both'


def test_large_native_change_is_left_open_not_promoted_by_menu_search():
    oracle = TZif(ROOT / 'data/tzdb/2024a/Pacific/Apia')
    zone = load_zone('2024a', 'Pacific/Apia')
    start = datetime(2011, 12, 29, 5, tzinfo=zone).timestamp()
    horizon = datetime(2011, 12, 31, 5, tzinfo=zone).timestamp()
    assert unsupported_native_transitions(oracle, start, horizon)
    contract = Contract((5,), (0,), gap='clamp_forward', fold='first', policy_scope='open')
    events, _ = reference(oracle, contract, start)
    run = [{'timestamp': x} for x in required(events, contract)[:8]]
    assert qualify(oracle, contract, start, run)['status'] == 'UNDERSPECIFIED'


def test_retained_native_comparison_keeps_negative_and_policy_sensitive_results():
    import json
    result = json.loads((ROOT / 'results/native-cronsim-comparison.json').read_text())
    summary = result['summary']
    assert summary['traces'] == 1368 and summary['api_calls'] == 10944
    assert summary['native_pass_but_skip_both_violation'] == 96
    assert summary['native_status_counts']['boundary|cronsim-2.6|VIOLATION'] == 8
    blocked = [row for row in result['runs'] if row['native_qualification']['status'] == 'VIOLATION']
    assert {row['zone'] for row in blocked} == {'Australia/Lord_Howe'}
    assert all('missing_required_occurrence' in row['native_qualification']['reasons'] for row in blocked)
    assert all(row['expression'] == '30 * * * *' for row in blocked)
    assert summary['requalification']['matrix_qualification_changes'] == []
    assert summary['requalification']['main_traces_requalified'] == 33600
    assert summary['requalification']['main_qualification_changes'] == []
