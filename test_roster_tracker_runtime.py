"""Real UT context/core smoke test; extract the official tracker.apworld separately."""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--archipelago', required=True)
    parser.add_argument('--tracker-source', type=Path, required=True, help='Extracted tracker package directory')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.archipelago).resolve()))
    import ModuleUpdate
    ModuleUpdate.update_ran = True
    import worlds
    spec = importlib.util.spec_from_file_location('worlds.tracker', args.tracker_source / '__init__.py',
                                                submodule_search_locations=[str(args.tracker_source)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from worlds.tracker.TrackerClient import TrackerGameContext
    from worlds.tracker.TrackerCore import TrackerLogLineGroup
    from test.general import setup_multiworld
    from worlds.AutoWorld import AutoWorldRegister
    from RosterTracker import install_bridge

    async def verify():
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            install_bridge(TrackerGameContext, path, 'Game 01')
            context = TrackerGameContext(None, None)
            try:
                context.auth, context.slot, context.team, context.seed_name = 'Game 01', 2, 0, 'runtime-test'
                context.disconnected_intentionally = False
                core = context.tracker_core
                core.multiworld = setup_multiworld([AutoWorldRegister.world_types['APQuest']])
                core.player_id, core.game, core.slot = 1, 'APQuest', 2
                core.hide_excluded, core.output_format, core.sorting_method = False, 'Location', 'location'
                core.sorting_priorities = {group.value: i for i, group in enumerate(TrackerLogLineGroup)}
                context.missing_locations = {loc.address for loc in core.multiworld.get_locations() if loc.address}
                # Real context update -> real core -> real AP reachability, with no network or GUI.
                assert context.updateTracker().in_logic_locations == []
                path.write_text(json.dumps(dict(version=1, seed_name='runtime-test', connected=True,
                                                unlocked=['Game 01'], updated_at=time.time())))
                reachable = context.updateTracker().in_logic_locations
                assert reachable, 'Unlocked APQuest must have reachable checks'
                path.write_text(json.dumps(dict(version=1, seed_name='wrong-room', connected=True,
                                                unlocked=['Game 01'], updated_at=time.time())))
                assert context.updateTracker().in_logic_locations == []
                path.unlink()
                assert context.updateTracker().in_logic_locations == []
                context.watcher_event.clear()
                await asyncio.sleep(1.05)
                assert context.watcher_event.is_set(), 'Roster updates must wake idle UT'
                print(f'PASS: UT {module.UT_VERSION} real context/core: locked=0, unlocked={len(reachable)}, wrong seed=0, missing=0, refresh wakes')
            finally:
                context.exit_event.set()
                await context._roster_refresh
                await context.shutdown()
    asyncio.run(verify())

if __name__ == '__main__':
    main()

