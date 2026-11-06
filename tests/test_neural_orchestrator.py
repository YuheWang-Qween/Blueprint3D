"""Regression checks for automatic inference paths and missing artifacts."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ForgeFloor'))
from extruder import NeuralInferenceOrchestrator


class NeuralOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "项目 B's files"
        self.root.mkdir()
        for name, script in [('SplitFloor', 'deploy.py'), ('SemaFloor', 'deploy_sema.py')]:
            folder = self.root / name
            (folder / 'checkpoints').mkdir(parents=True)
            (folder / script).touch()
        self.original_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.original_cwd)
        self.orchestrator = NeuralInferenceOrchestrator('.')
        self.image = self.root / "平面 A's image.png"
        self.image.touch()
        self.out = self.root / "输出 B's models"

    def test_checkpoint_directories_do_not_count_as_weights(self):
        status = self.orchestrator.check_dependencies()
        self.assertTrue(status['splitfloor_exists'])
        self.assertTrue(status['semafloor_exists'])
        self.assertFalse(status['splitfloor_checkpoint'])
        self.assertFalse(status['semafloor_checkpoint'])
        for folder, filename in [
            ('SplitFloor', 'splitfloor_best_miou.pth'),
            ('SemaFloor', 'best_semafloor_model.pth'),
        ]:
            (self.root / folder / 'checkpoints' / filename).touch()
        self.assertTrue(all(self.orchestrator.check_dependencies().values()))

    def test_split_uses_absolute_paths_and_per_run_output(self):
        def fake_run(cmd, **kwargs):
            self.assertEqual(Path(cmd[1]), self.root / 'SplitFloor/deploy.py')
            self.assertEqual(Path(kwargs['cwd']), self.root / 'SplitFloor')
            self.assertEqual(Path(cmd[cmd.index('--image') + 1]), self.image)
            temp_output = Path(cmd[cmd.index('--output_dir') + 1])
            self.assertTrue(temp_output.is_relative_to(self.out))
            for filename in ['output_mask.csv', 'output_mask_raw.png', 'output_mask_colored.png']:
                (temp_output / filename).write_bytes(b'new prediction')
            return subprocess.CompletedProcess(cmd, 0, '', '')

        # A stale source-folder result must never be selected.
        (self.root / 'SplitFloor/output_mask.csv').write_text('stale')
        with patch('extruder.subprocess.run', side_effect=fake_run):
            ok, files, error = self.orchestrator.run_splitfloor(self.image.name, self.out.name)
        self.assertTrue(ok, error)
        self.assertEqual(Path(files['split_csv_pipeline']).read_bytes(), b'new prediction')

    def test_sema_accepts_spaces_apostrophes_and_chinese_paths(self):
        def fake_run(cmd, **kwargs):
            self.assertEqual(Path(cmd[1]), self.root / 'SemaFloor/deploy_sema.py')
            self.assertEqual(Path(cmd[cmd.index('--image') + 1]), self.image)
            output = Path(cmd[cmd.index('--output_dir') + 1])
            self.assertEqual(output, self.out)
            for filename in ['sema.csv', f'{self.image.stem}_predicted_mask.png',
                             f'{self.image.stem}_overlay.png']:
                (output / filename).touch()
            return subprocess.CompletedProcess(cmd, 0, '', '')

        with patch('extruder.subprocess.run', side_effect=fake_run):
            ok, files, error = self.orchestrator.run_semafloor(self.image.name, self.out.name)
        self.assertTrue(ok, error)
        self.assertEqual(Path(files['sema_csv']), self.out / 'sema.csv')

    def test_success_exit_without_sema_csv_is_reported_as_failure(self):
        self.out.mkdir()
        for suffix in ['predicted_mask', 'overlay']:
            (self.out / f'{self.image.stem}_{suffix}.png').touch()
        with patch('extruder.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            ok, files, error = self.orchestrator.run_semafloor(self.image, self.out)
        self.assertFalse(ok)
        self.assertNotIn('sema_csv', files)
        self.assertIn('sema.csv', error)


if __name__ == '__main__':
    unittest.main()
