# Roster

A spoiler-light game selector for [Archipelago](https://archipelago.gg).

Put a yaml for every game you own in a folder. Each seed picks some of them at
random. You start with one or two games unlocked; the rest are locked behind
`Unlock: <slot>` items that live in the multiworld like any other progression
item. When someone finds `Unlock: Game 01`, the Roster client reveals the game,
for example **Game 01 — Balatro**, and you get to play it. The seed is done when every selected game is done.

Nothing here touches Archipelago itself. It is one apworld, a script that wraps
generation, and a small client.

## Launcher

On Windows, extract the portable `Roster-Windows.zip` and open
`RosterLauncher.exe`. It includes Python and its dependencies; Archipelago and
each candidate game's apworld still need to be installed separately.

From a clone, install `PyYAML` and `websockets` into your Python environment,
then double-click `StartRoster.cmd` or run `python RosterLauncher.py`.

1. Browse to your Archipelago installation and your folder of candidate YAMLs.
2. Click **Install Roster world** if Roster is not already installed.
3. Choose how many games to pick and how many start unlocked, then **Generate seed**.
4. The launcher displays the actual starting games and the generated ZIP path.
   Upload that ZIP with **Host on Archipelago**. Keep the local ZIP for recovery.
5. Enter the hosted room address and click **Start Roster client**. Leave it open.

Existing worlds are preserved by the install button. Source world copies update
with `git pull`; move an old `roster.apworld` out of `custom_worlds` before installing
its replacement. This does not modify an already generated room.

Only starting games are shown after generation. Full generator diagnostics,
tracker YAML contents, and AP's web pages may reveal other games.

While generating, the launcher shows elapsed time, time since the last log
update, and the diagnostic log path. **Show diagnostic logs** opens the output
folder. `roster_generate_<run>.log` contains live generator output;
`roster_worker_<run>.log` covers worker startup errors. These files may contain
spoilers. **Cancel generation** stops that launcher's worker and its child
processes on Windows; logs remain available. A silent log alone does not prove
generation is stuck, and some games can open a required-file dialog.

For older launchers, look in the Archipelago installation's `logs` folder for
the newest `Generate_*.txt`. Old launcher failure logs appear only after the
generator exits. The current launcher prevents the generator's console input
prompts from waiting invisibly.

To build the portable ZIP yourself: install `PyInstaller`, `PyYAML`, and
`websockets`, then run `python build_launcher.py`. The bundle is written to
`output/Roster-Windows.zip`. The EXE generates with the Windows Archipelago
installer; use the Python launcher for Archipelago source checkouts.

## Roster-aware Universal Tracker

Stock Universal Tracker reconstructs each game independently and does not apply
Roster's cross-game lock. Its green checks are therefore not proof that a locked
game is reachable in the generated multiworld.

The optional [source tracker bridge](docs/tracker-bridge.md) gates the actual
tracker rules using the Roster client's current unlock state. Missing, stale,
disconnected, or wrong-seed state keeps the tracked game locked. Use **Start
gated tracker (source only)** in the Python launcher after configuring a source
checkout with Universal Tracker. The stock installer tracker cannot load this
bridge; the portable EXE does not claim to gate it.

## What you need

- An **Archipelago source checkout or Windows installation**, plus Python 3.12
  and PyYAML for the generation wrapper. Source checkouts also need their
  `requirements.txt` installed in your Python environment.
- The Roster apworld and the apworlds for the games you want, already working in
  that Archipelago installation.
- Everyone playing needs the normal client/mod for each game, as usual.

## Setup

1. Clone this repo.
2. For a source checkout, link the world into Archipelago. On Windows (no admin needed):

       New-Item -ItemType Junction -Path "C:\path\to\Archipelago\worlds\roster" -Target "C:\path\to\roster\worlds\roster"

   On Linux/macOS: `ln -s /path/to/roster/worlds/roster /path/to/Archipelago/worlds/roster`

   For the Windows installer, install `roster.apworld` through Archipelago
   instead of creating a source junction.
3. Put one yaml per game in `games/`. Normal Archipelago yamls; the `name:` is
   replaced with a neutral slot name such as `Game 01` at generation time. Sixteen default-option
   yamls for PC games are included to start from.

## Generate a seed

The wrapper accepts either a source checkout (`Generate.py`) or a Windows
installation (`ArchipelagoGenerate.exe`). For an installer at `D:\Archipelago`:

```powershell
python -m pip install PyYAML
python roster_generate.py --games ./games --pick 10 --start 2 --archipelago "D:\Archipelago"
```

The wrapper needs Python and PyYAML; the installer runs generation with its own
bundled runtime. Install the Roster world and each selected game's world into
that Archipelago installation first. The client also supports installer-only
setups through a standalone console mode, described below.
Generator output is written live to an output-directory log instead of
revealing selected games in the console. Use `--log-file PATH` to choose its
location; the default filename includes the seed and a unique suffix.

    python roster_generate.py --games ./games --pick 10 --start 2 --archipelago C:\path\to\Archipelago

- `--pick` how many of the games get selected this seed
- `--start` how many of those are unlocked from the beginning (at least 1)
- `--seed` for a reproducible pick; random otherwise
- `--spoiler` is **0 by default** because the spoiler log names every game

It prints the seed number, output file and tracker YAML directory. Host that file the normal
way (`MultiServer.py` or the website's host page).

The generated seed contains one neutral slot per selected game (`Game 01`,
`Game 02`, and so on), plus one slot called `Roster`.

## Play

1. After a game is revealed, connect its normal game client using the neutral
   slot name: for **Game 01 — Balatro**, connect as `Game 01`. Several people on
   one slot is fine.
2. One person also runs the Roster client, connected to the `Roster` slot, and
   leaves it open:

       python RosterClient.py --archipelago C:\path\to\Archipelago

   It marks an unlocked game as started when a game client joins its slot, prints a
   line such as `Game 01 — Balatro` whenever an unlock arrives, and has `/started <slot>`
   as a manual fallback and `/unlocked` to list what's open.
3. A game is locked until its unlock item is found. Playing it early isn't
   prevented by anything but honour: the server will accept the checks.
4. The seed is done when every game slot has reached its goal.

### Client with an installed Archipelago distribution

You do not need a source checkout for the Roster client. Install its standalone
network dependency into the Python environment used to launch it:

```powershell
python -m pip install websockets
python RosterClient.py --archipelago "D:\Archipelago" --name Roster --connect "archipelago.gg:38281"
```

Replace the address with your hosted room's address. Without `--connect`, use
`/connect host:port` in the console. The wrapper automatically selects standalone
console mode when `CommonClient.py` is absent; source checkouts retain the
existing Archipelago client and optional GUI. Keep `RosterStandalone.py` beside
`RosterClient.py` (a normal `git pull` supplies both).

Connect this client as **Roster**, not as one of the selected games. It announces
the starting games after login and automatically completes its own slot when
every game is unlocked. For encrypted hosts you can use `/connect wss://host:port`;
the client also retries with encryption after an invalid plain WebSocket handshake.

Standalone mode supports `/started <slot>`, `/unlocked`, `/connect <address>`,
and `/exit`. It reconnects after network interruptions and retains unacknowledged
Started checks for replay. Run it before other players join; joining before the
Roster client connects needs the manual `/started` fallback. A full client restart
also loses unacknowledged local events, so use `/started` if a join was missed.
Tracker, text-only, and hint-client connections do not send Started checks.
Both automatic starts and `/started` require the slot to be unlocked. A client
that joined while locked must reconnect after the unlock or use `/started`.

## What is and isn't hidden

### Universal Tracker YAMLs

After successful generation, `output/roster_<seed>_tracker` retains the selected
game YAMLs with the exact slot names passed to generation. New seeds use neutral
slots `Game 01`, `Game 02`, etc. and matching `game_01.yaml`, `game_02.yaml`
tracker files. The seed deterministically randomizes assignment, so alphabetical
source filenames do not reveal which game each neutral slot represents. These files reveal
the selection if opened; ordinary directory listings and console output do not
name the selected games. Temporary player YAMLs use the same neutral filenames.
For **Game 01 — Balatro**, copy only `game_01.yaml` into the tracker's `Players`
folder and connect Universal Tracker as `Game 01`. Keep other selected YAMLs
out of that folder to avoid accidental reveals. Do not include the generated `Roster.yaml` in UT's input; run
RosterClient separately for the selector slot.

For an older seed, copy the original game's YAML and change only its top-level
`name` to the generated slot name (for example `Balatro`). Keep its game options
unchanged. UT still requires a compatible game apworld; weighted/random options
may require the actual rolled values or game-specific UT support. This export
does not by itself guarantee tracker compatibility.

Neutral names reduce accidental spoilers; they do not conceal Archipelago
metadata. YAML contents, generated zip contents, web trackers and clients that
show game metadata can still expose the selection. `--verbose`, spoiler logs and
failure logs can also reveal it. Avoid inspecting those when playing blind.
Existing rooms keep their original slot names and tracker YAMLs; regenerate only
when starting a new room, not to rename an ongoing seed.

## Known limits

- `--start 0` can't generate: with nothing unlocked there's nowhere to place the
  first item.
- Spoiler levels above 1 can fail on big rosters. The seed is fine; it's a
  quirk of Archipelago's playthrough log. Small rosters (four games) produce a
  full log without trouble.
- New slots use sequential neutral names. `--verbose` prints their game mapping
  and generator output, so leave it off when avoiding spoilers.
- If Archipelago stops on a "module update" prompt, the script bypasses it for
  you; if you see the prompt anyway, run generation once by hand and answer it.

## How it works

Archipelago's state object is multiworld-wide, so a rule in one slot can
require an item owned by another. The Roster world adds `Unlock: <slot>` items
and, after every other world has set its rules, wraps every location and the
goal of each game slot with "has that slot's unlock." The fill then treats the
unlocks as real progression and places them somewhere reachable. Each game also
gets a `Started: <slot>` location so item and location counts balance; those are
the checks the client sends.

Details in [DESIGN.md](DESIGN.md).
