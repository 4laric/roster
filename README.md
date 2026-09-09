# Roster

A spoiler-free game selector for [Archipelago](https://archipelago.gg).

Put a yaml for every game you own in a folder. Each seed picks some of them at
random. You start with one or two games unlocked; the rest are locked behind
`Unlock: <game>` items that live in the multiworld like any other progression
item. When someone finds "Unlock: Dark Souls III" in a Hollow Knight chest, you
get to play Dark Souls III. The seed is done when every selected game is done.

Nothing here touches Archipelago itself. It is one apworld, a script that wraps
generation, and a small client.

## What you need

- An **Archipelago source checkout** (not the installer build), Python 3.12.
  `git clone https://github.com/ArchipelagoMW/Archipelago` and
  `pip install -r requirements.txt` in it.
- The apworlds for the games you want, already working in that checkout.
- Everyone playing needs the normal client/mod for each game, as usual.

## Setup

1. Clone this repo next to your Archipelago checkout.
2. Link the world into Archipelago. On Windows (no admin needed):

       New-Item -ItemType Junction -Path "C:\path\to\Archipelago\worlds\roster" -Target "C:\path\to\roster\worlds\roster"

   On Linux/macOS: `ln -s /path/to/roster/worlds/roster /path/to/Archipelago/worlds/roster`
3. Put one yaml per game in `games/`. Normal Archipelago yamls; the `name:` is
   replaced with the game's name at generation time. Sixteen default-option
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
that Archipelago installation first. This support is for generation only; it
does not change `RosterClient.py`'s runtime requirements.
On failure, non-verbose generator output is saved to an output-directory log
instead of revealing selected games in the console.

    python roster_generate.py --games ./games --pick 10 --start 2 --archipelago C:\path\to\Archipelago

- `--pick` how many of the games get selected this seed
- `--start` how many of those are unlocked from the beginning (at least 1)
- `--seed` for a reproducible pick; random otherwise
- `--spoiler` is **0 by default** because the spoiler log names every game

It prints only the seed number and the output file. Host that file the normal
way (`MultiServer.py` or the website's host page).

The generated seed contains one slot per selected game, named after the game,
plus one slot called `Roster`.

## Play

1. Everyone connects to whichever game slot they're playing. Several people on
   one slot is fine.
2. One person also runs the Roster client, connected to the `Roster` slot, and
   leaves it open:

       python RosterClient.py --archipelago C:\path\to\Archipelago

   It marks a game as started the first time anyone joins its slot, prints a
   big `UNLOCKED: <game>` line whenever an unlock arrives, and has `/started <slot>`
   as a manual fallback and `/unlocked` to list what's open.
3. A game is locked until its unlock item is found. Playing it early isn't
   prevented by anything but honour: the server will accept the checks.
4. The seed is done when every game slot has reached its goal.

## What is and isn't hidden

Any client's player list shows every slot and its game as soon as you connect.
That is how Archipelago works and Roster doesn't fight it. What stays hidden is
which game unlocks next and where its unlock sits. If your group wants the
selection itself hidden too, have the person who generates not look.

## Known limits

- `--start 0` can't generate: with nothing unlocked there's nowhere to place the
  first item.
- Spoiler levels above 1 can fail on big rosters. The seed is fine; it's a
  quirk of Archipelago's playthrough log. Small rosters (four games) produce a
  full log without trouble.
- Slot names are cut to Archipelago's 16 characters. `Kingdom Hearts II` becomes
  `Kingdom Hearts I`. The script prints the mapping.
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
