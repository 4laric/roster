import contextlib
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import types
import sys
import unittest
from unittest.mock import patch

import yaml
import roster_generate as wrapper
from test_RosterSeed import multidata_bytes


class InstallerGeneration(unittest.TestCase):
    def test_source_failure_captures_existing_log_handler(self):
        output = io.StringIO()
        logger = logging.getLogger()
        handlers, level = logger.handlers[:], logger.level
        logger.handlers = [logging.StreamHandler(output)]
        fake_generate = types.SimpleNamespace(mystery_argparse=lambda args: args,
                                              main=lambda args: (args, 123))
        def fail(*args):
            logging.error("Hidden Game generation failed")
            print("Hidden Game traceback details", file=sys.stderr)
            raise RuntimeError("Hidden Game")
        try:
            with patch.dict(sys.modules, Generate=fake_generate, Main=types.SimpleNamespace(main=fail)), \
                 self.assertRaises(RuntimeError):
                wrapper.run_source_generation([], False)
            self.assertEqual(output.getvalue(), "")
            self.assertIs(logger.handlers[0].stream, output)
        finally:
            logger.handlers, logger.level = handlers, level

    def test_result_uses_generated_multidata_and_fresh_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ap, games, output = root / "AP", root / "games", root / "output"
            ap.mkdir(); games.mkdir(); output.mkdir()
            (ap / "ArchipelagoGenerate.exe").touch()
            (games / "input.yaml").write_text("game: Guessed Secret\n")
            stale = output / "seed.archipelago"
            stale.write_bytes(b"old seed")
            old_tracker = output / "roster_123_tracker"
            old_tracker.mkdir()
            (old_tracker / "game_99.yaml").write_text("stale")
            result_path = root / "result.json"
            result_path.write_text('{"starting_games":["stale secret"]}')

            def generate(command, **kwargs):
                self.assertFalse(result_path.exists())
                generated = Path(command[command.index("--outputpath") + 1])
                (generated / "seed.archipelago").write_bytes(multidata_bytes())
                return subprocess.CompletedProcess(command, 0, "")

            with patch.object(wrapper.subprocess, "run", side_effect=generate), contextlib.redirect_stdout(io.StringIO()):
                code = wrapper.main(["--archipelago", str(ap), "--games", str(games),
                                     "--outputpath", str(output), "--pick", "1", "--seed", "123",
                                     "--result-file", str(result_path)])
            self.assertEqual(code, 0)
            result = json.loads(result_path.read_text())
            self.assertEqual(result["starting_games"], [{"slot": "Game 02", "game": "Actual Rolled Game"}])
            self.assertTrue(Path(result["output"]).is_absolute())
            self.assertNotEqual(Path(result["output"]), stale)
            self.assertEqual(stale.read_bytes(), b"old seed")
            self.assertEqual([p.name for p in Path(result["tracker_dir"]).iterdir()], ["game_01.yaml"])
            self.assertTrue((old_tracker / "game_99.yaml").exists())

    def test_stale_output_is_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ap, games, output = root / "AP", root / "games", root / "output"
            ap.mkdir(); games.mkdir(); output.mkdir()
            (ap / "ArchipelagoGenerate.exe").touch()
            (games / "input.yaml").write_text("game: Hidden\n")
            (output / "stale.zip").touch()
            result = root / "result.json"
            result.write_text("stale")
            with patch.object(wrapper.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "")), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = wrapper.main(["--archipelago", str(ap), "--games", str(games),
                                     "--outputpath", str(output), "--pick", "1", "--result-file", str(result)])
            self.assertEqual(code, 1)
            self.assertFalse(result.exists())

    def test_invalid_counts(self):
        for pick, start in ((0, 1), (-1, 1), (2, 0), (2, 3)):
            with self.subTest(pick=pick, start=start), contextlib.redirect_stderr(io.StringIO()), \
                 self.assertRaises(SystemExit):
                wrapper.parse_args(["--pick", str(pick), "--start", str(start)])

    def test_neutral_names_are_unique_and_assignment_is_seeded(self):
        assignments = []
        for seed in (123, 123, 321):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                ap, games, output = root / "AP", root / "games", root / "output"
                ap.mkdir()
                games.mkdir()
                (ap / "ArchipelagoGenerate.exe").touch()
                for index in range(5):
                    # Duplicate game names must still produce distinct player slots.
                    (games / f"Secret_{index}.yaml").write_text(
                        f"game: Secret Game\nname: Original\nvariant: {index}\n")

                def generate(command, **kwargs):
                    players = Path(command[command.index("--player_files_path") + 1])
                    paths = sorted(p for p in players.glob("*.yaml") if p.name != "Roster.yaml")
                    self.assertEqual([p.name for p in paths], [f"game_{i:02d}.yaml" for i in range(1, 6)])
                    docs = [yaml.safe_load(p.read_text()) for p in paths]
                    self.assertEqual([d["name"] for d in docs], [f"Game {i:02d}" for i in range(1, 6)])
                    assignments.append([d["variant"] for d in docs])
                    (Path(command[command.index("--outputpath") + 1]) / "seed.zip").touch()
                    return subprocess.CompletedProcess(command, 0, "")

                stdout = io.StringIO()
                with patch.object(wrapper.subprocess, "run", side_effect=generate), contextlib.redirect_stdout(stdout):
                    result = wrapper.main(["--archipelago", str(ap), "--games", str(games),
                                           "--outputpath", str(output), "--pick", "5", "--seed", str(seed)])
                self.assertEqual(result, 0)
                self.assertNotIn("Secret", stdout.getvalue())
                tracker = output / f"roster_{seed}_tracker"
                self.assertEqual(sorted(p.name for p in tracker.iterdir()), [f"game_{i:02d}.yaml" for i in range(1, 6)])
                self.assertEqual([yaml.safe_load(p.read_text())["variant"] for p in sorted(tracker.iterdir())], assignments[-1])
        self.assertEqual(assignments[0], assignments[1])
        self.assertNotEqual(assignments[0], assignments[2])
        self.assertNotEqual(assignments[0], list(range(5)))

    def test_installer_success_and_failure(self):
        for code in (0, 4):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                ap = root / "AP with spaces"
                games = root / "games"
                output = root / "output"
                ap.mkdir()
                games.mkdir()
                (ap / "ArchipelagoGenerate.exe").touch()
                (games / "example.yaml").write_text("game: Secret Game\nname: Original\n")
                captured_players = []

                def generate(command, **kwargs):
                    self.assertEqual(Path.cwd(), ap)
                    self.assertEqual(command[0], str(ap / "ArchipelagoGenerate.exe"))
                    players = Path(command[command.index("--player_files_path") + 1])
                    captured_players.append(players)
                    self.assertEqual(yaml.safe_load((players / "Roster.yaml").read_text())["game"], "Roster")
                    self.assertEqual(yaml.safe_load((players / "game_01.yaml").read_text())["name"], "Game 01")
                    self.assertEqual(command[command.index("--spoiler") + 1], "0")
                    if not code:
                        (Path(command[command.index("--outputpath") + 1]) / "seed.zip").touch()
                    return subprocess.CompletedProcess(command, code, "Secret Game details")

                before = os.getcwd()
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(wrapper.subprocess, "run", side_effect=generate), \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    result = wrapper.main(["--archipelago", str(ap), "--games", str(games),
                                           "--outputpath", str(output), "--pick", "1", "--seed", "123"])
                self.assertEqual(result, code)
                self.assertEqual(os.getcwd(), before)
                self.assertFalse(captured_players[0].exists())
                self.assertNotIn("Secret Game", stdout.getvalue() + stderr.getvalue())
                if code:
                    self.assertIn("Secret Game", (output / "roster_generate_123.log").read_text())
                else:
                    tracker = output / "roster_123_tracker"
                    files = list(tracker.glob("*.yaml"))
                    self.assertEqual(len(files), 1)
                    self.assertEqual(files[0].name, "game_01.yaml")
                    self.assertEqual(yaml.safe_load(files[0].read_text())["name"], "Game 01")
                    self.assertFalse((tracker / "Roster.yaml").exists())


if __name__ == "__main__":
    unittest.main()
