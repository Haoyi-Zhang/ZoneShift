"""Small offline routing/geometry regressions; no scheduler or study execution."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def intersects_interior(p, q, box):
    """Segment/open rectangle intersection (boundary contact is allowed)."""
    lo, hi = 0.0, 1.0
    for start, stop, lower, upper in zip(p, q, box[:2], box[2:]):
        delta = stop - start
        if abs(delta) < 1e-12:
            if not lower < start < upper:
                return False
        else:
            a, b = sorted(((lower - start) / delta, (upper - start) / delta))
            lo, hi = max(lo, a), min(hi, b)
            if lo >= hi - 1e-12:
                return False
    return lo < hi - 1e-12


class WorkflowGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module('workflow_geometry', ROOT / 'plots/draw_workflow.py')

    def drawing(self):
        module = self.module
        original_arrow = module.Drawing.arrow
        routes = []

        def record(drawing, p, q, dashed=False, via=()):
            routes.append((tuple(p), *map(tuple, via), tuple(q)))
            return original_arrow(drawing, p, q, dashed, via)

        with mock.patch.object(module.Drawing, 'arrow', record):
            # autospec retains the Drawing instance passed to save.
            with mock.patch.object(module.Drawing, 'save', autospec=True) as capture:
                module.workflow(Path('.'))
            drawing = capture.call_args.args[0]
        return drawing, routes

    def test_data_effect_uses_fixed_code_vertical_pair(self):
        d, routes = self.drawing()
        try:
            no, nn = d.point('no', 'c'), d.point('nn', 'c')
            midpoint = ((no[0] + nn[0]) / 2, (no[1] + nn[1]) / 2)
            self.assertEqual(midpoint, (8.35, 1.9))
            data_routes = [r for r in routes if r[-1] == d.point('col', 'w')]
            self.assertEqual(len(data_routes), 1)
            self.assertEqual(data_routes[0][0], midpoint)
            self.assertNotIn((d.point('nn', 'e'), d.point('col', 'w')), routes)
            self.assertIn((d.point('no', 'e'), d.point('row', 'w')), routes)
            for name in ('oo', 'no', 'on', 'nn', 'contract', 'decision'):
                self.assertIn(name, d.nodes)
        finally:
            self.module.plt.close(d.fig)

    def test_data_route_avoids_labels_and_node_interiors(self):
        d, routes = self.drawing()
        try:
            route = next(r for r in routes if r[-1] == d.point('col', 'w'))
            d.fig.canvas.draw()
            renderer = d.fig.canvas.get_renderer()
            boxes = [(name, (x-w/2, y-h/2, x+w/2, y+h/2))
                     for name, (x, y, w, h, _) in d.nodes.items()]
            for artist, _ in d.labels:
                b = artist.get_window_extent(renderer).transformed(d.ax.transData.inverted())
                boxes.append((artist.get_text(), (b.x0-.025, b.y0-.025, b.x1+.025, b.y1+.025)))
            for p, q in zip(route, route[1:]):
                for name, box in boxes:
                    self.assertFalse(intersects_interior(p, q, box), (p, q, name))
        finally:
            self.module.plt.close(d.fig)


class AggregateOutputTests(unittest.TestCase):
    def test_only_scientific_json_csv_outputs(self):
        module = load_module('aggregate_output_route', ROOT / 'scripts/aggregate.py')
        implementations = ['aps-3.11.0', 'aps-3.11.1', 'aps-3.11.2',
                           'croniter-1.3.10', 'croniter-2.0.1']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'results').mkdir()
            (root / 'configs').mkdir()
            runs, summary = [], []
            for i, impl in enumerate(implementations):
                runs.append(dict(strategy='boundary', implementation=impl,
                                 case_id='ordinary-fixture', calls=2,
                                 policy_blind_alarm=0, trace=[{'timestamp': 1}],
                                 qualification={'status': 'PASS', 'reasons': []},
                                 kind='ordinary', profile='daily', zone='Etc/UTC', error=None))
                summary.extend([dict(strategy='boundary', implementation=impl,
                                     violation=0, underspecified=0, median_us=i+1),
                                dict(strategy='uniform', implementation=impl, violation=i)])
            (root / 'results/runs.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in runs))
            (root / 'results/benchmark-summary.json').write_text(json.dumps(summary))
            (root / 'results/intervention.json').write_text(json.dumps([
                {'before': {'elapsed_ns': 2000}, 'after_elapsed_ns': 1000}]))
            (root / 'configs/protocol.json').write_text(json.dumps(
                {'discovery_zones': [], 'extension_zones': []}))
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with mock.patch.object(module, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                module.main()
            after = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertFalse((root / 'paper').exists())
            self.assertEqual(set(after)-set(before), {Path('results/analysis.json'), Path('results/principal-table.csv')})
            for path, content in before.items():
                self.assertEqual(after[path], content)
            result = json.loads(after[Path('results/analysis.json')])
            self.assertEqual((result['total_runs'], result['total_calls']), (5, 10))
            self.assertEqual([x['uniform_mean'] for x in result['table']], list(range(5)))
            self.assertTrue(all(c['counts'] == {'same': 1, 'same:PASS:PASS': 1} for c in result['comparisons']))
            self.assertEqual(result['intervention_cost']['before_median_us'], 2)
            self.assertEqual(result['intervention_cost']['after_median_us'], 1)


if __name__ == '__main__':
    unittest.main()
