import json
from pathlib import Path
import tempfile
import sys
import threading
import time
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
                app.output.set(str(Path(temp) / 'output'))
                app.pick.set('1')
                app.start.set('1')
                app.seed.set('123')
                def generate(command, worker_log):
                    self.assertIn('--generate-worker', command)
                    self.assertEqual(command[command.index('--seed') + 1], '123')
                    self.assertTrue(Path(command[command.index('--log-file') + 1]).exists())
                    Path(command[command.index('--result-file') + 1]).write_text(json.dumps({
                        'output': str(Path(temp) / 'seed.zip'),
                        'tracker_dir': str(Path(temp) / 'tracker'),
                        'starting_games': [{'slot': 'Game 01', 'game': 'Balatro'}],
                    }))
                    return 0
                # Run synchronously to exercise UI completion without sleep/poll races.
                class ImmediateThread:
                    def __init__(self, target, **kwargs):
                        self.target = target
                    def start(self):
                        self.target()
                with patch.object(launcher.GenerationJob, 'run', side_effect=generate), patch.object(launcher.threading, 'Thread', ImmediateThread):
                    app.generate()
                app.poll()
                self.assertFalse(app.busy)
                text = app.reveal.get('1.0', 'end')
                self.assertIn('Game 01 — Balatro', text)
                self.assertNotIn('Secret Game', text)
        finally:
            root.destroy()

    def test_worker_live_log_and_cancel(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'worker.log'
            job = launcher.GenerationJob()
            results = []
            script = "import time; print('live progress', flush=True); time.sleep(60)"
            if sys.platform == 'win32':
                script = "import subprocess, sys, time; child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); print('child='+str(child.pid), flush=True); print('live progress', flush=True); time.sleep(60)"
            thread = threading.Thread(target=lambda: results.append(job.run(
                [sys.executable, '-c', script], log)))
            thread.start()
            child_handle = None
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if log.exists() and 'live progress' in log.read_text():
                        break
                    time.sleep(.02)
                self.assertIn('live progress', log.read_text())
                self.assertTrue(thread.is_alive())
                if sys.platform == 'win32':
                    import ctypes
                    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                    kernel.OpenProcess.restype = ctypes.c_void_p
                    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
                    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                    pid = int(next(line[6:] for line in log.read_text().splitlines() if line.startswith('child=')))
                    child_handle = kernel.OpenProcess(0x100000, False, pid)
                    self.assertTrue(child_handle)
                job.cancel()
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
                self.assertNotEqual(results, [0])
                if child_handle:
                    self.assertEqual(kernel.WaitForSingleObject(child_handle, 5000), 0)
            finally:
                job.cancel()
                thread.join(timeout=10)
                if child_handle:
                    kernel.CloseHandle(child_handle)

    def test_cancel_before_launch_never_starts_process(self):
        with tempfile.TemporaryDirectory() as temp:
            job = launcher.GenerationJob()
            job.cancel()
            with patch.object(launcher.subprocess, 'Popen') as popen:
                self.assertEqual(job.run(['unused'], Path(temp) / 'log'), 125)
                popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
