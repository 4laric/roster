import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml
import roster_generate as wrapper


class InstallerGeneration(unittest.TestCase):
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
                    self.assertEqual(yaml.safe_load((players / "example.yaml").read_text())["name"], "Secret Game")
                    self.assertEqual(command[command.index("--spoiler") + 1], "0")
                    if not code:
                        (output / "seed.zip").touch()
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


if __name__ == "__main__":
    unittest.main()
