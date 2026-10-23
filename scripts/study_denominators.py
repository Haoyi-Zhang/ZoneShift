"""Keep recorded campaigns, reanalysis and witness replay denominators separate."""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]
FILES = ('analysis.json', 'extended-analysis.json', 'policy-frontiers.json',
         'rule-release-series.json', 'native-cronsim-comparison.json',
         'minimized-witnesses.json', 'decision-record-summary.json')


def derive(inputs):
    main = inputs['analysis.json']
    extended = inputs['extended-analysis.json']
    frontier = inputs['policy-frontiers.json']['summary']
    series = inputs['rule-release-series.json']['summary']
    native = inputs['native-cronsim-comparison.json']
    witnesses = inputs['minimized-witnesses.json']
    base = [(main['total_runs'], main['total_calls'])]
    base.extend((extended[name]['traces'], extended[name]['api_calls'])
                for name in ('factorial', 'current_release', 'current_tzdb'))
    base.extend((data['traces'], data['api_calls']) for data in (series, frontier))
    if any(type(value) is not int or value < 0 for row in base for value in row):
        raise ValueError('Recorded denominator must be a nonnegative integer')
    total = tuple(sum(row[index] for row in base) for index in (0, 1))
    if total != (53400, 422592):
        raise ValueError('Base-study components disagree with the manuscript cohort')
    runs, summary = native['runs'], native['summary']
    if (len(runs) != summary['traces'] or sum(row['calls'] for row in runs) != summary['api_calls']
            or (summary['traces'], summary['api_calls']) != (1368, 10944)):
        raise ValueError('Native-comparison raw counts and summary differ')
    if summary['requalification']['new_scheduler_calls'] != 0:
        raise ValueError('Requalification cannot be counted as new scheduler execution')
    if (len(witnesses['witnesses']) != witnesses['summary']['witnesses'] or
            (witnesses['summary']['witnesses'], witnesses['summary']['replay_validation_api_calls']) != (43, 426)):
        raise ValueError('Witness replay denominator differs')
    decisions = inputs['decision-record-summary.json']['records'] + series['decision_records']
    if decisions != 7032:
        raise ValueError('Decision-ledger batches differ from published total')
    return {'base_traces': total[0], 'base_calls': total[1],
            'base_components': base, 'native_traces': len(runs),
            'native_calls': summary['api_calls'], 'witnesses': len(witnesses['witnesses']),
            'witness_calls': witnesses['summary']['replay_validation_api_calls'],
            'decision_records': decisions, 'new_requalification_calls': 0}


def render(result):
    rows = [r'\begin{table*}[t]', r'\centering\footnotesize',
            r'\caption{Separate evidence cohorts and their retained result inputs.}',
            r'\label{tab:cohorts}', r'\begin{tabular}{p{.20\textwidth}rr>{\raggedright\arraybackslash}p{.49\textwidth}}',
            r'\toprule', r'Evidence cohort & Units & API calls & Result inputs under \path{results/} \\',
            r'\midrule',
            r'Base study (traces) & 53,400 & 422,592 & \path{analysis.json}; \path{extended-analysis.json}; \path{policy-frontiers.json}; \path{rule-release-series.json} \\',
            r'Native comparison (traces) & 1,368 & 10,944 & \path{native-cronsim-comparison.json} \\',
            r'Witness validation (witnesses) & 43 & 426 & \path{minimized-witnesses.json} \\',
            r'Decision ledger (records) & 7,032 & -- & \path{decision-record-summary.json};\newline \path{release-series-decisions.jsonl} \\',
            r'\bottomrule', r'\end{tabular}', r'\end{table*}']
    return '\n'.join(rows) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper-dir', type=Path)
    args = parser.parse_args()
    inputs = {name: json.loads((ROOT / 'results' / name).read_text(encoding='utf-8')) for name in FILES}
    result = derive(inputs)
    if args.paper_dir is not None:
        output = args.paper_dir / 'generated/study-denominators.tex'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render(result), encoding='utf-8', newline='\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
