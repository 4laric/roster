#!/usr/bin/env python3
"""Roster generation wrapper.

    python roster_generate.py --games ./games --pick 10 --start 2 --seed 123

Picks --pick yamls out of --games with the seed, names every slot after its game
(truncated to Archipelago's 16 character slot limit and de-duplicated), writes a
Roster.yaml next to them, and runs Archipelago's Generate.py on the lot.

Prints the seed and the output path. Not the game list. The spoiler log is off by
default because it lists every selected game.
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

DEFAULT_ARCHIPELAGO = r"C:\Users\alari\Archipelago"
SLOT_NAME_LIMIT = 16


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Roster multiworld.")
    parser.add_argument("--games", default="./games", help="Folder of per-game yamls.")
    parser.add_argument("--pick", type=int, required=True, help="How many games to select.")
    parser.add_argument("--start", type=int, default=1, help="How many games start unlocked.")
    parser.add_argument("--seed", type=int, default=None, help="Seed. Random if omitted.")
    parser.add_argument("--spoiler", type=int, default=0, help="Spoiler level. 0 by default; the log names every game.")
    parser.add_argument("--outputpath", default="./output", help="Where the generated seed lands.")
    parser.add_argument("--archipelago", default=DEFAULT_ARCHIPELAGO, help="Path to the Archipelago checkout.")
    parser.add_argument("--verbose", action="store_true", help="Print the slot name mapping and generator output.")
    parser.add_argument("--keep-players", action="store_true", help="Keep the temporary players dir.")
    return parser.parse_args(argv)


def truncate_and_dedupe(names: list[str]) -> dict[str, str]:
    """Map source game name -> unique slot name of at most 16 characters."""
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for name in names:
        candidate = name[:SLOT_NAME_LIMIT]
        if candidate in used:
            for suffix in range(2, 100):
                tag = str(suffix)
                candidate = (name[: SLOT_NAME_LIMIT - len(tag)]) + tag
                if candidate not in used:
                    break
        used.add(candidate)
        mapping[name] = candidate
    return mapping


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    ap_path = Path(args.archipelago).resolve()
    if not (ap_path / "Generate.py").is_file():
        print(f"No Generate.py in {ap_path}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(ap_path))

    # The checkout's ModuleUpdate wants to reinstall mismatched requirements and prompts
    # for it interactively. We are not doing that.
    import ModuleUpdate

    ModuleUpdate.update_ran = True

    import yaml as _yaml  # provided by the Archipelago checkout's environment

    games_dir = Path(args.games).resolve()
    yaml_paths = sorted(p for p in games_dir.iterdir() if p.suffix.lower() in (".yaml", ".yml"))
    if not yaml_paths:
        print(f"No yamls in {games_dir}", file=sys.stderr)
        return 2
    if args.pick > len(yaml_paths):
        print(f"--pick {args.pick} but only {len(yaml_paths)} yamls in {games_dir}", file=sys.stderr)
        return 2

    seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    picker = random.Random(seed)
    chosen = sorted(picker.sample(yaml_paths, args.pick), key=lambda p: p.name)

    documents: dict[Path, dict] = {}
    for path in chosen:
        with open(path, encoding="utf-8") as handle:
            doc = _yaml.safe_load(handle)
        if not isinstance(doc, dict):
            print(f"{path.name} is not a single-document player yaml", file=sys.stderr)
            return 2
        documents[path] = doc

    def game_of(doc: dict, path: Path) -> str:
        game = doc.get("game")
        if isinstance(game, dict):
            game = max(game, key=lambda key: game[key])
        return str(game) if game else path.stem

    mapping = truncate_and_dedupe([game_of(documents[p], p) for p in chosen])

    players_dir = Path(tempfile.mkdtemp(prefix="roster_players_"))
    try:
        for path in chosen:
            doc = documents[path]
            doc["name"] = mapping[game_of(doc, path)]
            with open(players_dir / path.name, "w", encoding="utf-8") as handle:
                _yaml.safe_dump(doc, handle, sort_keys=False, allow_unicode=True)

        roster_yaml = {
            "name": "Roster",
            "game": "Roster",
            "description": "Roster selector slot",
            "accessibility": "full",
            "progression_balancing": 0,
            "Roster": {
                "starting_games": args.start,
                "gate_slots": [],
            },
        }
        with open(players_dir / "Roster.yaml", "w", encoding="utf-8") as handle:
            _yaml.safe_dump(roster_yaml, handle, sort_keys=False, allow_unicode=True)

        if args.verbose:
            print("Slot name mapping:")
            for game, slot in mapping.items():
                marker = "" if game == slot else "  (truncated)"
                print(f"  {game!r} -> {slot!r}{marker}")

        outputpath = Path(args.outputpath).resolve()
        outputpath.mkdir(parents=True, exist_ok=True)
        start_time = __import__("time").time() - 1

        import Generate
        from Main import main as run_generation

        gen_argv = [
            "--player_files_path", str(players_dir),
            "--outputpath", str(outputpath),
            "--seed", str(seed),
            "--spoiler", str(args.spoiler),
            "--multi", "0",
        ]

        cwd = os.getcwd()
        os.chdir(ap_path)
        try:
            import logging

            if args.verbose:
                logging.getLogger().setLevel(logging.INFO)
                logging.basicConfig(level=logging.INFO, force=True)
                gen_args, gen_seed = Generate.main(Generate.mystery_argparse(gen_argv))
                run_generation(gen_args, gen_seed)
            else:
                import contextlib
                import io

                logging.getLogger().setLevel(logging.ERROR)
                sink = io.StringIO()
                with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                    gen_args, gen_seed = Generate.main(Generate.mystery_argparse(gen_argv))
                    run_generation(gen_args, gen_seed)
        finally:
            os.chdir(cwd)

        new = [p for p in outputpath.iterdir() if p.stat().st_mtime >= start_time]
        new.sort(key=lambda p: p.stat().st_mtime)
        produced = [p for p in new if p.suffix in (".archipelago", ".zip")]
        target = produced[-1] if produced else (new[-1] if new else None)

        print(f"Seed: {seed}")
        print(f"Output: {target if target else outputpath}")
        return 0 if target else 1
    finally:
        if args.keep_players:
            print(f"Players dir: {players_dir}")
        else:
            shutil.rmtree(players_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
