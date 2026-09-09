"""Source-runtime Universal Tracker bootstrap with a live Roster gate.

Requires an AP source Python environment with a compatible Universal Tracker world.
No installed files are patched. See docs/tracker-bridge.md.
"""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time


def snapshot_unlocked(path: Path, seed: str | None, slot: str, now: float | None = None) -> bool:
    """Missing, expired, disconnected or wrong-seed state is locked."""
    if not seed:
        return False
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        age = (time.time() if now is None else now) - float(data['updated_at'])
        return (data.get('version') == 1 and data.get('connected') is True
                and data.get('seed_name') == seed and -5 <= age <= 30
                and isinstance(data.get('unlocked'), list) and slot in data['unlocked'])
    except (OSError, ValueError, TypeError, KeyError):
        return False


class TrackerGate:
    """AND a dynamic gate with real location rules, including logical events."""
    def __init__(self):
        self.allowed = False
        self.seen = set()
        self.worlds = set()

    def apply(self, multiworld, player):
        for location in multiworld.get_locations(player):
            if location in self.seen:
                continue
            previous = location.access_rule
            location.access_rule = lambda state, old=previous: self.allowed and old(state)
            self.seen.add(location)
        key = (multiworld, player)
        if key not in self.worlds:
            previous = multiworld.completion_condition[player]
            multiworld.completion_condition[player] = lambda state, old=previous: self.allowed and old(state)
            self.worlds.add(key)


def install_bridge(context_class, state_file: Path, slot: str):
    """Patch only this launched process, before TrackerGameContext is constructed."""
    for attribute in ('updateTracker', '__init__'):
        if not callable(getattr(context_class, attribute, None)):
            raise RuntimeError('Unsupported UT API: missing ' + attribute)
    old_init, old_update = context_class.__init__, context_class.updateTracker

    def update(context):
        core = context.tracker_core
        gate = context._roster_gate
        gate.allowed = (getattr(context, 'slot', None) is not None
                        and getattr(context, 'auth', None) == slot
                        and snapshot_unlocked(state_file, getattr(context, 'seed_name', None), slot))
        if core.multiworld is not None and core.player_id is not None:
            gate.apply(core.multiworld, core.player_id)
        return old_update(context)

    async def refresh(context):
        # UT normally refreshes only on game events; Roster updates are a separate stream.
        while not context.exit_event.is_set():
            context.watcher_event.set()
            try:
                await asyncio.wait_for(context.exit_event.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass

    def initialize(context, *args, **kwargs):
        old_init(context, *args, **kwargs)
        core = getattr(context, 'tracker_core', None)
        if core is None or not hasattr(core, 'multiworld') or not hasattr(core, 'player_id'):
            raise RuntimeError('Unsupported UT API: TrackerCore fields unavailable')
        context._roster_gate = TrackerGate()
        context._roster_refresh = asyncio.create_task(refresh(context))

    context_class.__init__ = initialize
    context_class.updateTracker = update


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archipelago', required=True)
    parser.add_argument('--roster-state', type=Path, required=True)
    parser.add_argument('--slot', required=True)
    args, tracker_args = parser.parse_known_args(argv)
    if any(a == '--name' or a.startswith('--name=') for a in tracker_args):
        parser.error('Use --slot for the tracked player name')
    ap = Path(args.archipelago).resolve()
    if not (ap / 'CommonClient.py').is_file():
        parser.error('This bridge requires an Archipelago source runtime; frozen installer UT is unsupported')
    sys.path.insert(0, str(ap))
    import ModuleUpdate
    ModuleUpdate.update_ran = True
    try:
        from worlds.tracker.TrackerClient import TrackerGameContext, launch
    except ImportError as error:
        parser.error(f'Install compatible Universal Tracker in the source runtime first: {error}')
    install_bridge(TrackerGameContext, args.roster_state.resolve(), args.slot)
    launch('--name', args.slot, *tracker_args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
