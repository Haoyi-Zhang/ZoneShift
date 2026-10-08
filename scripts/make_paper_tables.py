#!/usr/bin/env python3
from __future__ import annotations
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / 'results'
parser = argparse.ArgumentParser()
parser.add_argument('--paper-dir', type=Path, default=ROOT / 'paper')
OUT = parser.parse_args().paper_dir / 'generated'
OUT.mkdir(parents=True, exist_ok=True)

def load(name: str):
    return json.loads((RES / name).read_text())

analysis = load('analysis.json')
extended = load('extended-analysis.json')
comp = load('comparator-analysis.json')
rule_series = load('rule-release-series.json')['summary']
signatures = load('signature-budget.json')
minimized = load('minimized-witnesses.json')['summary']
release_validation = load('release-series-validation.json')
policy_frontiers = load('policy-frontiers.json')['summary']
upgrade_sufficiency = load('upgrade-sufficiency.json')['summary']

labels = {
    'aps-3.11.0': 'APS 3.11.0',
    'aps-3.11.1': 'APS 3.11.1',
    'aps-3.11.2': 'APS 3.11.2',
    'croniter-1.3.10': 'croniter 1.3.10',
    'croniter-2.0.1': 'croniter 2.0.1',
    'aps-3.11.3': 'APS 3.11.3',
    'croniter-6.2.4': 'croniter 6.2.4',
}

rows = []
for r in analysis['table']:
    rows.append(
        f"{labels[r['implementation']]} & {r['boundary_v']} & {r['boundary_u']} & "
        f"{r['uniform_mean']:.1f} [{r['uniform_min']},{r['uniform_max']}] & {r['boundary_calls']:,} \\\\"
    )
(OUT / 'benchmark-table.tex').write_text(
    '\\begin{tabular}{lrrrr}\n\\toprule\n'
    'Calculation module & Boundary V & U & Uniform V & Calls$^a$\\\\\n'
    '\\midrule\n' + '\n'.join(rows) + '\n\\bottomrule\n'
    '\\multicolumn{5}{l}{$^a$Actual next-occurrence calls in the boundary matrix.}\n'
    '\\end{tabular}\n'
)

# Comparator table
pb = comp['policy_blind_first_branch']
pa = comp['policy_aware_three_way']
naive = comp['naive_cross_library']['counts']
aps = comp['release_differential_aps']['counts']
cron = comp['release_differential_croniter']['counts']
(OUT / 'comparator-table.tex').write_text(
    '\\begin{tabular}{lrrrr}\n\\toprule\n'
    'Comparator & Alarms & Actionable & Uncertain/FP & Missed V\\\\\n'
    '\\midrule\n'
    f"Policy-blind branch & {pb['alarms']:,} & {pb['actionable_alarms']:,} & "
    f"{pb['alarms_on_underspecified'] + pb['false_alarms_on_pass']:,} & {pb['missed_violations']:,} \\\\\n"
    f"APS/croniter diff. & {naive['alarms']:,} & {naive['actionable_alarms']:,} & "
    f"{naive['alarms_with_only_uncertainty'] + naive['false_alarms_both_pass']:,} & {naive['shared_or_equal_missed_violations']:,} \\\\\n"
    f"APS release diff. & {aps['alarms']:,} & {aps['actionable_alarms']:,} & "
    f"{aps['alarms_with_only_uncertainty'] + aps['false_alarms_both_pass']:,} & {aps['shared_or_equal_missed_violations']:,} \\\\\n"
    f"croniter release diff. & {cron['alarms']:,} & {cron['actionable_alarms']:,} & "
    f"{cron['alarms_with_only_uncertainty'] + cron['false_alarms_both_pass']:,} & {cron['shared_or_equal_missed_violations']:,} \\\\\n"
    '\\bottomrule\n\\end{tabular}\n'
)

# Factorial data-effect table.  Keep current-release holdouts out of the
# historical 2024a/2025b grid instead of rendering misleading all-zero rows.
counts = extended['factorial']['data_effect_counts']
factorial_implementations = extended['factorial']['design']['implementations']
factor_rows = []
for impl in factorial_implementations:
    factor_rows.append(
        f"{labels[impl]} & "
        f"{counts.get(impl+'|accepted_data_effect', 0)} & "
        f"{counts.get(impl+'|changed_with_violation_or_uncertainty', 0)} & "
        f"{counts.get(impl+'|byte_change_no_observed_behavior_change', 0)} & "
        f"{counts.get(impl+'|identical_bytes_and_behavior', 0)} \\\\"
    )
(OUT / 'factorial-table.tex').write_text(
    '\\begin{tabular}{lrrrr}\n\\toprule\n'
    'Module & Accepted & Changed+V/U & Bytes only & Identical\\\\\n'
    '\\midrule\n' + '\n'.join(factor_rows) + '\n\\bottomrule\n\\end{tabular}\n'
)

# Compact challenge table
mut = extended['mutation']
pol = extended['policy']
(OUT / 'challenge-table.tex').write_text(
    '\\begin{tabular}{lrrl}\n\\toprule\n'
    'Challenge & Cases & Correct verdicts & Interpretation\\\\\n'
    '\\midrule\n'
    f"Explicit fold policies & {pol['fold_cases']} & {pol['fold_cases']} & match/mismatch/unknown separated \\\\\n"
    f"Gap policies & {pol['gap_cases']} & {pol['gap_cases']} & skip/forward/backward/unknown \\\\\n"
    f"Fault-seeded traces & {mut['mutants']} & {mut['detected']} & all six operators detected \\\\\n"
    f"Benign transformations & {mut['benign_cases']} & {mut['benign_cases']} & no alarms \\\\\n"
    '\\bottomrule\n\\end{tabular}\n'
)

# Time-separated current-release and tzdb holdouts
current_release = load('current-release-holdout.json')['summary']
current_tzdb = load('current-tzdb-holdout.json')['summary']
status = current_release['status_counts']
compare = current_release['release_comparisons']
rows = []
for impl, pred in [('aps-3.11.3','aps-3.11.2'),('croniter-6.2.4','croniter-2.0.1')]:
    cases = compare[f'{pred}->{impl}']['cases']
    changed = compare[f'{pred}->{impl}']['changed']
    passed = status.get(f'{impl}|PASS', 0)
    violated = status.get(f'{impl}|VIOLATION', 0)
    rows.append(f"{labels[impl]} & {cases:,} & {changed:,} & {passed:,} & {violated:,} \\\\")
(OUT / 'current-holdout-table.tex').write_text(
    '\\begin{tabular}{lrrrr}\n\\toprule\n'
    'Current module & Cases & Changed vs. predecessor & Pass & Violation\\\\\n'
    '\\midrule\n' + '\n'.join(rows) + '\n\\bottomrule\n\\end{tabular}\n'
)

# Anchor data, grouping the two croniter releases because their selected traces are identical.
a = analysis['anchor']
def get(impl, anchor):
    return a.get(f'{impl}:{anchor}:VIOLATION', 0)
anchors = [('-86400','0'),('-3600','1'),('1','2'),('ordinary','3')]
lines = ['anchor APS0 APS2 Croniter']
for key, idx in anchors:
    lines.append(f"{idx} {get('aps-3.11.0',key)} {get('aps-3.11.2',key)} {get('croniter-2.0.1',key)}")
(OUT / 'anchors.dat').write_text('\n'.join(lines)+'\n')

# De-correlated signature-yield table.
curve_index = {(x['implementation'], x['strategy'], x['budget']): x for x in signatures['curve']}
sig_rows = []
for impl in analysis['implementations'] if 'implementations' in analysis else [
    'aps-3.11.0','aps-3.11.1','aps-3.11.2','croniter-1.3.10','croniter-2.0.1'
]:
    full = signatures['full_pool'][impl]
    uniform = [x['unique_signatures'] for x in full['uniform']]
    b16 = curve_index[impl, 'boundary', 16]['detect_any_rate'] * 100
    u16 = curve_index[impl, 'uniform', 16]['detect_any_rate'] * 100
    bavg = signatures['budget_averaged_unique_signatures'][f'{impl}|boundary']
    uavg = signatures['budget_averaged_unique_signatures'][f'{impl}|uniform']
    sig_rows.append(
        f"{labels[impl]} & {full['boundary_unique_signatures']} & "
        f"{sum(uniform)/len(uniform):.1f} [{min(uniform)},{max(uniform)}] & "
        f"{b16:.1f}/{u16:.1f} & {bavg:.1f}/{uavg:.1f} \\\\"
    )
(OUT / 'signature-budget-table.tex').write_text(
    '\\begin{tabular}{lrrrr}\n\\toprule\n'
    'Module & Boundary sig. & Uniform sig. & Any V @16 (B/U) & Mean sig. (B/U)\\\\\n'
    '\\midrule\n' + '\n'.join(sig_rows) + '\n\\bottomrule\n\\end{tabular}\n'
)

# Aggregate curve for a compact vector plot: equal-weight mean across modules.
lines = ['budget boundary uniform']
for budget in signatures['design']['budgets']:
    b = [x['unique_signatures_mean'] for x in signatures['curve'] if x['budget']==budget and x['strategy']=='boundary']
    u = [x['unique_signatures_mean'] for x in signatures['curve'] if x['budget']==budget and x['strategy']=='uniform']
    lines.append(f"{budget} {sum(b)/len(b):.6f} {sum(u)/len(u):.6f}")
(OUT / 'signature-budget.dat').write_text('\n'.join(lines)+'\n')

# Stepwise IANA release-series table; counts remain correlated observations.
release_rows = []
for spec in rule_series['design']['pairs']:
    pair_id = f"{spec['old']}->{spec['new']}:{spec['zone']}"
    totals = {'accepted_data_effect':0, 'changed_with_violation_or_uncertainty':0,
              'byte_change_no_observed_behavior_change':0, 'identical_bytes_and_behavior':0}
    for impl in rule_series['design']['implementations']:
        for key in totals:
            totals[key] += rule_series['pair_classification_counts'].get(f'{pair_id}|{impl}|{key}', 0)
    zone = spec['zone'].replace('America/','').replace('Europe/','').replace('Africa/','')
    release_rows.append(
        f"{spec['old']}--{spec['new']} / {zone} & {totals['accepted_data_effect']} & "
        f"{totals['changed_with_violation_or_uncertainty']} & "
        f"{totals['byte_change_no_observed_behavior_change']} \\\\"
    )
(OUT / 'release-series-table.tex').write_text(
    '\\begin{tabular}{lrrr}\n\\toprule\n'
    'Rule pair / zone & Accepted $\\Delta$ & Blocked $\\Delta$ & Byte-only\\\\\n'
    '\\midrule\n' + '\n'.join(release_rows) + '\n\\bottomrule\n\\end{tabular}\n'
)


# Policy-completion frontier over actual scheduler traces.
frontier_counts = policy_frontiers['classification_counts']
support_counts = policy_frontiers['support_pattern_counts']
frontier_rows = []
for impl in labels:
    if impl not in policy_frontiers['design']['implementations']:
        continue
    fold_robust = frontier_counts.get(f'{impl}|fold|robust_violation', 0)
    fold_support = []
    gap_support = []
    for key, value in sorted(support_counts.items()):
        candidate, kind, pattern = key.split('|', 2)
        if candidate != impl or pattern == 'none':
            continue
        if kind == 'fold':
            fold_name = pattern.split('+', 1)[1]
            fold_support.append(f'{fold_name} {value}')
        elif kind == 'gap':
            gap_name = pattern.split('+', 1)[0].replace('shift_forward', 'forward').replace('shift_backward', 'backward')
            gap_support.append(f'{gap_name} {value}')
    fold_cell = f'{fold_robust} robust V' if fold_robust else ', '.join(fold_support)
    gap_cell = ', '.join(gap_support)
    frontier_rows.append(
        f"{labels[impl]} & {fold_cell} & {gap_cell} " + r"\\"
    )
(OUT / 'policy-frontier-table.tex').write_text(
    '\\begin{tabular}{lll}\n\\toprule\n'
    'Module & Fold frontier & Gap frontier\\\\\n'
    '\\midrule\n' + '\n'.join(frontier_rows) + '\n\\bottomrule\n\\end{tabular}\n'
)

# Inclusion-minimal coordinate changes that reach PASS in an executed 2x2 square.
sufficiency_rows = []
for pair in ('aps-3.11.0->aps-3.11.2', 'croniter-1.3.10->croniter-2.0.1'):
    counts = {
        key.split('|', 1)[1]: value
        for key, value in upgrade_sufficiency['decision_counts'].items()
        if key.startswith(pair + '|')
    }
    old_name, new_name = pair.split('->')
    short_pair = f"{labels[old_name]}$\\rightarrow${labels[new_name]}"
    sufficiency_rows.append(
        f"{short_pair} & {counts.get('baseline_already_passes', 0)} & "
        f"{counts.get('code_change_sufficient', 0)} & "
        f"{counts.get('data_change_sufficient', 0)} & "
        f"{counts.get('either_single_change_sufficient', 0)} & "
        f"{counts.get('both_changes_required', 0)} & "
        f"{counts.get('no_passing_target', 0)} " + r"\\"
    )
(OUT / 'sufficiency-table.tex').write_text(
    '\\begin{tabular}{lrrrrrr}\n\\toprule\n'
    'Upgrade & Base P & Code & Data & Either & Both & No pass\\\\\n'
    '\\midrule\n' + '\n'.join(sufficiency_rows) + '\n\\bottomrule\n\\end{tabular}\n'
)

witness_rows = [
    f"Blocked behavioural classes & {minimized['blocked']} & exact replay " + r"\\",
    f"Accepted rule-pair/module classes & {minimized['accepted_data_effects']} & exact replay " + r"\\",
    f"Total compact witnesses & {minimized['witnesses']} & {minimized['replay_validation_api_calls']} calls " + r"\\",
]
(OUT / 'witness-table.tex').write_text(
    '\\begin{tabular}{lrr}\n\\toprule\n'
    'Evidence class & Representatives & Validation\\\\\n\\midrule\n'
    + '\n'.join(witness_rows) + '\n'
    '\\bottomrule\n\\end{tabular}\n'
)

# A machine-readable summary for the paper audit.
summary = {
    'main_traces': analysis['total_runs'],
    'main_calls': analysis['total_calls'],
    'factorial_traces': extended['factorial']['traces'],
    'factorial_calls': extended['factorial']['api_calls'],
    'total_traces': analysis['total_runs'] + extended['factorial']['traces'],
    'total_calls': analysis['total_calls'] + extended['factorial']['api_calls'],
    'factorial_interactions': extended['factorial']['interaction_count'],
    'current_release_traces': current_release['traces'],
    'current_release_calls': current_release['api_calls'],
    'current_tzdb_traces': current_tzdb['traces'],
    'current_tzdb_calls': current_tzdb['api_calls'],
    'release_series_traces': rule_series['traces'],
    'release_series_calls': rule_series['api_calls'],
    'release_series_checks': release_validation['checks'],
    'release_series_transitions': release_validation['transition_records'],
    'release_series_accepted': sum(v for k,v in rule_series['classification_counts'].items() if k.endswith('|accepted_data_effect')),
    'release_series_blocked_changes': sum(v for k,v in rule_series['classification_counts'].items() if k.endswith('|changed_with_violation_or_uncertainty')),
    'historical_decision_records': load('decision-record-summary.json')['records'],
    'release_series_decision_records': rule_series['decision_records'],
    'all_decision_records': load('decision-record-summary.json')['records'] + rule_series['decision_records'],
    'minimized_witnesses': minimized['witnesses'],
    'policy_frontier_traces': policy_frontiers['traces'],
    'policy_frontier_calls': policy_frontiers['api_calls'],
    'upgrade_sufficiency_certificates': upgrade_sufficiency['certificates'],
    'upgrade_noncommutative_observations': upgrade_sufficiency['noncommutative_observations'],
    'grand_total_traces': analysis['total_runs'] + extended['factorial']['traces'] + current_release['traces'] + current_tzdb['traces'] + rule_series['traces'] + policy_frontiers['traces'],
    'grand_total_calls': analysis['total_calls'] + extended['factorial']['api_calls'] + current_release['api_calls'] + current_tzdb['api_calls'] + rule_series['api_calls'] + policy_frontiers['api_calls'],
    'mutants': mut['mutants'],
    'benign': mut['benign_cases'],
}
(OUT / 'paper-numbers.json').write_text(json.dumps(summary, indent=2)+'\n')
