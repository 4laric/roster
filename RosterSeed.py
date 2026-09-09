"""Read only the starting-game reveal from AP multidata, without importing AP.

Pickle globals are mapped to inert local value types. In particular, never
import an uploaded pickle's module or use Archipelago's options-class loader.
"""
from collections import Counter, namedtuple
import enum
import io
from pathlib import Path
import pickle
import pickletools
import zipfile
import zlib


class SeedReadError(ValueError):
    """A deliberately non-spoiling error suitable for the launcher UI."""


class SlotType(enum.IntFlag):
    spectator = 0
    player = 1
    group = 2


class ClientStatus(enum.IntEnum):
    CLIENT_UNKNOWN = 0
    CLIENT_CONNECTED = 5
    CLIENT_READY = 10
    CLIENT_PLAYING = 20
    CLIENT_GOAL = 30


class HintStatus(enum.IntEnum):
    HINT_UNSPECIFIED = 0
    HINT_NO_PRIORITY = 10
    HINT_AVOID = 20
    HINT_PRIORITY = 30
    HINT_FOUND = 40


NetworkSlot = namedtuple("NetworkSlot", "name game type group_members", defaults=((),))
NetworkItem = namedtuple("NetworkItem", "item location player flags", defaults=(0,))
Hint = namedtuple("Hint", "receiving_player finding_player location item found entrance item_flags status",
                  defaults=("", 0, HintStatus.HINT_UNSPECIFIED))

_GLOBALS = {
    ("builtins", "set"): set, ("builtins", "frozenset"): frozenset,
    ("collections", "Counter"): Counter,
    **{("NetUtils", cls.__name__): cls for cls in
       (NetworkSlot, NetworkItem, Hint, SlotType, ClientStatus, HintStatus)},
}
MAX_COMPRESSED = 64 * 1024 * 1024
MAX_INFLATED = 256 * 1024 * 1024


class _SeedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        try:
            return _GLOBALS[module, name]
        except KeyError:
            raise pickle.UnpicklingError("Unsupported seed value type") from None


def _read_multidata(path: Path):
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            entries = [entry for entry in archive.infolist()
                       if not entry.is_dir() and entry.filename.lower().endswith(".archipelago")]
            if len(entries) != 1 or entries[0].file_size > MAX_COMPRESSED:
                raise SeedReadError("Seed archive must contain one supported multidata file.")
            raw = archive.read(entries[0])
    else:
        if path.stat().st_size > MAX_COMPRESSED:
            raise SeedReadError("Seed data exceeds the supported size limit.")
        raw = path.read_bytes()
    if not raw or raw[0] != 3:
        raise SeedReadError("Unsupported seed format.")
    inflater = zlib.decompressobj()
    data = inflater.decompress(raw[1:], MAX_INFLATED + 1)
    if len(data) > MAX_INFLATED or not inflater.eof or inflater.unused_data:
        raise SeedReadError("Invalid or oversized seed data.")
    # EXT opcodes can consult pickle's process-wide extension cache without
    # calling find_class. Never allow that path (or persistent external objects).
    if any(op.name in {"EXT1", "EXT2", "EXT4", "PERSID", "BINPERSID"}
           for op, _, _ in pickletools.genops(data)):
        raise SeedReadError("Unsupported seed value type.")
    stream = io.BytesIO(data)
    result = _SeedUnpickler(stream).load()
    if stream.read(1):
        raise SeedReadError("Invalid seed data.")
    return result


def read_starting_games(path: str | Path) -> list[dict[str, str]]:
    """Return actual generated starting slots; never reroll or reveal gated slots."""
    try:
        data = _read_multidata(Path(path))
        infos = data["slot_info"]
        rosters = [slot for slot, info in infos.items() if info.game == "Roster"]
        if len(rosters) != 1:
            raise ValueError
        slot_data = data["slot_data"]
        roster = slot_data.get(rosters[0], slot_data.get(str(rosters[0])))
        names = roster["starting_slots"]
        if not isinstance(names, (list, tuple)) or not names or any(type(name) is not str for name in names):
            raise ValueError
        if len(set(names)) != len(names):
            raise ValueError
        result = []
        for name in names:
            matches = [info for info in infos.values()
                       if info.name == name and info.game != "Roster" and info.type == SlotType.player]
            if len(matches) != 1 or type(matches[0].game) is not str or not matches[0].game:
                raise ValueError
            result.append({"slot": name, "game": matches[0].game})
        return result
    except SeedReadError:
        raise
    except Exception:
        raise SeedReadError("Could not read starting games from this seed.") from None
