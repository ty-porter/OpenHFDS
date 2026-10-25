import re
import unittest

from OpenHFDS.hf_client_request import (
    HF_CLIENT_FIELD_MAX,
    HFUnknownClientRequest,
    decode_hf_udp,
    handle_delete,
    handle_get,
    handle_info,
    handle_set,
)
from OpenHFDS.hf_session import HFSessionList

# The client parses these with sscanf; the patterns mirror its format strings:
#   "info %d %d %d %d %d" and "get %d %s %s %s %s %d %d %d %s"
INFO_REPLY = re.compile(rb"^info (-?\d+) (-?\d+) (-?\d+) (-?\d+) (-?\d+)$")
GET_RECORD = re.compile(
    rb"^get (-?\d+) (\S+) (\S+) (\S+) (\S+) (-?\d+) (-?\d+) (-?\d+) (\S+)$"
)

# A real packet captured from the game client.
REAL_SET = "set Hell_Fighter_Server Unknown Unknown 1 24 0 v21.01"
HOST = ("10.0.0.1", 55389)


class FakeSocket:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    @property
    def payloads(self):
        return [data for data, _ in self.sent]


class RequestTestCase(unittest.TestCase):
    def setUp(self):
        self.sessions = HFSessionList()
        self.sock = FakeSocket()

    def set_(self, request=REAL_SET, addr=HOST):
        handle_set(request, self.sessions, self.sock, addr)

    def get(self, request, addr=("10.9.9.9", 1)):
        self.sock.sent.clear()
        handle_get(request, self.sessions, self.sock, addr)
        return self.sock.payloads

    def register(self, count):
        for i in range(count):
            self.set_(
                f"set Server{i} Unknown Unknown {i} 24 0 v21.01",
                addr=(f"10.0.0.{i + 1}", 5000),
            )


class DecodeTests(RequestTestCase):
    def test_routes_each_command(self):
        for text, handler in [
            ("info", handle_info),
            ("get 0 0", handle_get),
            (REAL_SET, handle_set),
            ("delete me", handle_delete),
        ]:
            with self.subTest(text=text):
                request, found = decode_hf_udp(text.encode("ascii"), HOST)
                self.assertEqual(request, text)
                self.assertIs(found, handler)

    def test_unknown_requests_raise_the_dedicated_error(self):
        for data in [b"junk", b"", b"\xff\xfe\x00", b"delete"]:
            with self.subTest(data=data):
                with self.assertRaises(HFUnknownClientRequest):
                    decode_hf_udp(data, HOST)


class InfoTests(RequestTestCase):
    def test_reply_has_five_ints_with_the_session_count_first(self):
        self.register(3)
        self.sock.sent.clear()

        handle_info("info", self.sessions, self.sock, HOST)

        (payload,) = self.sock.payloads
        self.assertRegex(payload, INFO_REPLY)
        self.assertEqual(payload, b"info 3 0 0 0 0")

    def test_empty_list_reports_zero(self):
        handle_info("info", self.sessions, self.sock, HOST)

        self.assertEqual(self.sock.payloads, [b"info 0 0 0 0 0"])

    def test_reply_goes_back_to_the_requester(self):
        handle_info("info", self.sessions, self.sock, HOST)

        self.assertEqual(self.sock.sent[0][1], HOST)


class SetTests(RequestTestCase):
    def test_real_client_packet_creates_a_session(self):
        self.set_()

        s = self.sessions.get_by_hostname("10.0.0.1")
        self.assertEqual(self.sessions.count, 1)
        self.assertEqual(
            (
                s.ID,
                s.hostname,
                s.name,
                s.location,
                s.connection,
                s.current_players,
                s.max_players,
                s.flags,
                s.version,
            ),
            (
                0,
                "10.0.0.1",
                "Hell_Fighter_Server",
                "Unknown",
                "Unknown",
                1,
                24,
                0,
                "v21.01",
            ),
        )

    def test_hosts_are_keyed_by_ip_not_port(self):
        # The client's source port is ephemeral and changes between messages.
        self.set_(addr=("10.0.0.1", 1111))
        self.set_(addr=("10.0.0.1", 2222))

        self.assertEqual(self.sessions.count, 1)

    def test_set_sends_no_reply(self):
        self.set_()

        self.assertEqual(self.sock.sent, [])

    def test_repeat_set_updates_the_existing_entry(self):
        self.set_()

        self.set_("set Renamed Somewhere LAN 5 24 1 v21.01")

        s = self.sessions.get_by_hostname("10.0.0.1")
        self.assertEqual(self.sessions.count, 1)
        self.assertEqual(
            (s.name, s.location, s.connection, s.current_players, s.flags),
            ("Renamed", "Somewhere", "LAN", 5, 1),
        )

    def test_repeat_set_refreshes_the_heartbeat(self):
        self.set_()
        s = self.sessions.get_by_hostname("10.0.0.1")
        s.last_seen -= 1000
        stale = s.last_seen

        self.set_()

        self.assertGreater(s.last_seen, stale)

    def test_different_hosts_get_different_ids(self):
        self.register(3)

        self.assertEqual(
            [self.sessions.get_by_hostname(f"10.0.0.{i + 1}").ID for i in range(3)],
            [0, 1, 2],
        )

    def test_long_strings_are_truncated_to_fit_the_clients_buffers(self):
        long = "x" * 200

        self.set_(f"set {long} {long} {long} 1 24 0 {long}")

        s = self.sessions.get_by_hostname("10.0.0.1")
        for value in (s.name, s.location, s.connection, s.version):
            self.assertEqual(len(value), HF_CLIENT_FIELD_MAX)

    def test_bad_number_on_an_existing_host_changes_nothing(self):
        self.set_()
        s = self.sessions.get_by_hostname("10.0.0.1")
        before = dict(vars(s))

        with self.assertRaises(ValueError):
            self.set_("set Changed Moved Elsewhere 7 99 notanint v99")

        self.assertEqual(vars(s), before)

    def test_bad_number_from_a_new_host_adds_nothing(self):
        with self.assertRaises(ValueError):
            self.set_("set X Unknown Unknown abc 24 0 v1")

        self.assertEqual(self.sessions.count, 0)

    def test_wrong_field_count_is_rejected(self):
        for request in ["set", "set a b c", "set a b c 1 24 0 v1 extra"]:
            with self.subTest(request=request):
                with self.assertRaises(ValueError):
                    self.set_(request)
        self.assertEqual(self.sessions.count, 0)


class GetTests(RequestTestCase):
    def test_record_matches_the_real_capture_exactly(self):
        self.set_()

        (record,) = self.get("get 0 0")

        self.assertEqual(
            record, b"get 0 10.0.0.1 Hell_Fighter_Server Unknown Unknown 1 24 0 v21.01"
        )

    def test_record_matches_the_clients_scanf_format(self):
        self.register(2)

        for record in self.get("get 0 1"):
            with self.subTest(record=record):
                self.assertRegex(record, GET_RECORD)

    def test_record_does_not_leak_last_seen(self):
        self.set_()

        (record,) = self.get("get 0 0")

        self.assertEqual(len(record.split(b" ")), 10)

    def test_range_is_inclusive_and_sends_one_datagram_per_session(self):
        self.register(4)

        records = self.get("get 1 2")

        self.assertEqual([int(r.split(b" ")[1]) for r in records], [1, 2])

    def test_whole_list_in_one_request(self):
        self.register(3)

        self.assertEqual(len(self.get("get 0 2")), 3)

    def test_single_argument_asks_for_one_session(self):
        self.register(3)

        records = self.get("get 1")

        self.assertEqual([int(r.split(b" ")[1]) for r in records], [1])

    def test_replies_go_to_the_requester(self):
        self.register(1)
        self.sock.sent.clear()

        handle_get("get 0 0", self.sessions, self.sock, ("10.7.7.7", 4242))

        self.assertEqual([addr for _, addr in self.sock.sent], [("10.7.7.7", 4242)])

    def test_ids_past_the_end_return_nothing(self):
        self.register(2)

        self.assertEqual(self.get("get 5 9"), [])

    def test_oversized_and_negative_ranges_are_clamped(self):
        self.register(3)

        self.assertEqual(len(self.get("get 0 2000000000")), 3)
        self.assertEqual(len(self.get("get -2000000000 1")), 2)

    def test_malformed_get_raises(self):
        for request in ["get", "get x y"]:
            with self.subTest(request=request):
                with self.assertRaises((ValueError, IndexError)):
                    handle_get(request, self.sessions, self.sock, HOST)

    def test_ids_have_no_gaps_after_a_removal(self):
        # Regression: a gap meant the session with the highest ID was never requested.
        self.register(3)
        handle_delete("delete me", self.sessions, self.sock, ("10.0.0.2", 5000))

        records = self.get("get 0 1")

        self.assertEqual([int(r.split(b" ")[1]) for r in records], [0, 1])


class DeleteTests(RequestTestCase):
    def test_removes_the_sender(self):
        self.set_()

        handle_delete("delete me", self.sessions, self.sock, HOST)

        self.assertEqual(self.sessions.count, 0)

    def test_unknown_sender_is_ignored(self):
        self.set_()

        handle_delete("delete me", self.sessions, self.sock, ("10.9.9.9", 1))

        self.assertEqual(self.sessions.count, 1)

    def test_deleting_twice_is_harmless(self):
        self.set_()

        handle_delete("delete me", self.sessions, self.sock, HOST)
        handle_delete("delete me", self.sessions, self.sock, HOST)

        self.assertEqual(self.sessions.count, 0)

    def test_delete_sends_no_reply(self):
        self.set_()
        self.sock.sent.clear()

        handle_delete("delete me", self.sessions, self.sock, HOST)

        self.assertEqual(self.sock.sent, [])


class ClientFetchSimulationTests(RequestTestCase):
    """Replays what the game does: `info`, then `get 0 <count-1>`, and expects every table slot filled."""

    def fetch(self):
        self.sock.sent.clear()
        handle_info("info", self.sessions, self.sock, HOST)
        count = int(INFO_REPLY.match(self.sock.payloads[0]).group(1))
        if count == 0:
            return count, {}

        self.sock.sent.clear()
        handle_get(f"get 0 {count - 1}", self.sessions, self.sock, HOST)
        table = {}
        for record in self.sock.payloads:
            fields = GET_RECORD.match(record).groups()
            table[int(fields[0])] = fields
        return count, table

    def test_every_slot_is_filled(self):
        self.register(4)

        count, table = self.fetch()

        self.assertEqual(sorted(table), list(range(count)))

    def test_still_complete_after_hosts_come_and_go(self):
        self.register(5)
        handle_delete("delete me", self.sessions, self.sock, ("10.0.0.2", 5000))
        handle_delete("delete me", self.sessions, self.sock, ("10.0.0.4", 5000))
        self.set_("set Late Unknown Unknown 1 24 0 v21.01", addr=("10.0.0.9", 5000))

        count, table = self.fetch()

        self.assertEqual(count, 4)
        self.assertEqual(sorted(table), list(range(count)))

    def test_empty_directory(self):
        count, table = self.fetch()

        self.assertEqual((count, table), (0, {}))


if __name__ == "__main__":
    unittest.main()
