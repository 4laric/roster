import unittest

from BaseClasses import CollectionState, ItemClassification
from test.general import setup_multiworld
from worlds.AutoWorld import AutoWorldRegister

from .. import GAME_NAME, unlock_name, started_name

OTHER_GAME = "APQuest"


def make_multiworld(starting_games: int = 0, seed: int = 1):
    roster = AutoWorldRegister.world_types[GAME_NAME]
    other = AutoWorldRegister.world_types[OTHER_GAME]
    return setup_multiworld(
        [roster, other, other],
        seed=seed,
        options=[{"starting_games": starting_games}, {}, {}],
    )


class TestRosterGate(unittest.TestCase):
    def test_local_prefill_runs_before_gate_and_goal_reset_is_wrapped(self) -> None:
        from unittest.mock import patch
        other = AutoWorldRegister.world_types[OTHER_GAME]
        visited = []

        def local_prefill(world):
            # Like SoH, prepare a local-only inventory and replace the goal.
            state = CollectionState(world.multiworld)
            for item in world.multiworld.itempool:
                if item.player == world.player:
                    state.collect(item, prevent_sweep=True)
            state.sweep_for_advancements(world.multiworld.get_locations(world.player))
            self.assertTrue(any(location.can_reach(state)
                                for location in world.multiworld.get_locations(world.player)))
            world.multiworld.completion_condition[world.player] = lambda state: True
            visited.append(world.player)

        with patch.object(other, 'pre_fill', local_prefill):
            multiworld = make_multiworld(starting_games=0)
        self.assertEqual(visited, [2, 3])
        state = CollectionState(multiworld)
        for player in visited:
            self.assertFalse(multiworld.completion_condition[player](state))
            self.assertTrue(all(not loc.can_reach(state) for loc in multiworld.get_locations(player)))

    def test_own_unlock_cannot_fill_own_started(self) -> None:
        multiworld = make_multiworld(starting_games=0)
        roster = multiworld.worlds[1]
        for player in (2, 3):
            name = multiworld.get_player_name(player)
            state = CollectionState(multiworld)
            for item in multiworld.itempool:
                if item.name != unlock_name(name):
                    state.collect(item, prevent_sweep=True)
            own_unlock = roster.create_item(unlock_name(name))
            started = roster.get_location(started_name(name))
            self.assertFalse(started.can_reach(state))
            self.assertFalse(started.can_fill(state, own_unlock, check_access=True))

    def test_real_restrictive_fill_has_no_circular_unlocks(self) -> None:
        from Fill import distribute_items_restrictive
        for seed in range(10):
            with self.subTest(seed=seed):
                multiworld = make_multiworld(starting_games=1, seed=seed)
                distribute_items_restrictive(multiworld)
                self.assertTrue(multiworld.can_beat_game())
                for location in multiworld.get_locations(1):
                    self.assertNotEqual(location.item.name,
                                        location.name.replace("Started: ", "Unlock: "))

    def test_tracker_bridge_preserves_rules_and_closes_checks(self) -> None:
        from RosterTracker import TrackerGate
        multiworld = make_multiworld(starting_games=1)
        gate = TrackerGate()
        for player in (2, 3):
            gate.apply(multiworld, player)
            gate.apply(multiworld, player)  # Repeat refresh must not stack wrappers.
        state = multiworld.get_all_state(False)
        self.assertTrue(all(not loc.can_reach(state) for p in (2, 3)
                            for loc in multiworld.get_locations(p)))
        gate.allowed = True
        state = multiworld.get_all_state(False)  # UT rebuilds CollectionState on every refresh.
        self.assertTrue(all(loc.can_reach(state) for p in (2, 3)
                           for loc in multiworld.get_locations(p)))
        gate.allowed = False
        self.assertTrue(all(not multiworld.completion_condition[p](state) for p in (2, 3)))

    def test_gated_slots_unreachable_from_empty_state(self) -> None:
        multiworld = make_multiworld(starting_games=0)
        state = CollectionState(multiworld)
        for player in (2, 3):
            for location in multiworld.get_locations(player):
                with self.subTest(location=location.name, player=player):
                    self.assertFalse(
                        location.can_reach(state),
                        f"{location.name} for player {player} is reachable without its unlock",
                    )
            self.assertFalse(multiworld.completion_condition[player](state))

    def test_everything_reachable_with_all_items(self) -> None:
        multiworld = make_multiworld(starting_games=0)
        state = CollectionState(multiworld)
        for item in multiworld.itempool:
            state.collect(item, prevent_sweep=True)
        for item in multiworld.precollected_items[1]:
            state.collect(item, prevent_sweep=True)
        state.sweep_for_advancements()
        for player in multiworld.player_ids:
            for location in multiworld.get_locations(player):
                with self.subTest(location=location.name, player=player):
                    self.assertTrue(location.can_reach(state))
            self.assertTrue(multiworld.completion_condition[player](state))

    def test_starting_games_are_precollected(self) -> None:
        multiworld = make_multiworld(starting_games=1)
        roster = multiworld.worlds[1]
        self.assertEqual(len(roster.starting_players), 1)
        precollected = {item.name for item in multiworld.precollected_items[1]}
        for player in roster.starting_players:
            self.assertIn(unlock_name(multiworld.get_player_name(player)), precollected)

    def test_item_and_location_counts_balance(self) -> None:
        multiworld = make_multiworld(starting_games=1)
        roster_items = [item for item in multiworld.itempool if item.player == 1]
        roster_locations = list(multiworld.get_locations(1))
        self.assertEqual(len(roster_items), len(roster_locations))
        self.assertEqual(len(roster_locations), 2)
        self.assertEqual(
            sum(1 for item in roster_items if item.classification == ItemClassification.filler), 1
        )
