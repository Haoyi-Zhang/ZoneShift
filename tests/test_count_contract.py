"""Owned offline bound checks; no scheduler calls or spawned processes."""
import unittest
from unittest.mock import patch

import zoneshift.__main__ as cli
from zoneshift.contracts import Contract
from zoneshift.execution import run_trace, validate_count


class CountContractTests(unittest.TestCase):
    def test_invalid_bounds_are_rejected_without_scheduler_execution(self):
        contract=Contract((5,), (0,), gap='skip', fold='both')
        for count in (True, False, 1.0, 1.9, '8', None, [], {}, 0, -1, 257):
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, 'integer in 1..256'):
                    run_trace('aps-3.11.3', None, contract, 1704067200, count)

    def test_single_and_upgrade_reject_before_any_cell_or_zone_is_loaded(self):
        base={'contract':{'hours':[5], 'minutes':[0], 'gap':'skip', 'fold':'both'}}
        for entry in (cli._single, cli._upgrade):
            for count in (True, 1.0, 1.9, '8', None, 0, 257):
                with self.subTest(entry=entry.__name__, count=count):
                    with patch.object(cli, '_execute_cell', side_effect=AssertionError('cell executed')):
                        with patch.object(cli, 'load_zone', side_effect=AssertionError('zone loaded')):
                            with self.assertRaisesRegex(ValueError, 'integer in 1..256'):
                                entry({**base, 'count':count})

    def test_single_keeps_the_exact_valid_declared_bound(self):
        base={'implementation':'aps-3.11.3', 'tzdb':'2024a', 'zone':'Etc/UTC',
              'start':'2024-01-01T00:00',
              'contract':{'hours':[5], 'minutes':[0], 'gap':'skip', 'fold':'both'}}
        for count in (1, 8, 256):
            with self.subTest(count=count):
                with patch.object(cli, '_execute_cell', return_value={'qualification':{'status':'PASS'}}) as cell:
                    result, code=cli._single({**base, 'count':count})
                self.assertEqual(cell.call_args.args[-1], count)
                self.assertEqual(result['input']['count'], count)
                self.assertEqual(code, 0)
                self.assertEqual(validate_count(count), count)


if __name__=='__main__':
    unittest.main()
