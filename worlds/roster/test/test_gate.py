import unittest

from BaseClasses import CollectionState, ItemClassification
from test.general import setup_multiworld
from worlds.AutoWorld import AutoWorldRegister

from .. import GAME_NAME, unlock_name

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
