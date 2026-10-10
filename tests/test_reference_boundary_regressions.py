"""Owned mathematical fixtures; no TZif payloads, schedulers, or campaigns."""
from datetime import datetime, timedelta
import unittest

from zoneshift.attribution import classify_upgrade_square
from zoneshift.contracts import Contract, policy_completion_frontier, qualify, reference, required
from zoneshift.tzif import EPOCH, MAX_TIME, MIN_TIME, TZif, _recurring_tail, _rule_seconds


class RollbackZone:
    """Small piecewise-offset model with a two-date civil rollback."""
    offsets = [-20 * 3600, 20 * 3600]

    def __init__(self, start):
        self.transition = start + 3600

    def offset_at(self, utc):
        return self.offsets[1] if utc < self.transition else self.offsets[0]

    def wall(self, utc):
        return EPOCH + timedelta(seconds=utc + self.offset_at(utc))

    def resolve(self, label):
        local = (label - EPOCH).total_seconds()
        return sorted(local - off for off in self.offsets
                      if self.offset_at(local - off) == off)

    def gap_projection_map(self, label):
        return {}


class ReferenceBoundaryRegressions(unittest.TestCase):
    def recurring_zone(self, standard, seasonal, start_rule, end_rule):
        initial, transitions = _recurring_tail(standard, seasonal, start_rule, end_rule, MIN_TIME - 1)
        zone = object.__new__(TZif)
        zone.times = []
        zone.types = [(standard, 0, 0)]
        zone.fixed_tail = None
        zone.tail_initial = initial
        zone.tail_transitions = transitions
        zone.transitions = transitions
        zone.offsets = sorted({standard, seasonal})
        return zone

    def fixed_zone(self):
        zone = object.__new__(TZif)
        zone.times = []
        zone.types = [(0, 0, 0)]
        zone.fixed_tail = 0
        zone.tail_initial = 0
        zone.tail_transitions = []
        zone.transitions = []
        zone.offsets = [0]
        return zone

    def test_southern_footer_initial_state_matches_first_transition(self):
        zone = self.recurring_zone(36000, 39600, (10, 1, 0, 7200), (3, 1, 0, 7200))
        first = zone.tail_transitions[0]
        self.assertEqual(zone.offset_at(MIN_TIME), 39600)
        self.assertEqual(zone.offset_at(first.utc - 1), first.before)
        self.assertEqual(zone.offset_at(first.utc), first.after)
        for left, right in zip(zone.tail_transitions, zone.tail_transitions[1:]):
            self.assertEqual(left.after, right.before)
        self.assertLess(zone.tail_transitions[-1].utc, MAX_TIME)

    def test_northern_footer_keeps_standard_initial_state(self):
        zone = self.recurring_zone(0, 3600, (3, 2, 0, 7200), (11, 1, 0, 7200))
        self.assertEqual(zone.offset_at(MIN_TIME), 0)
        self.assertEqual(zone.offset_at(zone.tail_transitions[0].utc - 1), 0)
        self.assertEqual(zone.offset_at(zone.tail_transitions[0].utc), 3600)

    def test_prior_year_rule_spillover_initial_state_and_qualification(self):
        zone = self.recurring_zone(0, 3600, _rule_seconds("M10.1.0/2"),
                                   _rule_seconds("M12.5.0/167"))
        # 1969's last Sunday in December is the 28th; +167 h - 1 h seasonal offset.
        expected_end = int((datetime(1970, 1, 3, 22) - EPOCH).total_seconds())
        self.assertEqual(zone.tail_transitions[0].utc, expected_end)
        self.assertEqual((zone.tail_transitions[0].before, zone.tail_transitions[0].after), (3600, 0))
        self.assertEqual(zone.offset_at(MIN_TIME), 3600)
        self.assertEqual(zone.offset_at(expected_end - 1), 3600)
        self.assertEqual(zone.offset_at(expected_end), 0)
        for left, right in zip(zone.tail_transitions, zone.tail_transitions[1:]):
            self.assertEqual(left.after, right.before)
        self.assertTrue(all(MIN_TIME <= tr.utc < MAX_TIME for tr in zone.tail_transitions))
        contract = Contract((0,), (0,), gap="skip", fold="both")
        self.assertEqual(qualify(zone, contract, 0, [{"timestamp": 82800}])["status"], "PASS")
        wrong = qualify(zone, contract, 0, [{"timestamp": 86400}])
        self.assertEqual(wrong["status"], "VIOLATION")
        self.assertIn("off_recurrence", wrong["reasons"])
        self.assertIn(82800, wrong["missing"])

    def test_recurring_tail_preserves_last_and_upper_bound_spillovers(self):
        start_rule, end_rule = _rule_seconds("M10.1.0/2"), _rule_seconds("M12.5.0/167")
        expected_end = int((datetime(1970, 1, 3, 22) - EPOCH).total_seconds())
        for last in (expected_end - 1, expected_end):
            with self.subTest(last=last):
                initial, transitions = _recurring_tail(0, 3600, start_rule, end_rule, last)
                self.assertTrue(all(last < tr.utc < MAX_TIME for tr in transitions))
                self.assertEqual(initial, 3600 if last < expected_end else 0)
                self.assertEqual(transitions[0].utc == expected_end, last < expected_end)
        # 2037's first Sunday in January is the 4th; -167 h - 1 h spills into 2036.
        expected_upper = int((datetime(2036, 12, 28) - EPOCH).total_seconds())
        _, transitions = _recurring_tail(0, 3600, _rule_seconds("M3.2.0/2"),
                                         _rule_seconds("M1.1.0/-167"), MAX_TIME - 8 * 86400)
        self.assertEqual([tr.utc for tr in transitions], [expected_upper])
        self.assertTrue(all(MIN_TIME <= tr.utc < MAX_TIME for tr in transitions))

    def test_reference_rejects_nonfinite_and_out_of_range_starts(self):
        zone = self.fixed_zone()
        complete = Contract((0,), (0,), gap="skip", fold="both")
        incomplete = Contract((0,), (0,))
        for start in (-1, -0.5, MAX_TIME, MAX_TIME + 0.5, float("nan"),
                      float("inf"), -float("inf")):
            with self.subTest(start=start):
                with self.assertRaisesRegex(ValueError, "1970--2036"):
                    reference(zone, complete, start, count=1)
                for contract in (complete, incomplete):
                    for trace, error in (([{"timestamp": 0}], None), ([], None),
                                         ([], "owned-error")):
                        with self.subTest(complete=contract.complete, trace=trace, error=error):
                            with self.assertRaisesRegex(ValueError, "1970--2036"):
                                qualify(zone, contract, start, trace, error)
                with self.assertRaisesRegex(ValueError, "1970--2036"):
                    policy_completion_frontier(zone, incomplete, start, [])

    def test_reference_keeps_supported_boundaries_and_64_date_cap(self):
        zone = self.fixed_zone()
        contract = Contract((0,), (0,), gap="skip", fold="both")
        for start, timestamp in ((MIN_TIME, 86400), (MAX_TIME - 2 * 86400, MAX_TIME - 86400)):
            with self.subTest(start=start):
                result = qualify(zone, contract, start, [{"timestamp": timestamp}])
                self.assertEqual(result["status"], "PASS")
                events, _ = reference(zone, contract, start, count=1, through=timestamp)
                self.assertTrue(all(MIN_TIME <= event["timestamp"] < MAX_TIME for event in events))
        with self.assertRaisesRegex(ValueError, "Reference horizon exhausted"):
            reference(zone, contract, MAX_TIME - 1, count=1)

        class NoOccurrenceZone:
            offsets = [0]

            def __init__(self):
                self.labels = []

            def resolve(self, label):
                self.labels.append(label)
                return []

            def gap_projection_map(self, label):
                return {}

        empty = NoOccurrenceZone()
        with self.assertRaisesRegex(ValueError, "Reference horizon exhausted"):
            reference(empty, contract, MIN_TIME, count=1)
        self.assertEqual(len({label.date() for label in empty.labels}), 64)

    def test_full_offset_span_covers_future_earlier_civil_date(self):
        start = (datetime(2024, 1, 4, 6) - EPOCH).total_seconds()
        zone = RollbackZone(start)
        contract = Contract((12,), (0,), gap="skip", fold="both")
        expected = (datetime(2024, 1, 4, 8) - EPOCH).total_seconds()
        for through in (None, expected + 86400):
            events, _ = reference(zone, contract, start, count=2, through=through)
            self.assertEqual(required(events, contract)[0], expected)
            first = events[0]
            self.assertEqual(first["label"], "2024-01-03T12:00:00")
            self.assertGreater(first["timestamp"], start)

    def test_qualification_does_not_ignore_the_earlier_occurrence(self):
        start = (datetime(2024, 1, 4, 6) - EPOCH).total_seconds()
        zone = RollbackZone(start)
        contract = Contract((12,), (0,), gap="skip", fold="both")
        first = start + 7200
        self.assertEqual(qualify(zone, contract, start, [{"timestamp": first}])["status"], "PASS")
        omitted = qualify(zone, contract, start, [{"timestamp": first + 86400}])
        self.assertEqual(omitted["status"], "VIOLATION")
        self.assertIn("missing_required_occurrence", omitted["reasons"])
        self.assertIn(first, omitted["missing"])

    def test_flag_is_sequence_presence_not_qualification_reversal(self):
        statuses = {"old_code_old_data": "VIOLATION", "new_code_old_data": "PASS",
                    "old_code_new_data": "PASS", "new_code_new_data": "VIOLATION"}
        traces = {"old_code_old_data": (1.0,), "new_code_old_data": (2.0,),
                  "old_code_new_data": (3.0,), "new_code_new_data": (4.0,)}
        result = classify_upgrade_square(statuses, traces)
        self.assertFalse(result["noncommutative_observation"])
        self.assertEqual(result["minimal_sufficient_changes"], [["code"], ["data"]])
        self.assertEqual(result["target_status"], "VIOLATION")
        self.assertEqual(result["code_effect_by_data"], {"old_data": True, "new_data": True})

    def test_masked_sequence_presence_is_flagged(self):
        statuses = {"old_code_old_data": "VIOLATION", "new_code_old_data": "PASS",
                    "old_code_new_data": "PASS", "new_code_new_data": "PASS"}
        traces = {"old_code_old_data": (1.0,), "new_code_old_data": (2.0,),
                  "old_code_new_data": (3.0,), "new_code_new_data": (3.0,)}
        self.assertTrue(classify_upgrade_square(statuses, traces)["noncommutative_observation"])


if __name__ == "__main__":
    unittest.main()
