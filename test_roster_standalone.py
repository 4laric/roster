import unittest
from unittest.mock import AsyncMock

from RosterStandalone import RosterStandaloneClient, parse_connection


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_game_names_revealed_only_after_unlock(self):
        output = []
        client = RosterStandaloneClient(output=output.append)
        client.send_msgs = AsyncMock()
        await client.handle_packet({
            "cmd": "Connected", "team": 0, "slot": 3,
            "slot_info": {
                "1": {"name": "Game 01", "game": "Balatro"},
                "2": {"name": "Game 02", "game": "Secret Game"},
            },
            "missing_locations": [101, 102],
            "slot_data": {"starting_slots": ["Game 01"]},
        })
        await client.handle_packet({"cmd": "DataPackage", "data": {"games": {"Roster": {
            "item_name_to_id": {"Unlock: Game 02": 202},
            "location_name_to_id": {"Started: Game 01": 101, "Started: Game 02": 102},
        }}}})
        await client.command("/unlocked")
        await client.command("/started nonexistent")
        self.assertIn("UNLOCKED: Game 01 — Balatro  (starting game)", output)
        self.assertNotIn("Secret Game", "\n".join(output))
        await client.handle_packet({"cmd": "ReceivedItems", "index": 0, "items": [{"item": 202}]})
        self.assertIn("UNLOCKED: Game 02 — Secret Game", output)
        output.clear()
        await client.command("/unlocked")
        self.assertIn("UNLOCKED: Game 02 — Secret Game", output)

    async def test_tls_retry_and_disconnected_unlock_message(self):
        from websockets.exceptions import InvalidMessage
        output, attempts = [], []
        client = RosterStandaloneClient("localhost:38281", output=output.append)
        await client.command("/unlocked")
        self.assertTrue(any("Not connected" in line for line in output))
        self.assertNotIn("No games unlocked yet.", output)

        class Connection:
            async def __aenter__(self):
                if len(attempts) == 1:
                    raise InvalidMessage("TLS endpoint")
                client.exit_event.set()
                return self

            async def __aexit__(self, *args):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        def connect(address, **kwargs):
            attempts.append(address)
            return Connection()

        await client.run(connect)
        self.assertEqual(attempts, ["ws://localhost:38281", "wss://localhost:38281"])

    async def make_client(self):
        output = []
        client = RosterStandaloneClient(name="Roster", output=output.append)
        client.send_msgs = AsyncMock()
        await client.handle_packet({
            "cmd": "Connected", "team": 0, "slot": 1,
            "players": [
                {"team": 0, "slot": 1, "name": "Roster", "alias": "Roster"},
                {"team": 0, "slot": 2, "name": "Game A", "alias": "Alias A"},
            ],
            "missing_locations": [100], "checked_locations": [],
            "slot_data": {"gated_slots": {"2": "Game A"}, "starting_slots": []},
        })
        return client, output

    async def test_late_datapackage_unlock_goal_and_duplicate_join(self):
        client, output = await self.make_client()
        # The player roster is not evidence anybody has joined a game.
        self.assertFalse(client.started_slots)
        await client.handle_packet({"cmd": "ReceivedItems", "index": 0,
                                    "items": [{"item": 200, "location": -2, "player": 1, "flags": 1}]})
        self.assertFalse(client.unlocked)
        await client.handle_packet({"cmd": "DataPackage", "data": {"games": {"Roster": {
            "item_name_to_id": {"Unlock: Game A": 200},
            "location_name_to_id": {"Started: Game A": 100},
        }}}})
        self.assertEqual(client.unlocked, {"Game A"})
        packets = [p for call in client.send_msgs.call_args_list for p in call.args[0]]
        self.assertIn({"cmd": "StatusUpdate", "status": 30}, packets)
        client.send_msgs.reset_mock()
        join = {"cmd": "PrintJSON", "type": "Join", "team": 0, "slot": 2}
        await client.handle_packet(dict(join, team=1))
        self.assertFalse(client.started_slots)
        await client.handle_packet(join)
        await client.handle_packet(join)
        packets = [p for call in client.send_msgs.call_args_list for p in call.args[0]]
        checks = [p for p in packets if p["cmd"] == "LocationChecks"]
        self.assertEqual(checks, [{"cmd": "LocationChecks", "locations": [100]}])
        self.assertTrue(any("UNLOCKED: Game A" in line for line in output))

    def test_connection_addresses(self):
        url, name, password = parse_connection("localhost:38281", "Roster", None)
        self.assertEqual(url, "ws://localhost:38281")
        url, name, password = parse_connection("archipelago://Roster:secret@localhost:38281", "Other", None)
        self.assertEqual((url, name, password), ("ws://localhost:38281", "Roster", "secret"))

    async def test_gap_sync_and_check_replay_until_acknowledged(self):
        client, _ = await self.make_client()
        await client.handle_packet({"cmd": "DataPackage", "data": {"games": {"Roster": {
            "item_name_to_id": {"Unlock: Game A": 200},
            "location_name_to_id": {"Started: Game A": 100},
        }}}})
        client.send_msgs.reset_mock()
        gap = {"cmd": "ReceivedItems", "index": 3, "items": [{"item": 200}]}
        await client.handle_packet(gap)
        await client.handle_packet(gap)
        client.send_msgs.assert_awaited_once_with([{"cmd": "Sync"}])
        await client.mark_started("Game A")
        self.assertEqual(client.pending_checks, {"Game A"})
        client.sent_checks.clear()  # Simulate a dropped connection before acknowledgment.
        client.send_msgs.reset_mock()
        await client.flush_checks()
        client.send_msgs.assert_awaited_once_with([{"cmd": "LocationChecks", "locations": [100]}])
        await client.handle_packet({"cmd": "RoomUpdate", "checked_locations": [100]})
        self.assertFalse(client.pending_checks)


if __name__ == "__main__":
    unittest.main()
