"""Owned offline regressions; no scheduler calls or study campaigns."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_reproduction
from scripts.run_extended import integration_metrics


class SemanticComparisonTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "source": {"path": "vendor/released-module.py", "sha256": "a" * 64},
            "zone_file_sha256": "b" * 64,
            "contract": {"occurrences": 8, "gap": "skip", "fold": "both"},
            "start": 1704067200.0,
            "cells": [{
                "run": {
                    "runner": "spawned-process",
                    "startup_ns": 1000000,
                    "elapsed_ns": 2000000,
                    "calls": 2,
                    "error": None,
                    "trace": [
                        {"timestamp": 1704085200.0, "iso": "2024-01-01T05:00:00+00:00", "fold": 0},
                        {"timestamp": 1704171600.0, "iso": "2024-01-02T05:00:00+00:00", "fold": 0},
                    ],
                },
                "qualification": {"status": "PASS", "reasons": []},
            }],
            "after_elapsed_ns": 3000000,
        }

    def semantic_digest(self, value):
        # Exercise both actual JSON loaders and recursive canonicalization.
        # The production result list is narrowed only inside this fixture.
        with tempfile.TemporaryDirectory(prefix="zoneshift-semantic-test-") as temp:
            root = Path(temp)
            (root / "runs.jsonl").write_text(json.dumps(value) + "\n", encoding="utf-8")
            (root / "historical.json").write_text(
                json.dumps({"squares": [value]}), encoding="utf-8"
            )
            with patch.object(check_reproduction, "FILES", ["runs.jsonl", "historical.json"]):
                return check_reproduction.digest(root)[0]

    def test_nested_startup_cost_is_ignored_without_mutating_records(self):
        original = copy.deepcopy(self.record)
        changed = copy.deepcopy(self.record)
        changed["cells"][0]["run"]["startup_ns"] = 987654321
        self.assertEqual(self.semantic_digest(original), self.semantic_digest(changed))
        runtime_only = copy.deepcopy(self.record)
        runtime_only["cells"][0]["run"]["elapsed_ns"] = 876543210
        runtime_only["after_elapsed_ns"] = 765432109
        self.assertEqual(self.semantic_digest(original), self.semantic_digest(runtime_only))
        canonical = check_reproduction.strip_runtime(original)
        self.assertNotIn("startup_ns", canonical["cells"][0]["run"])
        self.assertEqual(canonical["cells"][0]["run"]["runner"], "spawned-process")
        self.assertEqual(canonical["source"], original["source"])
        self.assertEqual(original, self.record)
        self.assertEqual(changed["cells"][0]["run"]["startup_ns"], 987654321)

    def test_nested_scientific_and_source_changes_remain_visible(self):
        changes = [
            (("cells", 0, "run", "trace", 0, "timestamp"), 1704085201.0),
            (("cells", 0, "run", "trace", 0, "iso"), "different-civil-label"),
            (("cells", 0, "run", "trace", 0, "fold"), 1),
            (("cells", 0, "run", "trace"), list(reversed(self.record["cells"][0]["run"]["trace"]))),
            (("cells", 0, "qualification", "status"), "VIOLATION"),
            (("cells", 0, "qualification", "reasons"), ["off_recurrence"]),
            (("source", "sha256"), "c" * 64),
            (("zone_file_sha256",), "d" * 64),
            (("source", "path"), "vendor/other-release.py"),
            (("cells", 0, "run", "runner"), "other-runner"),
            (("cells", 0, "run", "calls"), 1),
            (("cells", 0, "run", "error"), "timeout"),
            (("contract", "occurrences"), 4),
            (("contract", "fold"), "first"),
            (("start",), 1704067201.0),
        ]
        baseline = self.semantic_digest(self.record)
        for keys, replacement in changes:
            with self.subTest(field=keys):
                changed = copy.deepcopy(self.record)
                node = changed
                for key in keys[:-1]:
                    node = node[key]
                node[keys[-1]] = replacement
                self.assertNotEqual(baseline, self.semantic_digest(changed))

    def test_missing_result_file_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory(prefix="zoneshift-semantic-test-") as temp:
            with patch.object(check_reproduction, "FILES", ["runs.jsonl"]):
                with self.assertRaises(FileNotFoundError):
                    check_reproduction.digest(Path(temp))


class CurrentSizeTests(unittest.TestCase):
    def test_complete_core_file_set_matches_both_derived_size_records(self):
        root = Path(__file__).resolve().parents[1]
        expected = {
            path.relative_to(root).as_posix(): sum(
                bool(line.strip()) and not line.lstrip().startswith("#")
                for line in path.read_text().splitlines()
            )
            for path in (root / "zoneshift").glob("*.py")
        }
        with tempfile.TemporaryDirectory(prefix="zoneshift-size-test-") as temp:
            measured = integration_metrics(Path(temp))
        self.assertEqual(measured["core_python_sloc_nonblank_noncomment"], expected)
        self.assertIn("zoneshift/vendor_support.py", expected)
        self.assertEqual(measured["core_total_sloc"], sum(expected.values()))
        recorded = json.loads((root / "results/integration-metrics.json").read_text())
        embedded = json.loads((root / "results/extended-analysis.json").read_text())["integration"]
        self.assertEqual(measured, recorded)
        self.assertEqual(measured, embedded)


if __name__ == "__main__":
    unittest.main()
