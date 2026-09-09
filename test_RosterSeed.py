from collections import namedtuple
import os
from pathlib import Path
import pickle
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile
import zlib
import RosterSeed

from RosterSeed import read_starting_games, SeedReadError


def multidata_bytes(start="Game 02"):
    # Match AP's wire globals without importing AP, even in an installer-only environment.
    module = types.ModuleType("NetUtils")
    module.NetworkSlot = namedtuple("NetworkSlot", "name game type group_members", defaults=((),))
    module.NetworkSlot.__module__ = "NetUtils"
    with patch.dict(sys.modules, NetUtils=module):
        data = {"slot_info": {1: module.NetworkSlot("Roster", "Roster", 1),
                              2: module.NetworkSlot("Game 01", "Hidden Game", 1),
                              3: module.NetworkSlot("Game 02", "Actual Rolled Game", 1)},
                "slot_data": {1: {"starting_slots": (start,),
                                  "slot_games": {"Game 02": "Wrong guessed game"}}}}
        return b"\x03" + zlib.compress(pickle.dumps(data))


class SeedReading(unittest.TestCase):
    def test_actual_slot_info_and_no_ap_imports(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "seed.zip"
            with zipfile.ZipFile(archive, "w") as target:
                target.writestr("seed.archipelago", multidata_bytes())
            with patch.dict(sys.modules, {"NetUtils": None, "Utils": None, "Options": None}):
                self.assertEqual(read_starting_games(archive),
                                 [{"slot": "Game 02", "game": "Actual Rolled Game"}])

    def test_arbitrary_global_never_executes(self):
        class Evil:
            def __reduce__(self):
                return os.system, ("echo hidden secret",)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.archipelago"
            path.write_bytes(b"\x03" + zlib.compress(pickle.dumps(Evil())))
            with patch.object(os, "system") as execute, self.assertRaises(SeedReadError) as error:
                read_starting_games(path)
            execute.assert_not_called()
            self.assertNotIn("hidden", str(error.exception))

    def test_missing_slot_and_duplicate_archives_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "seed.archipelago"
            path.write_bytes(multidata_bytes("Secret nonexistent slot"))
            with self.assertRaises(SeedReadError) as error:
                read_starting_games(path)
            self.assertNotIn("Secret", str(error.exception))
            archive = Path(temp) / "seed.zip"
            with zipfile.ZipFile(archive, "w") as target:
                target.writestr("a.archipelago", multidata_bytes())
                target.writestr("b.archipelago", multidata_bytes())
            with self.assertRaises(SeedReadError):
                read_starting_games(archive)

    def test_extension_cache_and_oversize_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "seed.archipelago"
            path.write_bytes(b"\x03" + zlib.compress(b"\x80\x02\x82\x01."))
            with self.assertRaises(SeedReadError):
                read_starting_games(path)
            path.write_bytes(multidata_bytes())
            with patch.object(RosterSeed, "MAX_INFLATED", 16), self.assertRaises(SeedReadError):
                read_starting_games(path)


if __name__ == "__main__":
    unittest.main()
