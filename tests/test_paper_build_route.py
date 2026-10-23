"""Owned build fixtures preserve delivered figures on renderer/compiler failure."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'paper/build.py'


@unittest.skipUnless(SCRIPT.is_file(), 'companion manuscript not included')
class BuildRouteTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('zoneshift_paper_build', SCRIPT)
        self.build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.build)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.paper = Path(temp.name) / 'paper'
        (self.paper / 'figures').mkdir(parents=True)
        (self.paper / 'main.tex').write_text('owned fixture', encoding='utf-8')
        (self.paper / 'main.pdf').write_bytes(b'old manuscript')
        (self.paper / 'figures/workflow.pdf').write_bytes(b'old vector')

    def run_build(self, failure=None):
        def run(command, **kwargs):
            if len(command) > 1 and str(command[1]).endswith('study_denominators.py'):
                work = Path(command[command.index('--paper-dir') + 1])
                (work / 'generated').mkdir(exist_ok=True)
                (work / 'generated/study-denominators.tex').write_text('owned cohort table', encoding='utf-8')
                if failure == 'denominator':
                    raise subprocess.CalledProcessError(1, command)
            elif len(command) > 1 and str(command[1]).endswith('draw_workflow.py'):
                target = Path(command[command.index('--output-dir') + 1]) / 'workflow.pdf'
                self.assertNotEqual(target.parent, self.paper / 'figures')
                target.write_bytes(b'new vector')
                if failure == 'renderer':
                    raise subprocess.CalledProcessError(1, command)
            else:
                if failure == 'compiler':
                    raise subprocess.CalledProcessError(1, command)
                work = Path(kwargs['cwd'])
                (work / 'main.pdf').write_bytes(b'new manuscript')
                (work / 'main.log').write_text('owned clean log', encoding='utf-8')
            return subprocess.CompletedProcess(command, 0)
        with patch.object(self.build, 'HERE', self.paper), \
             patch.object(self.build.shutil, 'which', side_effect=lambda name: name), \
             patch.object(self.build.subprocess, 'run', side_effect=run):
            self.build.main()

    def test_missing_engine_never_starts_renderer(self):
        with patch.object(self.build.shutil, 'which', return_value=None), \
             patch.object(self.build.subprocess, 'run') as run, self.assertRaises(SystemExit):
            self.build.main()
        run.assert_not_called()

    def test_renderer_failure_preserves_manuscript_and_vector(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_build('renderer')
        self.assertEqual((self.paper / 'main.pdf').read_bytes(), b'old manuscript')
        self.assertEqual((self.paper / 'figures/workflow.pdf').read_bytes(), b'old vector')

    def test_compiler_failure_preserves_manuscript_and_vector(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_build('compiler')
        self.assertEqual((self.paper / 'main.pdf').read_bytes(), b'old manuscript')
        self.assertEqual((self.paper / 'figures/workflow.pdf').read_bytes(), b'old vector')

    def test_complete_build_publishes_both_outputs(self):
        self.run_build()
        self.assertEqual((self.paper / 'main.pdf').read_bytes(), b'new manuscript')
        self.assertEqual((self.paper / 'figures/workflow.pdf').read_bytes(), b'new vector')

    def test_invalid_denominator_blocks_render_and_publication(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_build('denominator')
        self.assertEqual((self.paper / 'main.pdf').read_bytes(), b'old manuscript')
        self.assertEqual((self.paper / 'figures/workflow.pdf').read_bytes(), b'old vector')
