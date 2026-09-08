from dataclasses import dataclass

from Options import OptionSet, PerGameCommonOptions, Range


class StartingGames(Range):
    """How many of the other slots in the multiworld start already unlocked.

    Their "Unlock: <slot>" items are precollected, and an equal number of
    "Roster Token" filler items take their place in the item pool.
    """

    display_name = "Starting Games"
    range_start = 0
    range_end = 20
    default = 1


class GateSlots(OptionSet):
    """Slot names to put behind the roster gate.

    Empty (the default) means every non-Roster slot in the multiworld.
    """

    display_name = "Gated Slots"
    valid_keys = ()
    default = frozenset()


@dataclass
class RosterOptions(PerGameCommonOptions):
    starting_games: StartingGames
    gate_slots: GateSlots
