#!/usr/bin/env python3
"""RosterClient: the client for the Roster selector slot.

    python RosterClient.py --name Roster archipelago.gg:38281

It connects to the Roster slot and sits in the background:

- Watches join messages. The first time any client joins slot X, it sends the
  ``Started: X`` location check.
- Prints a loud ``UNLOCKED: <game>`` line whenever an ``Unlock:`` item arrives.
- ``/started <slot>`` is the manual fallback.
- Sends its own goal once it holds every unlock.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

DEFAULT_ARCHIPELAGO = os.environ.get("ARCHIPELAGO_PATH", r"C:\Users\alari\Archipelago")


def _bootstrap(archipelago_path: str) -> None:
    """Put the Archipelago checkout on sys.path without tripping ModuleUpdate's prompt."""
    if archipelago_path and archipelago_path not in sys.path:
        sys.path.insert(0, archipelago_path)
    import ModuleUpdate

    ModuleUpdate.update_ran = True


def _pre_parse_archipelago(argv: list[str]) -> tuple[str, list[str]]:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--archipelago", default=DEFAULT_ARCHIPELAGO)
    known, rest = pre.parse_known_args(argv)
    return known.archipelago, rest


ARCHIPELAGO_PATH, _REST_ARGV = _pre_parse_archipelago(sys.argv[1:])
_bootstrap(ARCHIPELAGO_PATH)

import Utils  # noqa: E402
from CommonClient import (  # noqa: E402
    ClientCommandProcessor,
    CommonContext,
    get_base_parser,
    gui_enabled,
    logger,
    server_loop,
)
from NetUtils import ClientStatus  # noqa: E402

GAME_NAME = "Roster"
UNLOCK_PREFIX = "Unlock: "
STARTED_PREFIX = "Started: "


class RosterCommandProcessor(ClientCommandProcessor):
    def _cmd_started(self, slot_name: str = "") -> bool:
        """Manually mark a slot as started, sending its Started check."""
        if not slot_name:
            self.output("Usage: /started <slot name>")
            return False
        return self.ctx.mark_started(slot_name, manual=True)

    def _cmd_unlocked(self) -> bool:
        """List the unlocks this Roster slot currently holds."""
        if not self.ctx.unlocked:
            self.output("No games unlocked yet.")
        for name in sorted(self.ctx.unlocked):
            self.output(f"UNLOCKED: {name}")
        return True


class RosterContext(CommonContext):
    command_processor = RosterCommandProcessor
    game = GAME_NAME
    items_handling = 0b111  # full remote items

    def __init__(self, server_address: str | None, password: str | None) -> None:
        super().__init__(server_address, password)
        self.unlocked: set[str] = set()
        self.started_slots: set[str] = set()
        self.gated_slots: set[str] = set()

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    # ------------------------------------------------------------------ helpers

    def _started_location_ids(self) -> dict[str, int]:
        """slot name -> location id, read out of the datapackage the server handed us."""
        mapping: dict[str, int] = {}
        for loc_id in self.server_locations:
            name = self.location_names.lookup_in_game(loc_id, GAME_NAME)
            if isinstance(name, str) and name.startswith(STARTED_PREFIX):
                mapping[name[len(STARTED_PREFIX):]] = loc_id
        return mapping

    def mark_started(self, slot_name: str, manual: bool = False) -> bool:
        if slot_name in self.started_slots:
            return True
        mapping = self._started_location_ids()
        location_id = mapping.get(slot_name)
        if location_id is None:
            if manual:
                logger.info(f"No 'Started: {slot_name}' check exists. Known: {sorted(mapping)}")
            return False
        self.started_slots.add(slot_name)
        logger.info(f"Started: {slot_name}")
        Utils.async_start(self.check_locations([location_id]), name="roster started check")
        return True

    def _check_goal(self) -> None:
        mapping = self._started_location_ids()
        if not mapping or self.finished_game:
            return
        if all(slot in self.unlocked for slot in mapping):
            logger.info("Every game is unlocked. Sending Roster goal.")
            self.finished_game = True
            Utils.async_start(
                self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]),
                name="roster goal",
            )

    # ------------------------------------------------------------------ network

    def on_package(self, cmd: str, args: dict) -> None:
        if cmd == "Connected":
            self.gated_slots = set(args.get("slot_data", {}).get("gated_slots", {}).values())
            for slot_name in args.get("slot_data", {}).get("starting_slots", []):
                logger.info(f"UNLOCKED: {slot_name}  (starting game)")
                self.unlocked.add(slot_name)

        elif cmd == "ReceivedItems":
            for item in args["items"]:
                name = self.item_names.lookup_in_game(item.item, GAME_NAME)
                if isinstance(name, str) and name.startswith(UNLOCK_PREFIX):
                    slot_name = name[len(UNLOCK_PREFIX):]
                    if slot_name not in self.unlocked:
                        self.unlocked.add(slot_name)
                        logger.info("=" * 60)
                        logger.info(f"UNLOCKED: {slot_name}")
                        logger.info("=" * 60)
            self._check_goal()

        elif cmd == "PrintJSON":
            if args.get("type") in ("Join", "Connect"):
                slot = args.get("slot")
                if slot is not None:
                    slot_name = self.player_names.get(slot)
                    if slot_name and slot_name != self.auth:
                        self.mark_started(slot_name)

        elif cmd == "RoomUpdate":
            self._check_goal()

    def run_gui(self) -> None:
        from kvui import GameManager

        class RosterManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Archipelago Roster Client"

        self.ui = RosterManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")


async def _main(args) -> None:
    ctx = RosterContext(args.connect, args.password)
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")

    if gui_enabled:
        ctx.run_gui()
    ctx.run_cli()

    await ctx.exit_event.wait()
    await ctx.shutdown()


def main(argv: list[str] | None = None) -> None:
    import colorama

    parser = get_base_parser(description="Archipelago Roster Client")
    parser.add_argument("--name", default="Roster", help="Slot name to connect as. Defaults to 'Roster'.")
    parser.add_argument("--archipelago", default=DEFAULT_ARCHIPELAGO, help="Path to the Archipelago checkout.")
    parser.add_argument("url", nargs="?", help="Archipelago connection url")
    args = parser.parse_args(_REST_ARGV if argv is None else argv)

    if args.url:
        import urllib.parse

        url = urllib.parse.urlparse(args.url)
        args.connect = url.netloc
        if url.username:
            args.name = urllib.parse.unquote(url.username)
        if url.password:
            args.password = urllib.parse.unquote(url.password)

    colorama.just_fix_windows_console()
    asyncio.run(_main(args))
    colorama.deinit()


if __name__ == "__main__":
    import logging

    logging.getLogger().setLevel(logging.INFO)
    main()
