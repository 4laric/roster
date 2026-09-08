# Roster Setup Guide

## Required Software

- An Archipelago install with the Roster apworld.
- `RosterClient.py` from the Roster repository.

## Generating a seed

Use `roster_generate.py` from the Roster repository:

```
python roster_generate.py --games ./games --pick 10 --start 2
```

It picks `--pick` yamls out of your `games` folder, names each slot after its
game, adds a `Roster.yaml` with `starting_games: --start`, and runs Archipelago's
`Generate.py` with the spoiler log off.

## Playing

Start `RosterClient.py` and connect it to the Roster slot. It sends a
`Started: <slot>` check the first time any client joins a slot, prints a loud
`UNLOCKED:` line whenever an unlock arrives, and sends its own goal once it holds
every unlock. `/started <slot>` is the manual fallback.
