"""Roster: a spoiler-free game selector for Archipelago.

One Roster slot holds an "Unlock: <slot>" item for every other slot in the
multiworld. A few of them are precollected; the rest live in the item pool like
any other progression item. Until a slot's unlock is held, none of that slot's
locations are reachable and its goal cannot be completed.

See DESIGN.md in the roster repo for the full design.
"""

from __future__ import annotations

from typing import Any, ClassVar

from BaseClasses import CollectionState, Item, ItemClassification, Location, MultiWorld, Region, Tutorial
from worlds.AutoWorld import WebWorld, World
from worlds.generic.Rules import add_rule

from .options import RosterOptions

GAME_NAME = "Roster"

ITEM_ID_BASE = 0x520000
LOCATION_ID_BASE = 0x520000
FILLER_NAME = "Roster Token"
FILLER_ID = ITEM_ID_BASE  # player ids start at 1, so 0 is free for the filler


def unlock_name(slot_name: str) -> str:
    return f"Unlock: {slot_name}"


def started_name(slot_name: str) -> str:
    return f"Started: {slot_name}"


class RosterItem(Item):
    game = GAME_NAME


class RosterLocation(Location):
    game = GAME_NAME


class RosterWeb(WebWorld):
    theme = "partyTime"
    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "A guide to setting up Roster in an Archipelago multiworld.",
            "English",
            "setup_en.md",
            "setup/en",
            ["4laric"],
        )
    ]


class RosterWorld(World):
    """Roster picks which games tonight's multiworld actually plays. Every other slot is
    locked until its "Unlock" item is found, so nobody knows what is coming next."""

    game = GAME_NAME
    web = RosterWeb()

    options_dataclass = RosterOptions
    options: RosterOptions

    # These are rebuilt per multiworld in stage_generate_early, because the item and
    # location names depend on the other slots' names.
    item_name_to_id: ClassVar[dict[str, int]] = {FILLER_NAME: FILLER_ID}
    location_name_to_id: ClassVar[dict[str, int]] = {}

    origin_region_name = "Roster"

    gated_players: list[int]
    starting_players: list[int]

    # ------------------------------------------------------------------ helpers

    @classmethod
    def _all_gated_players(cls, multiworld: MultiWorld) -> list[int]:
        """Every non-Roster player that at least one Roster slot wants to gate."""
        others = [p for p in multiworld.player_ids if multiworld.worlds[p].game != GAME_NAME]
        wanted: set[int] = set()
        for p in multiworld.player_ids:
            world = multiworld.worlds[p]
            if world.game != GAME_NAME:
                continue
            names = set(world.options.gate_slots.value)
            if not names:
                wanted.update(others)
            else:
                wanted.update(o for o in others if multiworld.get_player_name(o) in names)
        return sorted(wanted)

    @classmethod
    def _rebuild_data_package(cls, multiworld: MultiWorld) -> None:
        item_name_to_id = {FILLER_NAME: FILLER_ID}
        location_name_to_id: dict[str, int] = {}
        for player in cls._all_gated_players(multiworld):
            name = multiworld.get_player_name(player)
            item_name_to_id[unlock_name(name)] = ITEM_ID_BASE + player
            location_name_to_id[started_name(name)] = LOCATION_ID_BASE + player

        cls.item_name_to_id = item_name_to_id
        cls.location_name_to_id = location_name_to_id
        cls.item_id_to_name = {v: k for k, v in item_name_to_id.items()}
        cls.location_id_to_name = {v: k for k, v in location_name_to_id.items()}
        cls.item_names = frozenset(item_name_to_id)
        cls.location_names = frozenset(location_name_to_id)

        # Keep the network data package in sync; Main.py copies it into the multidata
        # after generation, and the server serves that copy to clients.
        try:
            import worlds

            worlds.network_data_package["games"][GAME_NAME] = cls.get_data_package_data()
        except Exception:  # pragma: no cover - never worth failing generation over
            pass

    # ------------------------------------------------------------------ generation

    @classmethod
    def stage_generate_early(cls, multiworld: MultiWorld) -> None:
        cls._rebuild_data_package(multiworld)

    def generate_early(self) -> None:
        self.gated_players = []
        self.starting_players = []

    def create_regions(self) -> None:
        self.gated_players = self._all_gated_players(self.multiworld)
        wanted = set(self.options.gate_slots.value)
        if wanted:
            self.gated_players = [
                p for p in self.gated_players if self.multiworld.get_player_name(p) in wanted
            ]

        count = min(self.options.starting_games.value, len(self.gated_players))
        self.starting_players = sorted(self.random.sample(self.gated_players, count))

        menu = Region(self.origin_region_name, self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        for player in self.gated_players:
            name = self.multiworld.get_player_name(player)
            location = RosterLocation(self.player, started_name(name), self.location_name_to_id[started_name(name)], menu)
            menu.locations.append(location)

    def create_item(self, name: str) -> RosterItem:
        classification = (
            ItemClassification.filler if name == FILLER_NAME else ItemClassification.progression
        )
        return RosterItem(name, classification, self.item_name_to_id[name], self.player)

    def get_filler_item_name(self) -> str:
        return FILLER_NAME

    def create_items(self) -> None:
        for player in self.gated_players:
            item = self.create_item(unlock_name(self.multiworld.get_player_name(player)))
            if player in self.starting_players:
                self.multiworld.push_precollected(item)
                self.multiworld.itempool.append(self.create_item(FILLER_NAME))
            else:
                self.multiworld.itempool.append(item)

    def set_rules(self) -> None:
        for player in self.gated_players:
            name = self.multiworld.get_player_name(player)
            location = self.get_location(started_name(name))
            location.access_rule = (
                lambda state, item=unlock_name(name), me=self.player: state.has(item, me)
            )

        self.multiworld.completion_condition[self.player] = (
            lambda state, items=[unlock_name(self.multiworld.get_player_name(p)) for p in self.gated_players],
            me=self.player: state.has_all(items, me)
        )

    @classmethod
    def stage_generate_basic(cls, multiworld: MultiWorld) -> None:
        """Wrap every gated slot's location rules and completion condition with its unlock."""
        for roster_player in multiworld.player_ids:
            world = multiworld.worlds[roster_player]
            if world.game != GAME_NAME:
                continue
            for player in world.gated_players:
                unlock = unlock_name(multiworld.get_player_name(player))

                for location in multiworld.get_locations(player):
                    add_rule(
                        location,
                        lambda state, item=unlock, me=roster_player: state.has(item, me),
                    )

                old_condition = multiworld.completion_condition[player]
                multiworld.completion_condition[player] = (
                    lambda state, item=unlock, me=roster_player, old=old_condition:
                    state.has(item, me) and old(state)
                )

    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "gated_slots": {
                str(p): self.multiworld.get_player_name(p) for p in self.gated_players
            },
            "starting_slots": [self.multiworld.get_player_name(p) for p in self.starting_players],
            "slot_games": {
                self.multiworld.get_player_name(p): self.multiworld.game[p]
                for p in sorted(set(self.gated_players) | set(self.starting_players))
            },
            "starting_games": self.options.starting_games.value,
        }
