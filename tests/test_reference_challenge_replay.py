"""Offline calendar and declared-domain replay regressions; no scheduler calls."""
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_extended, run_policy_attribution
from scripts.check_reproduction import strip_runtime
from zoneshift.contracts import COMPLETE_GAP_POLICIES, Contract
from zoneshift.tzif import Transition

ROOT = Path(__file__).resolve().parents[1]


class NoPlatformTimestamp(datetime):
    @classmethod
    def fromtimestamp(cls, *args, **kwargs):
        raise AssertionError("UTC year lookup must not call platform fromtimestamp")


class ReferenceChallengeReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retained = json.loads((ROOT / 'results/policy-matrix.json').read_text(encoding='utf-8'))
        cls.outputs = []
        with patch.object(run_extended, 'dump', lambda path, value: cls.outputs.append(path.name)), \
             patch.object(run_extended, 'datetime', NoPlatformTimestamp), \
             patch.object(run_extended, 'run_trace', side_effect=AssertionError('No scheduler calls')):
            cls.replayed = run_extended.policy_matrix(Path('in-memory'))
            cls.current = run_extended.policy_matrix(Path('in-memory'), domain='current')

    def test_retained_rows_and_metadata_match_exactly(self):
        self.assertEqual(len(self.replayed['fold_rows']), 528)
        self.assertEqual(len(self.replayed['gap_rows']), 528)
        # Do not omit labels, row order, reasons or supporting completions.
        self.assertEqual(strip_runtime(self.replayed), strip_runtime(self.retained))
        # This reference-only file has no runtime fields: equality is exact.
        self.assertEqual(self.replayed, self.retained)

    def test_recovered_positions_and_menus_are_explicit(self):
        self.assertEqual(self.replayed['complete_gap_policies'], ['skip', 'shift_forward', 'shift_backward'])
        self.assertEqual(self.replayed['complete_fold_policies'], ['both', 'first', 'second'])
        for kind in ('fold', 'gap'):
            unique = {(r['zone'], r['transition'], r['label']) for r in self.replayed[kind + '_rows']}
            self.assertEqual(len(unique), 44)
            for name, utc, label in unique:
                zone = run_extended.TZif(ROOT / 'data/tzdb/2024a' / name)
                tr = next(t for t in zone.transitions if t.utc == utc)
                self.assertEqual(label, run_extended.minute_inside(utc + min(tr.before, tr.after),
                                                                  utc + max(tr.before, tr.after)).isoformat())

    def test_current_midpoint_domain_does_not_replace_historical_result(self):
        self.assertEqual(self.outputs, ['policy-matrix.json', 'policy-matrix-current.json'])
        self.assertEqual(self.current['challenge_domain'], 'current-four-gap-midpoint')
        self.assertEqual(len(self.current['gap_rows']), 880)
        self.assertEqual(len(self.current['fold_rows']), 528)
        clamp = [r for r in self.current['gap_rows']
                 if r['trace_policy'] == 'clamp_forward' and r['checked_policy'] == 'unspecified']
        self.assertEqual(len(clamp), 44)
        self.assertTrue(all(r['passing_completions'] == [{'gap': 'clamp_forward', 'fold': 'both'}] for r in clamp))

    def test_current_checker_keeps_all_four_gap_policies(self):
        self.assertEqual(COMPLETE_GAP_POLICIES, ('skip', 'shift_forward', 'shift_backward', 'clamp_forward'))
        self.assertEqual(len(Contract((2,), (30,)).completions()), 12)
        Contract((2,), (30,), gap='clamp_forward', fold='both')

    def test_frontier_driver_skips_old_calendar_year_without_native_execution(self):
        old = Transition(-1773012580, -1820, 0)
        admitted = Transition(1710054000, -18000, -14400)
        fixture = SimpleNamespace(transitions=[old, admitted])
        with patch.object(run_policy_attribution, 'datetime', NoPlatformTimestamp), \
             patch.object(run_policy_attribution, 'corpus_zones', return_value=['in-memory-zone']), \
             patch.object(run_policy_attribution, 'TZif', return_value=fixture), \
             patch.object(run_policy_attribution, 'load_zone', return_value=object()), \
             patch.object(run_policy_attribution, 'IMPLEMENTATIONS', ()), \
             patch.object(run_policy_attribution, 'Contract', wraps=Contract) as constructed, \
             patch.object(run_policy_attribution, 'run_trace', side_effect=AssertionError('No scheduler calls')), \
             patch.object(run_policy_attribution, 'dump', return_value=None):
            result = run_policy_attribution.policy_frontier_study(Path('in-memory'))
        self.assertEqual(constructed.call_count, 1)
        self.assertEqual(result['traces'], 0)
        self.assertEqual(result['api_calls'], 0)

    def test_reference_mutation_year_scan_avoids_platform_timestamp(self):
        with patch.object(run_extended, 'datetime', NoPlatformTimestamp), \
             patch.object(run_extended, 'run_trace', side_effect=AssertionError('No scheduler calls')), \
             patch.object(run_extended, 'dump', return_value=None):
            result = run_extended.mutation_study(Path('in-memory'))
        self.assertEqual(result['mutants'], 651)
        self.assertEqual(result['detected'], 651)

    def test_unknown_challenge_domain_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown reference-challenge domain'):
            run_extended.policy_matrix(Path('in-memory'), domain='unknown')


if __name__ == '__main__':
    unittest.main()
