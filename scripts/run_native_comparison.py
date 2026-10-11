#!/usr/bin/env python3
"""Requalify retained observations and run a separate benign cronsim comparator.

No compilation, remote service, or historical timing replacement. Native
policies follow the actual emitted expression, not a vote among libraries.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from zoneshift.adapters import cronsim_class
from zoneshift.contracts import Contract, policy_completion_frontier, qualify
from zoneshift.execution import load_zone, run_trace
from zoneshift.profiles import PROFILES
from zoneshift.tzif import EPOCH, TZif
from scripts.run_policy_attribution import upgrade_sufficiency_study


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def contract_from_dict(raw):
    return Contract(**{key: tuple(value) if key in {'hours', 'minutes', 'weekdays'} else value
                       for key, value in raw.items()})


def native_contract(contract, expression):
    minute, hour, *_ = expression.split()
    special = not minute.startswith('*') and not hour.startswith('*')
    return replace(contract, gap='clamp_forward' if special else 'skip',
                   fold='first' if special else 'both')


def unsupported_native_transitions(oracle, start, horizon):
    """The documentation's small-change policy does not specify >=3-hour jumps."""
    return [tr.utc for tr in oracle.transitions
            if start <= tr.utc <= horizon and abs(tr.delta) >= 10800]


def requalify(out):
    zones = {}
    def oracle(tzdb, name):
        if (tzdb, name) not in zones:
            zones[tzdb, name] = TZif(ROOT / 'data/tzdb' / tzdb / name)
        return zones[tzdb, name]

    frontier_data = json.loads((out / 'policy-frontiers.json').read_text())
    classifications, supports = Counter(), Counter()
    changed = 0
    for row in frontier_data['runs']:
        result = policy_completion_frontier(oracle('2024a', row['zone']),
            contract_from_dict(row['contract']), row['start'], row['trace'], row['error'])
        changed += result['classification'] != row['frontier']['classification']
        row['frontier'] = result
        row['support_pattern'] = [f"{item['gap']}+{item['fold']}"
                                 for item in result['passing_completions']]
        classifications[row['implementation'], row['kind'], result['classification']] += 1
        supports[row['implementation'], row['kind'], ','.join(row['support_pattern']) or 'none'] += 1
    summary = frontier_data['summary']
    summary['classification_counts'] = {'|'.join(key): value for key, value in sorted(classifications.items())}
    summary['support_pattern_counts'] = {'|'.join(key): value for key, value in sorted(supports.items())}
    summary['qualification_model'] = 'four gap policies / three fold policies; coalesced instants'
    summary['execution_basis'] = 'Retained 616 executed traces; frontiers recomputed, no new scheduler calls'
    summary['interpretation'] = 'Robustness is relative to the enumerated policy domain, not every application policy.'
    dump(out / 'policy-frontiers.json', frontier_data)

    # Re-evaluate violations and square attribution from actual retained traces.
    # Complete skip/both contracts should not change merely by extending the menu.
    matrix = json.loads((out / 'version-data-matrix.json').read_text())
    matrix_changes = []
    status_counts = Counter()
    for row in matrix['runs']:
        result = qualify(oracle(row['tzdb'], row['zone']), PROFILES[row['profile']],
                         row['start'], row['trace'], row['error'])
        if result != row['qualification']:
            matrix_changes.append({'case_id': row['case_id'], 'implementation': row['implementation'],
                                   'tzdb': row['tzdb'], 'before': row['qualification'], 'after': result})
        status_counts[row['implementation'], result['status']] += 1
    if matrix_changes:
        raise RuntimeError('Retained matrix changed; inspect before regenerating attribution')
    main_changes = []
    main_counts = Counter()
    main_traces = 0
    for line in (ROOT / 'results/runs.jsonl').read_text().splitlines():
        row = json.loads(line)
        result = qualify(oracle(row['tzdb'], row['zone']), PROFILES[row['profile']],
                         row['start'], row['trace'], row['error'])
        main_traces += 1
        main_counts[row['implementation'], row['strategy'], result['status']] += 1
        if result != row['qualification']:
            main_changes.append({'case_id': row['case_id'], 'implementation': row['implementation'],
                                 'strategy': row['strategy'], 'seed': row['seed'],
                                 'before': row['qualification'], 'after': result})
    if main_changes:
        raise RuntimeError('Retained benchmark changed; inspect its comparator accounting')
    sufficiency = upgrade_sufficiency_study(out)
    dump(out / 'policy-attribution-summary.json', {'policy_frontiers': summary, 'upgrade_sufficiency': sufficiency})
    verification = {'frontier_traces_requalified': len(frontier_data['runs']),
        'frontier_classification_changes': changed,
        'matrix_traces_requalified': len(matrix['runs']), 'matrix_qualification_changes': matrix_changes,
        'matrix_status_counts': {'|'.join(key): value for key, value in sorted(status_counts.items())},
        'main_traces_requalified': main_traces, 'main_qualification_changes': main_changes,
        'main_status_counts': {'|'.join(key): value for key, value in sorted(main_counts.items())},
        'certificates_recomputed': sufficiency['certificates'], 'new_scheduler_calls': 0}
    dump(out / 'policy-model-requalification.json', verification)
    return verification, frontier_data['runs']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'results')
    parser.add_argument('--limit', type=int, help='Smoke run only; writes a separately named result')
    parser.add_argument('--requalify-only', action='store_true', help='Recheck retained traces without new scheduler calls')
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT.resolve()):
        raise ValueError('Output must stay inside this artifact')
    out.mkdir(parents=True, exist_ok=True)
    if args.requalify_only:
        verification, _ = requalify(out)
        native_path = out / 'native-cronsim-comparison.json'
        if native_path.exists():
            native = json.loads(native_path.read_text())
            native['summary']['requalification'] = verification
            dump(native_path, native)
        print(json.dumps(verification, indent=2), flush=True)
        return
    cronsim_class()  # Assert exact optional dependency before any experiment.
    requalification, retained_frontiers = requalify(out) if args.limit is None else (None,
        json.loads((ROOT / 'results/policy-frontiers.json').read_text())['runs'])
    rows = []
    cache = {}
    boundary_baselines = {}
    for line in (ROOT / 'results/runs.jsonl').read_text().splitlines():
        row = json.loads(line)
        if row['strategy'] == 'boundary':
            boundary_baselines[row['case_id'], row['implementation']] = row

    def execute(study, case_id, name, start, contract, implementation='cronsim-2.6'):
        if name not in cache:
            cache[name] = (load_zone('2024a', name), TZif(ROOT / 'data/tzdb/2024a' / name))
        zone, oracle = cache[name]
        expression = contract.cron(native_wildcards=True)
        native = native_contract(contract, expression)
        run = run_trace(implementation, zone, contract, start, count=8)
        horizon = max([start] + [event['timestamp'] for event in run['trace']])
        unsupported = unsupported_native_transitions(oracle, start, horizon)
        if unsupported:
            native = replace(native, policy_scope='open')
        native_result = qualify(oracle, native, start, run['trace'], run['error'])
        fixed_result = qualify(oracle, replace(contract, gap='skip', fold='both'),
                               start, run['trace'], run['error'])
        frontier = policy_completion_frontier(oracle,
            replace(contract, gap='unspecified', fold='unspecified', policy_scope=native.policy_scope),
            start, run['trace'], run['error'])
        baselines = {}
        if study == 'boundary':
            for impl in ('aps-3.11.2', 'croniter-1.3.10', 'croniter-2.0.1'):
                before = boundary_baselines[case_id, impl]
                baselines[impl] = {'qualification': before['qualification'],
                    'sequence_equal': [e['timestamp'] for e in before['trace']] ==
                                      [e['timestamp'] for e in run['trace']]}
        rows.append({'study': study, 'case_id': case_id, 'zone': name, 'tzdb': '2024a',
            'zone_file_sha256': hashlib.sha256((ROOT / 'data/tzdb/2024a' / name).read_bytes()).hexdigest(),
            'implementation': implementation, 'expression': expression, 'start': start,
            'native_contract': native.to_dict(), 'native_qualification': native_result,
            'skip_both_qualification': fixed_result, 'frontier': frontier,
            'unsupported_large_transitions': unsupported, 'retained_baseline_comparisons': baselines, **run})

    cases = json.loads((ROOT / 'results/design.json').read_text())['case_specification']
    for index, case in enumerate(cases[:args.limit] if args.limit else cases):
        execute('boundary', case['case_id'], case['zone'], case['start'], PROFILES[case['profile']])
        if (index + 1) % 100 == 0:
            print(f'Native boundary: {index + 1}/{len(cases)}', flush=True)
    if args.limit is None:
        # Midpoints distinguish clamp from position-preserving projection;
        # the older frontier chose the lower boundary, where they can coincide.
        unique = {row['case_id']: row for row in retained_frontiers}
        for row in unique.values():
            oracle = TZif(ROOT / 'data/tzdb/2024a' / row['zone'])
            tr = next(tr for tr in oracle.transitions if tr.utc == row['transition'])
            middle = ((tr.utc + min(tr.before, tr.after) + abs(tr.delta) // 2 + 59) // 60) * 60
            label = EPOCH + timedelta(seconds=middle)
            contract = Contract((label.hour,), (label.minute,), gap='unspecified', fold='unspecified')
            execute('midpoint_' + row['kind'], row['case_id'] + ':midpoint', row['zone'], row['start'], contract)
        sentry = json.loads((ROOT / 'results/released-sentry.json').read_text())
        for index, row in enumerate(sentry['runs']):
            for implementation in ('cronsim-2.6', 'sentry-cronsim-2.6'):
                execute('sentry_five_am', f'sentry:{index}', row['zone'], row['start'], PROFILES['five_am'], implementation)
    counts = Counter((row['study'], row['implementation'], row['native_qualification']['status']) for row in rows)
    fixed_counts = Counter((row['study'], row['implementation'], row['skip_both_qualification']['status']) for row in rows)
    summary = {'traces': len(rows), 'api_calls': sum(row['calls'] for row in rows),
        'timeouts': sum(row['error'] == 'timeout' for row in rows),
        'native_status_counts': {'|'.join(key): value for key, value in sorted(counts.items())},
        'skip_both_status_counts': {'|'.join(key): value for key, value in sorted(fixed_counts.items())},
        'native_pass_but_skip_both_violation': sum(row['native_qualification']['status'] == 'PASS' and
            row['skip_both_qualification']['status'] == 'VIOLATION' for row in rows),
        'unsupported': sum(bool(row['unsupported_large_transitions']) for row in rows),
        'requalification': requalification,
        'interpretation': 'Native-policy compatibility is separate from skip/both compatibility; not new defect counts or a full Sentry deployment.'}
    import cronsim.cronsim as native_source
    result = {'summary': summary, 'environment': {'python': sys.version, 'platform': platform.platform(),
        'executed_utc': datetime.now(timezone.utc).isoformat(), 'cronsim': version('cronsim'),
        'cronsim_source_sha256': hashlib.sha256(Path(native_source.__file__).read_bytes()).hexdigest(),
        'source_url': 'https://github.com/cuu508/cronsim/blob/2.6/cronsim/cronsim.py',
        'policy_source_url': 'https://github.com/cuu508/cronsim/blob/2.6/README.md',
        'sentry_source_url': 'https://github.com/getsentry/sentry/blob/24.12.1/src/sentry/monitors/schedule.py'},
        'runs': rows}
    dump(out / ('native-cronsim-smoke.json' if args.limit else 'native-cronsim-comparison.json'), result)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
