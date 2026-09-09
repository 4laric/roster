"""Run this checkout's world tests using a prepared AP source environment.

python test_roster_world.py --archipelago C:/path/to/Archipelago
No installed world files are changed.
"""
import argparse
import importlib.util
from pathlib import Path
import sys
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archipelago', required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.archipelago).resolve()))
    import ModuleUpdate
    ModuleUpdate.update_ran = True
    import worlds
    from worlds.AutoWorld import AutoWorldRegister
    AutoWorldRegister.world_types.pop('Roster', None)
    for name in list(sys.modules):
        if name == 'worlds.roster' or name.startswith('worlds.roster.'):
            del sys.modules[name]
    local = Path(__file__).resolve().parent / 'worlds' / 'roster'
    spec = importlib.util.spec_from_file_location('worlds.roster', local / '__init__.py', submodule_search_locations=[str(local)])
    module = importlib.util.module_from_spec(spec)
    sys.modules['worlds.roster'] = module
    setattr(worlds, 'roster', module)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromName('worlds.roster.test.test_gate')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return not result.wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(main())
