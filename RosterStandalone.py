#!/usr/bin/env python3
"""Installer-compatible Roster console client: stdlib plus websockets only.

This module never imports the Archipelago checkout or frozen installer modules.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import queue
import sys
import threading
import uuid
from urllib.parse import unquote, urlsplit, urlunsplit

GAME_NAME = "Roster"
STARTED_PREFIX = "Started: "
UNLOCK_PREFIX = "Unlock: "
CLIENT_VERSION = {"major": 0, "minor": 6, "build": 0, "class": "Version"}


def parse_connection(address: str, name: str = "Roster", password: str | None = None):
    """Normalize a bare host:port or AP/websocket URI without leaking credentials."""
    address = address.strip()
    if "://" not in address:
        address = "ws://" + address
    parts = urlsplit(address)
    scheme = "ws" if parts.scheme == "archipelago" else parts.scheme
    if scheme not in ("ws", "wss") or not parts.hostname:
        raise ValueError("Use host:port, archipelago://host:port, ws:// or wss://")
    port = parts.port or 38281
    host = parts.hostname
    if ":" in host:
        host = f"[{host}]"
    if parts.username is not None:
        name = unquote(parts.username)
    if parts.password is not None:
        password = unquote(parts.password)
    return urlunsplit((scheme, f"{host}:{port}", parts.path, parts.query, "")), name, password


class DifferentSeedError(RuntimeError):
    pass


class RosterStandaloneClient:
    def __init__(self, address=None, name="Roster", password=None, output=print):
        self.address = None
        self.name, self.password = name, password
        if address:
            self.address, self.name, self.password = parse_connection(address, name, password)
        self.output = output
        self.socket = None
        self.authenticated = False
        self.team = self.slot = None
        self.seed_name = None
        self.client_uuid = str(uuid.uuid4())
        self.player_names = {}
        self.players = {}  # (team, slot) -> canonical name; aliases aren't location names.
        self.pending_joins = set()
        self.location_ids = {}  # "Started: X" -> ID
        self.item_names = {}  # ID -> "Unlock: X"
        self.server_locations = set()
        self.checked_locations = set()
        self.missing_locations = set()
        self.pending_checks = set()  # Names retained until the server acknowledges.
        self.sent_checks = set()  # Suppress repeat sends within this connection.
        self.started_slots = set()
        self.gated_slots = set()
        self.unlocked = set()
        self.items_received = []
        self.finished_game = False
        self.goal_sent = False
        self.sync_requested = False
        self.exit_event = asyncio.Event()
        self.reconnect_event = asyncio.Event()

    async def send_msgs(self, messages):
        if self.socket is not None:
            await self.socket.send(json.dumps(messages))

    def _consume_players(self, players):
        for player in players:
            if isinstance(player, dict):
                team, slot = player.get("team"), player.get("slot")
                name = player.get("name") or player.get("alias")
            elif isinstance(player, (list, tuple)) and len(player) >= 4:
                team, slot, _alias, name = player[:4]
            else:
                continue
            if isinstance(team, int) and isinstance(slot, int) and isinstance(name, str):
                self.players[(team, slot)] = name
        if self.team is not None:
            self.player_names = {slot: name for (team, slot), name in self.players.items() if team == self.team}

    def _started_location_ids(self):
        return {name[len(STARTED_PREFIX):]: location for name, location in self.location_ids.items()
                if name.startswith(STARTED_PREFIX) and location in self.server_locations}

    async def mark_started(self, slot_name, manual=False):
        mapping = self._started_location_ids()
        if slot_name not in mapping:
            if manual:
                self.output(f"No 'Started: {slot_name}' check exists. Known: {sorted(mapping)}")
            return False
        if slot_name not in self.started_slots:
            self.started_slots.add(slot_name)
            self.output(f"Started: {slot_name}")
        if mapping[slot_name] not in self.checked_locations:
            self.pending_checks.add(slot_name)
        await self.flush_checks()
        return True

    async def flush_checks(self):
        if not self.authenticated:
            return
        mapping = self._started_location_ids()
        self.pending_checks = {name for name in self.pending_checks
                               if mapping.get(name) not in self.checked_locations}
        ids = {mapping[name] for name in self.pending_checks if name in mapping}
        ids &= self.missing_locations
        ids -= self.sent_checks
        if ids:
            await self.send_msgs([{"cmd": "LocationChecks", "locations": sorted(ids)}])
            self.sent_checks.update(ids)

    async def _resolve_joins(self):
        if not self.authenticated:
            return
        for team, slot in list(self.pending_joins):
            if team != self.team or slot == self.slot:
                self.pending_joins.discard((team, slot))
                continue
            name = self.player_names.get(slot)
            if name and await self.mark_started(name):
                self.pending_joins.discard((team, slot))

    def _announce_unlock(self, name, starting=False):
        if name not in self.unlocked:
            self.unlocked.add(name)
            self.output(f"UNLOCKED: {name}" + ("  (starting game)" if starting else ""))

    async def _resolve_items(self):
        for item in self.items_received:
            item_id = item.get("item") if isinstance(item, dict) else item[0]
            name = self.item_names.get(item_id)
            if name and name.startswith(UNLOCK_PREFIX):
                self._announce_unlock(name[len(UNLOCK_PREFIX):])
        await self._check_goal()

    async def _check_goal(self):
        mapping = self._started_location_ids()
        if mapping and all(name in self.unlocked for name in mapping):
            if not self.finished_game:
                self.output("Every game is unlocked. Sending Roster goal.")
            self.finished_game = True
        if self.authenticated and self.finished_game and not self.goal_sent:
            await self.send_msgs([{"cmd": "StatusUpdate", "status": 30}])
            self.goal_sent = True

    async def handle_packet(self, packet):
        cmd = packet.get("cmd")
        if cmd == "RoomInfo":
            seed = packet.get("seed_name")
            if self.seed_name is not None and seed != self.seed_name:
                raise DifferentSeedError("Server has a different seed. Restart the client to join it safely.")
            self.seed_name = seed
            if packet.get("password") and not self.password:
                self.output("Server requires a password; restart with --password PASSWORD.")
            await self.send_msgs([
                {"cmd": "GetDataPackage", "games": [GAME_NAME]},
                {"cmd": "Connect", "game": GAME_NAME, "name": self.name,
                 "password": self.password, "uuid": self.client_uuid,
                 "version": CLIENT_VERSION, "items_handling": 7, "tags": ["AP"], "slot_data": True},
            ])
        elif cmd == "ConnectionRefused":
            self.output("Connection refused: " + ", ".join(map(str, packet.get("errors", []))))
            self.output("Check --name/--password and ensure this slot uses the Roster world.")
            # Keep the local console alive for /connect; don't spin on bad credentials.
            self.address = None
            if self.socket is not None:
                await self.socket.close()
        elif cmd == "DataPackage":
            data = packet.get("data", {}).get("games", {}).get(GAME_NAME, {})
            if data:
                self.location_ids = dict(data.get("location_name_to_id", {}))
                self.item_names = {value: name for name, value in data.get("item_name_to_id", {}).items()}
                await self._resolve_joins()
                await self.flush_checks()
                await self._resolve_items()
        elif cmd == "Connected":
            self.team, self.slot = packet["team"], packet["slot"]
            self.authenticated = True
            self.sent_checks.clear()
            self.goal_sent = False
            self.items_received = []
            self.sync_requested = False
            self._consume_players(packet.get("players", []))
            self.checked_locations = set(packet.get("checked_locations", []))
            self.missing_locations = set(packet.get("missing_locations", []))
            self.server_locations = self.checked_locations | self.missing_locations
            data = packet.get("slot_data") or {}
            gated = data.get("gated_slots", {})
            self.gated_slots = set(gated.values() if isinstance(gated, dict) else gated)
            for name in data.get("starting_slots", []):
                self._announce_unlock(name, starting=True)
            self.output(f"Connected as {self.name} (team {self.team + 1}, slot {self.slot}).")
            # The full player roster is not proof that any other client joined.
            await self._resolve_joins()
            await self.flush_checks()
            await self._resolve_items()
        elif cmd == "ReceivedItems":
            index = packet.get("index", 0)
            items = packet.get("items", [])
            if index == 0:
                self.items_received = list(items)
                self.sync_requested = False
            elif index == len(self.items_received):
                self.items_received.extend(items)
            elif 0 <= index < len(self.items_received) and self.items_received[index:index + len(items)] == items:
                return  # A duplicate delivery of already accepted entries.
            else:
                if not self.sync_requested:
                    await self.send_msgs([{"cmd": "Sync"}])
                    self.sync_requested = True
                return
            await self._resolve_items()
        elif cmd == "PrintJSON" and packet.get("type") in ("Join", "Connect"):
            slot = packet.get("slot")
            team = packet.get("team", self.team)
            if isinstance(slot, int) and isinstance(team, int):
                self.pending_joins.add((team, slot))
                await self._resolve_joins()
        elif cmd == "RoomUpdate":
            self._consume_players(packet.get("players", []))
            checked = set(packet.get("checked_locations", []))
            self.checked_locations |= checked
            self.missing_locations -= checked
            await self._resolve_joins()
            await self.flush_checks()
            await self._check_goal()
        elif cmd == "Print":
            self.output(str(packet.get("text", "")))

    async def command(self, line):
        command, _, argument = line.strip().partition(" ")
        argument = argument.strip()
        if command in ("/exit", "/quit"):
            self.exit_event.set()
            self.reconnect_event.set()
            if self.socket is not None:
                await self.socket.close()
        elif command == "/started":
            if argument:
                await self.mark_started(argument, manual=True)
            else:
                self.output("Usage: /started <slot name>")
        elif command == "/unlocked":
            if not self.authenticated:
                self.output("Not connected to the Roster slot. Unlocks below are cached; connect first to get current starting games.")
            for name in sorted(self.unlocked):
                self.output(f"UNLOCKED: {name}")
            if not self.unlocked and self.authenticated:
                self.output("No games unlocked yet.")
        elif command == "/connect":
            if not argument:
                self.output("Usage: /connect host:port (or archipelago://name:password@host:port)")
                return
            try:
                self.address, self.name, self.password = parse_connection(argument, self.name, self.password)
            except ValueError as exc:
                self.output(str(exc))
                return
            self.reconnect_event.set()
            if self.socket is not None:
                await self.socket.close()
        elif command:
            self.output("Commands: /started <slot>, /unlocked, /connect <address>, /exit. No chat is sent.")

    async def run(self, websocket_connect):
        from websockets.exceptions import InvalidMessage

        delay = 1
        while not self.exit_event.is_set():
            if not self.address:
                await self.reconnect_event.wait()
                self.reconnect_event.clear()
                continue
            self.reconnect_event.clear()
            try:
                async with websocket_connect(self.address, ping_interval=20, open_timeout=10) as socket:
                    self.socket = socket
                    self.authenticated = False
                    delay = 1
                    async for raw in socket:
                        packets = json.loads(raw)
                        if not isinstance(packets, list):
                            continue
                        for packet in packets:
                            if isinstance(packet, dict):
                                await self.handle_packet(packet)
            except asyncio.CancelledError:
                raise
            except DifferentSeedError as exc:
                self.output(str(exc))
                self.address = None
            except Exception as exc:
                # Match CommonClient: a TLS-only AP endpoint may close a plain
                # websocket handshake without returning a valid HTTP response.
                if isinstance(exc, InvalidMessage) and self.address and self.address.startswith("ws://"):
                    self.address = "wss://" + self.address[len("ws://"):]
                    self.output("Server may require encryption; retrying with wss://.")
                    continue
                # Exception strings from websocket libraries can contain a URL;
                # normalized self.address never contains login credentials.
                self.output(f"Connection lost ({type(exc).__name__}); pending checks retained.")
            finally:
                self.socket = None
                self.authenticated = False
                self.sent_checks.clear()
            if self.exit_event.is_set():
                break
            if self.address:
                self.output(f"Reconnecting in {delay} seconds...")
                try:
                    await asyncio.wait_for(self.reconnect_event.wait(), delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(delay * 2, 30)


async def _main(args, websocket_connect):
    client = RosterStandaloneClient(args.connect or args.url, args.name, args.password)
    commands = queue.Queue()

    def read_console():
        # A daemon reader avoids asyncio executor shutdown hanging on input().
        for line in sys.stdin:
            commands.put(line)
    threading.Thread(target=read_console, daemon=True).start()
    network = asyncio.create_task(client.run(websocket_connect))
    client.output("Roster client. Commands: /started <slot>, /unlocked, /connect <address>, /exit")
    if not client.address:
        client.output("Use /connect host:port to connect.")
    try:
        while not client.exit_event.is_set():
            while not commands.empty():
                await client.command(commands.get_nowait())
            await asyncio.sleep(0.1)
    finally:
        network.cancel()
        await asyncio.gather(network, return_exceptions=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Standalone Archipelago Roster client")
    parser.add_argument("--name", default="Roster")
    parser.add_argument("--connect")
    parser.add_argument("--password")
    parser.add_argument("--archipelago", help="Accepted for launcher compatibility; not used")
    parser.add_argument("--nogui", action="store_true", help="Accepted; this client is console-only")
    parser.add_argument("url", nargs="?")
    args = parser.parse_args(argv)
    try:
        import websockets
    except ImportError:
        print("Missing websockets. Install it for this Python: python -m pip install websockets", file=sys.stderr)
        return 1
    try:
        asyncio.run(_main(args, websockets.connect))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
