# Roster candidate yamls

One yaml per game, each on that world's default options, PC-native and needing no
ROM or external file at generation time. `roster_generate.py` picks `--pick` of
these and renames the slot after the game.

## Known-incompatible worlds

None found so far. Every world in this folder has generated under the Roster gate
in the seed 1-10 sweep (see the repo's commit message / DESIGN Findings).

Worlds deliberately kept out of this folder:

- Anything needing a ROM or a game install at generation time (all console worlds,
  Factorio's mod output is fine but ROM worlds are not).
- Worlds whose default options make a very small location pool; with too few
  locations the fill has nowhere early to put unlocks. `accessibility: full` on
  the generated `Roster.yaml` is the safety net, but a tiny world plus a large
  `--pick` can still fail the fill.

## Note on `--start`

`--start 0` cannot generate: with no game unlocked, sphere 0 is empty and the fill
has nowhere to place anything. Use `--start 1` or more.
