import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import RosterLauncher as launcher


class LauncherTests(unittest.TestCase):
    def test_install_world_and_preserve_existing_install(self):
        with tempfile.TemporaryDirectory() as temp:
            ap = Path(temp)
            (ap / 'ArchipelagoGenerate.exe').touch()
            self.assertIn('installed', launcher.install_world(ap))
            target = ap / 'custom_worlds' / 'roster.apworld'
            before = target.read_bytes()
            with zipfile.ZipFile(target) as archive:
                self.assertIn('roster/__init__.py', archive.namelist())
                manifest = json.loads(archive.read('roster/archipelago.json'))
                self.assertEqual(manifest['compatible_version'], 7)
                self.assertFalse(any('/test/' in n or '__pycache__' in n for n in archive.namelist()))
            launcher.install_world(ap)
            self.assertEqual(target.read_bytes(), before)

    def test_gui_shows_only_starting_games_and_passes_generation_settings(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            app = launcher.Launcher(root)
            with tempfile.TemporaryDirectory() as temp:
                ap = Path(temp) / 'AP'
                ap.mkdir()
                (ap / 'ArchipelagoGenerate.exe').touch()
                games = Path(temp) / 'games'
                games.mkdir()
                (games / 'candidate.yaml').write_text('game: Secret Game')
                app.ap.set(str(ap))
                app.games.set(str(games))
                app.pick.set('1')
                app.start.set('1')
                app.seed.set('123')
                def generate(command, **kwargs):
                    self.assertIn('--generate-worker', command)
                    self.assertEqual(command[command.index('--seed') + 1], '123')
                    Path(command[command.index('--result-file') + 1]).write_text(json.dumps({
                        'output': str(Path(temp) / 'seed.zip'),
                        'tracker_dir': str(Path(temp) / 'tracker'),
                        'starting_games': [{'slot': 'Game 01', 'game': 'Balatro'}],
                    }))
                    return type('Result', (), {'returncode': 0, 'stdout': ''})()
                # Run synchronously to exercise UI completion without sleep/poll races.
                class ImmediateThread:
                    def __init__(self, target, **kwargs):
                        self.target = target
                    def start(self):
                        self.target()
                with patch.object(launcher.subprocess, 'run', side_effect=generate), patch.object(launcher.threading, 'Thread', ImmediateThread):
                    app.generate()
                app.poll()
                self.assertFalse(app.busy)
                text = app.reveal.get('1.0', 'end')
                self.assertIn('Game 01 — Balatro', text)
                self.assertNotIn('Secret Game', text)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
