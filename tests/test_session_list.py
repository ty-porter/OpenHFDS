import unittest

from OpenHFDS.hf_session import HFSession, HFSessionList


def session(host: str, **kwargs) -> HFSession:
    return HFSession(hostname=host, **kwargs)


class HFSessionTests(unittest.TestCase):
    def test_visible_fields_match_the_wire_record_order(self):
        # The client reads: get ID hostname name location connection cur max flags version
        # The ID is the session's position in the list, so handle_get writes it ahead of these.
        names = [f.name for f in HFSession.visible_fields(HFSession())]

        self.assertEqual(
            names,
            [
                "hostname",
                "name",
                "location",
                "connection",
                "current_players",
                "max_players",
                "flags",
                "version",
            ],
        )

    def test_heartbeat_refreshes_last_seen(self):
        s = HFSession()
        s.last_seen = 0

        s.heartbeat()

        self.assertGreater(s.last_seen, 0)


class HFSessionListTests(unittest.TestCase):
    def test_new_list_is_empty(self):
        sl = HFSessionList()

        self.assertEqual(sl.count, 0)
        self.assertIsNone(sl.get_by_id(0))

    def test_add_assigns_contiguous_ids_from_zero(self):
        sl = HFSessionList()
        for i in range(3):
            sl.add(session(f"10.0.0.{i}"))

        self.assertEqual(sl.count, 3)
        self.assertEqual(
            [sl.get_by_id(i).hostname for i in range(3)],
            ["10.0.0.0", "10.0.0.1", "10.0.0.2"],
        )

    def test_get_by_id_rejects_negative_and_out_of_range_ids(self):
        sl = HFSessionList()
        for i in range(3):
            sl.add(session(f"10.0.0.{i}"))

        for ID in (-1, -3, 3, 100):
            with self.subTest(ID=ID):
                self.assertIsNone(sl.get_by_id(ID))

    def test_add_of_a_known_host_is_ignored(self):
        sl = HFSessionList()
        first = session("10.0.0.1")
        sl.add(first)

        sl.add(session("10.0.0.1"))

        self.assertEqual(sl.count, 1)
        self.assertIs(sl.get_by_hostname("10.0.0.1"), first)

    def test_remove_renumbers_so_ids_stay_contiguous(self):
        # The client only ever asks for 0..count-1, so a gap would hide a session.
        sl = HFSessionList()
        for i in range(3):
            sl.add(session(f"10.0.0.{i}"))

        sl.remove(sl.get_by_hostname("10.0.0.1"))

        self.assertEqual(sl.count, 2)
        self.assertEqual(sl.get_by_id(0).hostname, "10.0.0.0")
        self.assertEqual(sl.get_by_id(1).hostname, "10.0.0.2")
        self.assertIsNone(sl.get_by_id(2))

    def test_remove_of_an_unknown_session_is_a_noop(self):
        sl = HFSessionList()
        sl.add(session("10.0.0.1"))

        sl.remove(session("10.9.9.9"))
        sl.remove(session("10.9.9.9"))

        self.assertEqual(sl.count, 1)

    def test_removing_twice_does_not_corrupt_count(self):
        sl = HFSessionList()
        s = session("10.0.0.1")
        sl.add(s)

        sl.remove(s)
        sl.remove(s)

        self.assertEqual(sl.count, 0)

    def test_spoof_adds_the_requested_number_of_unique_sessions(self):
        sl = HFSessionList()
        sl.add(session("10.200.0.0"))  # already taken, so spoof has to skip it

        sl.spoof(5, seed=1)

        self.assertEqual(sl.count, 6)
        self.assertEqual(len({sl.get_by_id(i).hostname for i in range(6)}), 6)

    def test_spoof_stops_at_max_entries(self):
        sl = HFSessionList(max_entries=3)

        sl.spoof(10)

        self.assertEqual(sl.count, 3)

    def test_spoofed_sessions_fit_the_clients_record_format(self):
        sl = HFSessionList()

        sl.spoof(50, seed=1)

        for i in range(50):
            s = sl.get_by_id(i)
            with self.subTest(i=i):
                self.assertLessEqual(s.current_players, s.max_players)
                for value in (s.hostname, s.name, s.location, s.connection, s.version):
                    self.assertRegex(value, r"^\S{1,63}$")

    def test_max_entries_is_enforced_and_logged(self):
        sl = HFSessionList(max_entries=2)
        sl.add(session("10.0.0.1"))
        sl.add(session("10.0.0.2"))

        with self.assertLogs("OpenHFDS", level="WARNING") as logs:
            sl.add(session("10.0.0.3"))

        self.assertEqual(sl.count, 2)
        self.assertIsNone(sl.get_by_hostname("10.0.0.3"))
        self.assertIn("10.0.0.3", logs.output[0])


class ExpireTests(unittest.TestCase):
    def test_expire_removes_only_stale_sessions(self):
        sl = HFSessionList(ttl=600)
        for i in range(3):
            sl.add(session(f"10.0.0.{i}"))
        sl.get_by_hostname("10.0.0.1").last_seen -= 1000

        removed = sl.expire()

        self.assertEqual([s.hostname for s in removed], ["10.0.0.1"])
        self.assertEqual(sl.count, 2)

    def test_expire_keeps_ids_contiguous(self):
        sl = HFSessionList(ttl=600)
        for i in range(3):
            sl.add(session(f"10.0.0.{i}"))
        sl.get_by_hostname("10.0.0.0").last_seen -= 1000

        sl.expire()

        self.assertEqual(sl.get_by_id(0).hostname, "10.0.0.1")
        self.assertEqual(sl.get_by_id(1).hostname, "10.0.0.2")
        self.assertIsNone(sl.get_by_id(2))

    def test_expire_can_remove_every_session_at_once(self):
        # Regression: removing mutates the list while expire() is walking it, which used to break iteration.
        sl = HFSessionList(ttl=0)
        for i in range(5):
            sl.add(session(f"10.0.0.{i}"))

        removed = sl.expire()

        self.assertEqual(len(removed), 5)
        self.assertEqual(sl.count, 0)

    def test_expire_with_nothing_stale_returns_empty(self):
        sl = HFSessionList(ttl=600)
        sl.add(session("10.0.0.1"))

        self.assertEqual(sl.expire(), [])
        self.assertEqual(sl.count, 1)

    def test_a_fresh_heartbeat_keeps_a_session_alive(self):
        sl = HFSessionList(ttl=600)
        s = session("10.0.0.1")
        sl.add(s)
        s.last_seen -= 1000

        s.heartbeat()

        self.assertEqual(sl.expire(), [])


if __name__ == "__main__":
    unittest.main()
