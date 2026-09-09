"""Exercise source-client policy without importing an AP installation."""
import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock


class SourcePolicyTests(unittest.TestCase):
    def test_join_tags_team_and_unlock_gate(self):
        tree = ast.parse(Path(__file__).with_name("RosterClient.py").read_text(encoding="utf-8"))
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                 and n.name in ("is_game_join", "RosterContext")]
        class Base:
            def __init__(self, *args):
                pass
        env = dict(CommonContext=Base, RosterCommandProcessor=object, GAME_NAME="Roster",
                   logger=Mock(), STARTED_PREFIX="Started: ", UNLOCK_PREFIX="Unlock: ",
                   Utils=types.SimpleNamespace(async_start=Mock()))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "source-client-policy", "exec"), env)
        ctx = env["RosterContext"](None, None)
        ctx.team, ctx.auth = 0, "Roster"
        ctx.locations_checked = set()
        ctx.slot_info = {2: types.SimpleNamespace(name="Game A")}
        ctx.player_names = {2: "Alias"}
        ctx._started_location_ids = lambda: {"Game A": 100}
        ctx.check_locations = Mock(return_value=None)
        join = {"type": "Join", "team": 0, "slot": 2, "tags": ["AP"]}
        ctx.on_package("PrintJSON", join)
        self.assertFalse(ctx.mark_started("Game A", manual=True))
        self.assertFalse(ctx.started_slots)
        ctx.unlocked.add("Game A")
        for tags in (["AP", "Tracker"], ["AP", "TextOnly"], ["AP", "HintGame"], [], ["PopTracker"]):
            ctx.on_package("PrintJSON", dict(join, tags=tags))
        ctx.on_package("PrintJSON", dict(join, team=1))
        ctx.check_locations.assert_not_called()
        ctx.on_package("PrintJSON", join)
        ctx.on_package("PrintJSON", join)
        ctx.check_locations.assert_called_once_with([100])
        self.assertEqual(ctx.started_slots, {"Game A"})
        self.assertEqual(ctx.locations_checked, {100})


if __name__ == "__main__":
    unittest.main()
