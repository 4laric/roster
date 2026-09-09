#!/usr/bin/env python3
"""Roster generation wrapper.

    python roster_generate.py --games ./games --pick 10 --start 2 --seed 123

Picks and orders --pick yamls with the seed, assigns neutral Game 01 slot names,
writes neutral per-slot filenames and a
Roster.yaml next to them, and runs Archipelago's Generate.py on the lot.

Prints the seed and the output path. Not the game list. The spoiler log is off by
default because it lists every selected game.
"""

from __future__ import annotations

import argparse
import json
import uuid
import traceback
from datetime import datetime, timezone
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from RosterSeed import read_starting_games

DEFAULT_ARCHIPELAGO = r"C:\Users\alari\Archipelago"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Roster multiworld.")
    parser.add_argument("--games", default="./games", help="Folder of per-game yamls.")
    parser.add_argument("--pick", type=int, required=True, help="How many games to select.")
    parser.add_argument("--start", type=int, default=1, help="How many games start unlocked.")
    parser.add_argument("--seed", type=int, default=None, help="Seed. Random if omitted.")
    parser.add_argument("--spoiler", type=int, default=0, help="Spoiler level. 0 by default; the log names every game.")
    parser.add_argument("--outputpath", default="./output", help="Where the generated seed lands.")
    parser.add_argument("--archipelago", default=DEFAULT_ARCHIPELAGO, help="Path to an Archipelago source checkout or installed distribution.")
    parser.add_argument("--verbose", action="store_true", help="Print the slot name mapping and generator output.")
    parser.add_argument("--keep-players", action="store_true", help="Keep the temporary players dir.")
    parser.add_argument("--log-file", help="Live generator diagnostic log (may contain spoilers).")
    parser.add_argument("--result-file", help="Write success JSON for the launcher.")
    args = parser.parse_args(argv)
    if args.pick < 1 or not 1 <= args.start <= args.pick:
        parser.error("Require --pick >= 1 and 1 <= --start <= --pick")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    result_path = Path(args.result_file).resolve() if args.result_file else None
    if result_path:
        result_path.unlink(missing_ok=True)

    ap_path = Path(args.archipelago).resolve()
    source_install = (ap_path / "Generate.py").is_file()
    generator_exe = ap_path / "ArchipelagoGenerate.exe"
    if not source_install and not generator_exe.is_file():
        print(f"No Generate.py or ArchipelagoGenerate.exe in {ap_path}", file=sys.stderr)
        return 2
    if source_install:
        sys.path.insert(0, str(ap_path))


    try:
        import yaml as _yaml
    except ImportError:
        print("Roster needs PyYAML in your Python environment. Run: python -m pip install PyYAML", file=sys.stderr)
        return 2

    games_dir = Path(args.games).resolve()
    if not games_dir.is_dir():
        print("The games folder does not exist.", file=sys.stderr)
        return 2
    yaml_paths = sorted(p for p in games_dir.iterdir() if p.is_file() and p.suffix.lower() in (".yaml", ".yml"))
    if not yaml_paths:
        print(f"No yamls in {games_dir}", file=sys.stderr)
        return 2
    if args.pick > len(yaml_paths):
        print(f"--pick {args.pick} but only {len(yaml_paths)} yamls in {games_dir}", file=sys.stderr)
        return 2

    seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    picker = random.Random(seed)
    # sample returns a seeded random order: sorted source filenames must not
    # determine which selected game gets Game 01, Game 02, and so on.
    chosen = picker.sample(yaml_paths, args.pick)

    documents: dict[Path, dict] = {}
    for path in chosen:
        try:
            with open(path, encoding="utf-8") as handle:
                doc = _yaml.safe_load(handle)
        except (OSError, _yaml.YAMLError):
            print("A selected player YAML could not be read.", file=sys.stderr)
            return 2
        if not isinstance(doc, dict):
            print("A selected player YAML is not a single-document mapping.", file=sys.stderr)
            return 2
        documents[path] = doc

    def game_of(doc: dict, path: Path) -> str:
        game = doc.get("game")
        if isinstance(game, dict):
            game = max(game, key=lambda key: game[key])
        return str(game) if game else path.stem

    mapping = {path: f"Game {index:02d}" for index, path in enumerate(chosen, 1)}
    filenames = {path: f"game_{index:02d}.yaml" for index, path in enumerate(chosen, 1)}

    players_dir = Path(tempfile.mkdtemp(prefix="roster_players_"))
    staging_dir = None
    log_stream = None
    log_path = None
    try:
        for path in chosen:
            doc = documents[path]
            doc["name"] = mapping[path]
            with open(players_dir / filenames[path], "w", encoding="utf-8") as handle:
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
            for path, slot in mapping.items():
                print(f"  {game_of(documents[path], path)!r} -> {slot!r}")

        outputpath = Path(args.outputpath).resolve()
        outputpath.mkdir(parents=True, exist_ok=True)
        log_path = (Path(args.log_file).resolve() if args.log_file else
                    outputpath / f"roster_generate_{seed}_{uuid.uuid4().hex[:8]}.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_stream = log_path.open("a", encoding="utf-8", buffering=1)
        log_phase(log_stream, seed, "prepared; invoking installer" if not source_install else "prepared; invoking source")
        print(f"Generation log: {log_path} (may contain selected games)", flush=True)
        # A private output directory makes freshness unambiguous even when a
        # same-seed archive already exists with a recent/coarse timestamp.
        staging_dir = Path(tempfile.mkdtemp(prefix=".roster_generation_", dir=outputpath))

        gen_argv = [
            "--player_files_path", str(players_dir),
            "--outputpath", str(staging_dir),
            "--seed", str(seed),
            "--spoiler", str(args.spoiler),
            "--multi", "0",
        ]

        cwd = os.getcwd()
        os.chdir(ap_path)
        try:
            if not source_install:
                result = run_installer_generation([str(generator_exe), *gen_argv], log_stream)
                log_phase(log_stream, seed, f"installer exit {result.returncode}")
                if args.verbose:
                    print(log_path.read_text(encoding="utf-8"), end="")
                if result.returncode:
                    print(f"Archipelago generator failed (exit {result.returncode}). See the generation log.", file=sys.stderr)
                    return result.returncode
            else:
                run_source_generation(gen_argv, args.verbose, log_stream)
                log_phase(log_stream, seed, "source generation returned")
        finally:
            os.chdir(cwd)

        log_phase(log_stream, seed, "validating generated output")
        produced = [p for p in staging_dir.iterdir() if p.is_file() and p.suffix.lower() in (".archipelago", ".zip")]
        if len(produced) != 1:
            log_phase(log_stream, seed, "failed: no unique fresh seed archive")
            print("Generation did not produce one fresh seed archive.", file=sys.stderr)
            return 1
        generated = produced[0]
        starting_games = read_starting_games(generated) if result_path else None
        target = outputpath / generated.name
        if target.exists():
            target = outputpath / f"{generated.stem}_{uuid.uuid4().hex[:8]}{generated.suffix}"
        generated.replace(target)

        if target:
            # UT needs the same slot names/options, and doesn't search our
            # temporary generator directory. Exclude the selector itself: its
            # dynamic multiworld data is handled by RosterClient, not UT.
            tracker_dir = outputpath / f"roster_{seed}_tracker"
            if tracker_dir.exists():
                tracker_dir = Path(tempfile.mkdtemp(prefix=f"roster_{seed}_tracker_", dir=outputpath))
            else:
                tracker_dir.mkdir()
            for path in chosen:
                shutil.copy2(players_dir / filenames[path], tracker_dir / filenames[path])
            print(f"Tracker YAMLs: {tracker_dir} (contains selected games)")

        if result_path:
            result_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_result = result_path.with_name(result_path.name + ".tmp-" + uuid.uuid4().hex)
            temporary_result.write_text(json.dumps({"output": str(target.resolve()),
                                                    "tracker_dir": str(tracker_dir.resolve()),
                                                    "starting_games": starting_games}), encoding="utf-8")
            temporary_result.replace(result_path)
        log_phase(log_stream, seed, "complete")
        print(f"Seed: {seed}")
        print(f"Output: {target if target else outputpath}")
        return 0 if target else 1
    except (Exception, SystemExit):
        if log_stream:
            log_phase(log_stream, seed, "failed")
            traceback.print_exc(file=log_stream)
            log_stream.flush()
        if args.verbose:
            raise
        print("Generation failed; no starting games were revealed. Use --verbose only if spoilers are acceptable.",
              file=sys.stderr)
        return 1
    finally:
        if log_stream:
            log_stream.close()
        if staging_dir:
            shutil.rmtree(staging_dir, ignore_errors=True)
        if args.keep_players:
            print(f"Players dir: {players_dir}")
        else:
            shutil.rmtree(players_dir, ignore_errors=True)


def log_phase(stream, seed: int, phase: str) -> None:
    stream.write(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
                 f"pid={os.getpid()} seed={seed} phase={phase}\n")
    stream.flush()


def run_installer_generation(command: list[str], log_stream):
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    return subprocess.run(command, stdout=log_stream, stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL, env=environment,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                          text=True, encoding="utf-8", errors="replace")


class _LiveWriter:
    def __init__(self, stream, echo=None):
        self.stream, self.echo = stream, echo

    def write(self, text):
        result = self.stream.write(text)
        self.stream.flush()
        if self.echo:
            self.echo.write(text)
            self.echo.flush()
        return result

    def flush(self):
        self.stream.flush()
        if self.echo:
            self.echo.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def run_source_generation(gen_argv: list[str], verbose: bool, log_stream=None) -> None:
    import contextlib
    import io
    import logging

    sink = _LiveWriter(log_stream if log_stream is not None else io.StringIO(), sys.stdout if verbose else None)
    logger = logging.getLogger()
    handlers, level = logger.handlers[:], logger.level
    handler = logging.StreamHandler(sink)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    try:
        # Imports can emit diagnostics too. Keep them inside the live capture.
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            import ModuleUpdate
            ModuleUpdate.update_ran = True
            import Generate
            from Main import main as run_generation
            gen_args, gen_seed = Generate.main(Generate.mystery_argparse(gen_argv))
            run_generation(gen_args, gen_seed)
    finally:
        sink.flush()
        logger.handlers = handlers
        logger.setLevel(level)


if __name__ == "__main__":
    raise SystemExit(main())
