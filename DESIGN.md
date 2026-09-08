# Roster

A spoiler-free game selector for Archipelago. You put N game yamls in a folder,
the seed picks K of them, you start with one or two, and the rest are locked
behind "Unlock: <game>" items that live in the multiworld like any other
progression item. The seed is done when every selected game is done.

Nothing here touches Archipelago core. It is one apworld plus a script that
wraps `Generate.py`.

## Who it's for
Two or more friends who want "we have 20 games, tonight's seed is 10 of them,
and we find out which as we go." Everyone connects to whichever game slot they
are playing; several people on one slot is fine.

## Pieces

### 1. `roster_generate.py` (the wrapper)
    python roster_generate.py --games ./games --pick 10 --start 2 --seed 123

- Reads every `*.yaml` in `--games`. One yaml per game, normal AP yaml.
- Picks `--pick` of them with the seed. Refuses if `--pick` > N.
- Copies the chosen yamls to a temp players dir. Sets each `name:` to the
  game name, truncated to AP's 16-character slot limit and de-duplicated.
- Writes one `Roster.yaml` alongside them with `starting_games: --start`.
- Runs Archipelago's `Generate.py` on that dir with `--spoiler 0` by default.
  The spoiler log lists every selected game, so it is off unless asked.
- Prints only the seed and the output path. Not the game list.
- Works around the `ModuleUpdate` version prompt by setting
  `ModuleUpdate.update_ran = True` before importing Generate (same trick used
  for BBFT M0; see that repo).

### 2. `worlds/roster/` (the apworld)
One slot, game name "Roster".

- **Items.** `Unlock: <slot name>` for every non-Roster slot in the multiworld,
  classification progression. `starting_games` of them are precollected at
  random. The rest go in the pool. `starting_games` filler items named
  `Roster Token` are added so item and location counts balance.
- **Locations.** `Started: <slot name>` for every non-Roster slot. Access rule:
  has that slot's unlock. These are the checks the Roster client sends when a
  game is first launched.
- **The gate.** In `stage_generate_basic`, for every non-Roster player, wrap
  every location's access rule and the completion condition with
  `state.has("Unlock: <slot>", roster_player)`. Lambda arguments are bound
  with defaults so each closure captures its own slot.
- **Completion.** Roster's own goal is "has every unlock." Real completion,
  the thing the humans care about, is every game slot goaled on the server.
- **Options.** `starting_games` (int, default 1). `gate_slots` (list of slot
  names, default empty meaning all).
- **Slot data.** The list of gated slots and the starting ones.

### 3. `RosterClient.py`
A `CommonClient` subclass that connects to the Roster slot and stays open in
the background.

- Watches `PrintJSON` join messages. The first time any client joins slot X,
  sends the `Started: X` location check.
- On receiving `Unlock: X`, prints a big obvious line: `UNLOCKED: Dark Souls III`.
- `/started <slot>` as a manual fallback.
- Sends its own goal when it holds every unlock.

## Why it isn't hidden, and what is
Any client's player list shows every slot and its game as soon as it connects.
That is Archipelago behaviour and Roster does not fight it. What stays hidden
is which game unlocks next and where its unlock item sits. That is the fun
part. If the group wants the selection itself hidden, the yaml folder owner
generates and doesn't look.

## Known risks
- Some worlds place their own items in `pre_fill` or assume their sphere 0 is
  reachable from an empty state. Wrapping every rule could break one of them.
  The test generation across ten games is how we find out which.
- Worlds with very few locations may leave the fill nowhere to put unlocks
  early. `accessibility: full` on the Roster yaml is the safety net.
- Slot names longer than 16 characters get truncated. `Kingdom Hearts II`
  becomes `Kingdom Hearts I`. The wrapper prints the mapping it used.

## Relationship to BBFT
BBFT's v1 cross-slot unlock feature is this world. When BBFT gets there it
imports Roster rather than reimplementing the gate.
