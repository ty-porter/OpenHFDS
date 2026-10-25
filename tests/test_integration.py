"""
End-to-end tests: run openhfds.py as a real process and talk to it over UDP.

Each test picks a free port and passes it with --port, so a dev server on 10666 doesn't interfere.
"""

import os
import socket
import subprocess
import sys
import time
import unittest

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
    finally:
        probe.close()


class ServerProcessTestCase(unittest.TestCase):
    server_args: list[str] = []

    def setUp(self):
        self.addr = ("127.0.0.1", free_port())
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "openhfds.py",
                "--port",
                str(self.addr[1]),
                *self.server_args,
            ],
            cwd=TOOLS_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.addCleanup(self.stop_server)

        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.settimeout(2)
        self.addCleanup(self.client.close)

        self.wait_until_ready()

    def stop_server(self):
        if self.proc.poll() is None:
            self.proc.terminate()
        self.output = self.proc.communicate(timeout=10)[0]

    def wait_until_ready(self):
        deadline = time.time() + 5
        while time.time() < deadline:
            self.client.sendto(b"info", self.addr)
            try:
                self.client.recvfrom(100)
                return
            except ConnectionResetError:
                # Windows reports the closed port from before the server bound it; try again shortly.
                time.sleep(0.1)
            except socket.timeout:
                pass
        self.fail("server never answered")

    def send(self, data: bytes) -> None:
        self.client.sendto(data, self.addr)

    def ask(self, data: bytes, replies: int = 1) -> list[bytes]:
        self.send(data)
        return [self.client.recvfrom(1000)[0] for _ in range(replies)]


class ServerProcessTests(ServerProcessTestCase):
    def test_register_list_and_remove(self):
        self.send(b"set Hell_Fighter_Server Unknown Unknown 1 24 0 v21.01")

        self.assertEqual(self.ask(b"info"), [b"info 1 0 0 0 0"])
        self.assertEqual(
            self.ask(b"get 0 0"),
            [b"get 0 127.0.0.1 Hell_Fighter_Server Unknown Unknown 1 24 0 v21.01"],
        )

        self.send(b"delete me")
        self.assertEqual(self.ask(b"info"), [b"info 0 0 0 0 0"])

    def test_survives_junk_and_malformed_requests(self):
        for packet in [
            b"junk",
            b"\xff\xfe\x00",
            b"",
            b"set bad",
            b"get x y",
            b"get 0 2000000000",
        ]:
            self.send(packet)

        self.assertEqual(self.ask(b"info"), [b"info 0 0 0 0 0"])
        self.assertIsNone(self.proc.poll(), "server exited")

    def test_survives_a_client_that_closed_before_the_reply(self):
        # Windows raises ConnectionResetError from recvfrom after sending to a closed UDP port.
        self.send(b"set A Unknown Unknown 1 24 0 v21.01")
        self.assertEqual(self.ask(b"info"), [b"info 1 0 0 0 0"])

        gone = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        gone.sendto(b"get 0 0", self.addr)
        gone.close()
        time.sleep(0.3)

        self.assertEqual(self.ask(b"info"), [b"info 1 0 0 0 0"])
        self.assertIsNone(self.proc.poll(), "server exited")

    def test_junk_is_logged_as_a_warning_not_a_traceback(self):
        self.send(b"junk")
        self.ask(b"info")

        self.stop_server()

        self.assertIn("Unable to handle 'junk'", self.output)
        self.assertNotIn("Traceback", self.output)

    def test_announces_its_settings_at_startup(self):
        self.stop_server()

        self.assertIn(
            f"Listening on 127.0.0.1:{self.addr[1]} (ttl 600s, up to 4096 sessions)",
            self.output,
        )


class MaxEntriesOptionTests(ServerProcessTestCase):
    server_args = ["--max-entries", "1"]

    def test_second_host_is_refused(self):
        self.send(b"set First Unknown Unknown 1 24 0 v21.01")
        self.assertEqual(self.ask(b"info"), [b"info 1 0 0 0 0"])

        other = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(other.close)
        other.bind(("127.0.0.2", 0))  # a different source IP, so a different host
        other.sendto(b"set Second Unknown Unknown 1 24 0 v21.01", self.addr)

        self.assertEqual(self.ask(b"info"), [b"info 1 0 0 0 0"])
        self.assertEqual(len(self.ask(b"get 0 5")[0].split(b" ")), 10)


class TtlOptionTests(ServerProcessTestCase):
    server_args = ["--ttl", "1"]

    def test_silent_host_expires(self):
        self.send(b"set Shortlived Unknown Unknown 1 24 0 v21.01")
        self.assertEqual(self.ask(b"info"), [b"info 1 0 0 0 0"])

        deadline = time.time() + 6
        while time.time() < deadline:
            time.sleep(0.5)
            if self.ask(b"info") == [b"info 0 0 0 0 0"]:
                break
        else:
            self.fail("host never expired")

        self.stop_server()
        self.assertIn("Expire: session 0 (127.0.0.1)", self.output)

    def test_warns_that_the_ttl_is_shorter_than_the_clients_heartbeat(self):
        self.stop_server()

        self.assertIn("shorter than the game's 180 s heartbeat", self.output)


class LogLevelOptionTests(ServerProcessTestCase):
    server_args = ["--log-level", "warning"]

    def test_packets_are_not_logged_below_the_chosen_level(self):
        self.ask(b"info")

        self.stop_server()

        self.assertNotIn("Receive: <", self.output)
        self.assertNotIn("Listening", self.output)


class StartupFailureTests(unittest.TestCase):
    def run_hfds(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "openhfds.py", *args],
            cwd=TOOLS_DIR,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_port_already_in_use_exits_with_a_clear_error(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(holder.close)
        holder.bind(("127.0.0.1", 0))
        port = holder.getsockname()[1]

        result = self.run_hfds("--port", str(port))

        self.assertEqual(result.returncode, 1)
        self.assertIn(f"Could not listen on 127.0.0.1:{port}", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_bad_option_exits_with_usage_error(self):
        result = self.run_hfds("--port", "99999")

        self.assertEqual(result.returncode, 2)
        self.assertIn("--port", result.stderr)

    def test_help_lists_every_option(self):
        result = self.run_hfds("--help")

        self.assertEqual(result.returncode, 0)
        for option in ["--bind", "--port", "--ttl", "--max-entries", "--log-level"]:
            self.assertIn(option, result.stdout)


if __name__ == "__main__":
    unittest.main()
