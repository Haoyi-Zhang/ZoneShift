"""The manuscript cohort ledger rejects merged or drifting result populations."""
import json
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / 'scripts/study_denominators.py'))


def inputs():
    return {name: json.loads((ROOT / 'results' / name).read_text(encoding='utf-8'))
            for name in MODULE['FILES']}


def test_all_current_denominators_stay_separate():
    result = MODULE['derive'](inputs())
    assert (result['base_traces'], result['base_calls']) == (53400, 422592)
    assert len(result['base_components']) == 6
    assert (result['native_traces'], result['native_calls']) == (1368, 10944)
    assert (result['witnesses'], result['witness_calls']) == (43, 426)
    assert result['decision_records'] == 7032
    assert result['new_requalification_calls'] == 0
    table = MODULE['render'](result)
    assert 'Native comparison (traces)' in table
    assert 'Witness validation (witnesses)' in table


@pytest.mark.parametrize('change', ['base', 'native_count', 'native_calls', 'witnesses', 'decisions', 'requalification'])
def test_count_drift_is_rejected_before_table_generation(change):
    data = inputs()
    if change == 'base':
        data['analysis.json']['total_runs'] += 1
    elif change == 'native_count':
        data['native-cronsim-comparison.json']['runs'].pop()
    elif change == 'native_calls':
        data['native-cronsim-comparison.json']['runs'][0]['calls'] -= 1
    elif change == 'witnesses':
        data['minimized-witnesses.json']['witnesses'].pop()
    elif change == 'decisions':
        data['decision-record-summary.json']['records'] += 1
    else:
        data['native-cronsim-comparison.json']['summary']['requalification']['new_scheduler_calls'] = 1
    with pytest.raises(ValueError):
        MODULE['derive'](data)
