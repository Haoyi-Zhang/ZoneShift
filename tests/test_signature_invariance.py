"""Sampling labels cannot create a new behavioural class."""
import copy
import json
from pathlib import Path
from scripts.run_release_analysis import behaviour_signature


def test_signature_ignores_sampler_metadata():
    root = Path(__file__).resolve().parents[1]
    row = next(json.loads(line) for line in (root / 'results/runs.jsonl').open()
               if json.loads(line)['qualification']['status'] == 'VIOLATION')
    changed = copy.deepcopy(row)
    changed.update(kind='uniform', transition_delta=0, anchor_offset=987654)
    assert behaviour_signature(row) == behaviour_signature(changed)
