#!/usr/bin/env python3
"""Replay one compact ZoneShift regression-pack witness offline."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from zoneshift.contracts import Contract, qualify
from zoneshift.execution import load_zone, run_trace
from zoneshift.tzif import TZif


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--study', required=True)
    p.add_argument('--case-id', required=True)
    p.add_argument('--implementation', required=True)
    p.add_argument('--pack', type=Path, default=ROOT/'results'/'regression-pack.json')
    args = p.parse_args()
    pack = json.loads(args.pack.read_text())
    matches = [r for r in pack['records'] if r['study']==args.study and
               r['case_id']==args.case_id and r['implementation']==args.implementation]
    if len(matches) != 1:
        raise SystemExit(f'expected one record, found {len(matches)}')
    rec = matches[0]
    c = Contract(tuple(rec['contract']['hours']), tuple(rec['contract']['minutes']),
                 gap=rec['contract']['gap'], fold=rec['contract']['fold'])
    zone = load_zone(rec['tzdb'], rec['zone'])
    reference = TZif(ROOT/'data'/'tzdb'/rec['tzdb']/rec['zone'])
    run = run_trace(rec['implementation'], zone, c, rec['start'])
    verdict = qualify(reference, c, rec['start'], run['trace'], run['error'])
    payload = json.dumps(run['trace'], sort_keys=True, separators=(',', ':')).encode()
    digest = hashlib.sha256(payload).hexdigest()
    ok = (digest == rec['trace_sha256'] and verdict['status'] == rec['verdict'] and
          run['trace'] == rec['expected_trace'])
    print(json.dumps({'ok': ok, 'trace_sha256': digest, 'verdict': verdict,
                      'error': run['error'], 'calls': run['calls']}, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
