"""SoH shuffled-shop integration regression using an external apworld without installing it."""
import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--archipelago', required=True)
    parser.add_argument('--soh-apworld', type=Path, required=True)
    parser.add_argument('--simulate-late-gate', action='store_true')
    parser.add_argument('--simulate-early-gate', action='store_true', help='Reproduce the former crash using the old hook timing')
    parser.add_argument('--full-fill', action='store_true', help='Also fill Roster + SoH + APQuest, starting with APQuest')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.archipelago).resolve()))
    import ModuleUpdate
    ModuleUpdate.update_ran = True
    import worlds
    from worlds.AutoWorld import AutoWorldRegister
    def load(name, directory):
        for key in list(sys.modules):
            if key == name or key.startswith(name + '.'):
                del sys.modules[key]
        spec = importlib.util.spec_from_file_location(name, directory / '__init__.py', submodule_search_locations=[str(directory)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    AutoWorldRegister.world_types.pop('Roster', None)
    roster = load('worlds.roster', Path(__file__).parent / 'worlds/roster')
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(args.soh_apworld) as archive:
            archive.extractall(tmp)
        # Drop only this process's earlier SoH registration, if present.
        for game, cls in list(AutoWorldRegister.world_types.items()):
            if cls.__module__.startswith('worlds.oot_soh'):
                AutoWorldRegister.world_types.pop(game)
        soh = load('worlds.oot_soh', Path(tmp) / 'oot_soh')
        roster_type = AutoWorldRegister.world_types['Roster']
        soh_type = next(cls for cls in AutoWorldRegister.world_types.values() if cls.__module__ == soh.__name__)
        if args.simulate_late_gate:
            descriptor = roster_type.__dict__.get('stage_generate_basic')
            if descriptor:
                setattr(roster_type, 'stage_pre_fill', descriptor)
                delattr(roster_type, 'stage_generate_basic')
        if args.simulate_early_gate:
            descriptor = roster_type.__dict__.get('stage_pre_fill')
            if descriptor:
                setattr(roster_type, 'stage_generate_basic', descriptor)
                delattr(roster_type, 'stage_pre_fill')
        from test.general import setup_multiworld
        from BaseClasses import CollectionState
        multiworld = setup_multiworld([roster_type, soh_type], seed=1,
                                     options=[{'starting_games': 0}, {'shuffle_shops': 1}])
        state = CollectionState(multiworld)
        assert all(not loc.can_reach(state) for loc in multiworld.get_locations(2))
        assert not multiworld.completion_condition[2](state)
        state = multiworld.get_all_state(False)
        assert multiworld.completion_condition[2](state), 'All items must satisfy the actual SoH goal'
        unlock = roster.unlock_name(multiworld.get_player_name(2))
        state.remove(multiworld.worlds[1].create_item(unlock))
        assert not multiworld.completion_condition[2](state), 'SoH pre_fill must not erase completion gate'
        assert all(not loc.can_reach(state) for loc in multiworld.get_locations(2))
        state.collect(multiworld.worlds[1].create_item(unlock), True)
        assert any(loc.can_reach(state) for loc in multiworld.get_locations(2))
        print('PASS: SoH shuffled-shop prefill succeeds, all checks and final completion remain gated; unlock restores access')
        if args.full_fill:
            from Fill import distribute_items_restrictive
            for seed in range(10):
                candidate = setup_multiworld([roster_type, soh_type, AutoWorldRegister.world_types['APQuest']],
                                            seed=seed, options=[{'starting_games': 1}, {'shuffle_shops': 1}, {}])
                if candidate.worlds[1].starting_players == [3]:
                    break
            else:
                raise AssertionError('Could not select APQuest starting seed')
            distribute_items_restrictive(candidate)
            assert candidate.can_beat_game(), 'Filled room must be beatable from APQuest start'
            print(f'PASS: full restrictive fill seed {seed}, APQuest starts, SoH locked, room beatable')

if __name__ == '__main__':
    main()
