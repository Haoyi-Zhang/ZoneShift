"""Bounded plotting-route tests; no subject, timing, resampling, or font install."""
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "plot_inputs/signature-budget.dat"
SCRIPT = ROOT / "scripts/render_signature_budget.py"
spec = importlib.util.spec_from_file_location("render_signature_budget_under_test", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PlotRouteTests(unittest.TestCase):
    def test_retained_values_and_order(self):
        data = module.load_data(SOURCE)
        self.assertEqual([row[0] for row in data], [16, 32, 64, 128, 256, 512, 1120])
        self.assertEqual(data[0], (16, 3.011, .125))

    def test_invalid_input_is_not_silently_plotted(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / SOURCE.name
            source.write_text(SOURCE.read_text(encoding="utf-8").replace("3.011000", "nan"), encoding="utf-8")
            with self.assertRaises(ValueError):
                module.load_data(source)

    def test_missing_font_fails_before_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "uncreated"
            with self.assertRaises(FileNotFoundError):
                module.main(["--source", str(SOURCE), "--output-dir", str(output), "--font-root", str(Path(directory) / "absent")])
            self.assertFalse(output.exists())

    def test_required_paths_have_no_implicit_output(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit) as raised:
            module.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_output_routing_keeps_drawing_contract_and_source(self):
        before = SOURCE.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            self.check_drawing(Path(directory) / "vectors")
        self.assertEqual(SOURCE.read_bytes(), before)

    def check_drawing(self, output):
        with mock.patch.object(module, "require_fonts"), mock.patch.object(module.pdfmetrics, "EmbeddedType1Face"), mock.patch.object(module.pdfmetrics, "Font"), mock.patch.object(module.pdfmetrics, "registerTypeFace"), mock.patch.object(module.pdfmetrics, "registerFont"), mock.patch.object(module.canvas, "Canvas") as canvas:
            module.main(["--source", str(SOURCE), "--output-dir", str(output), "--font-root", str(output / "fonts")])
        self.assertEqual(canvas.call_args.args[0], str(output / "signature-budget.pdf"))
        self.assertEqual(canvas.call_args.kwargs["pagesize"], (252, 4.7 * 72 / 2.54))
        self.assertEqual(canvas.call_args.kwargs["invariant"], 1)


if __name__ == "__main__":
    unittest.main()
