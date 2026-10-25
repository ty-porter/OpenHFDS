import contextlib
import io
import unittest

from hf_session import DEFAULT_MAX_ENTRIES, DEFAULT_TTL
from openhfds import DEFAULT_BIND, DEFAULT_PORT, parse_args


def rejected(*argv: str) -> str:
    """Parses argv, expecting argparse to exit with a usage error, and returns what it printed."""
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr), contextlib.suppress(SystemExit):
        try:
            parse_args(list(argv))
        except SystemExit as e:
            assert e.code == 2, f"expected exit code 2, got {e.code}"
            raise
        raise AssertionError(f"{argv} was accepted")
    return stderr.getvalue()


class DefaultsTests(unittest.TestCase):
    def test_no_arguments_gives_the_original_behavior(self):
        args = parse_args([])

        self.assertEqual(args.bind, "127.0.0.1")
        self.assertEqual(args.port, 10666)
        self.assertEqual(args.ttl, 600)
        self.assertEqual(args.max_entries, 0x1000)
        self.assertEqual(args.log_level, "INFO")

    def test_defaults_come_from_the_module_constants(self):
        args = parse_args([])

        self.assertEqual(
            (args.bind, args.port, args.ttl, args.max_entries),
            (DEFAULT_BIND, DEFAULT_PORT, DEFAULT_TTL, DEFAULT_MAX_ENTRIES),
        )


class OptionTests(unittest.TestCase):
    def test_every_option(self):
        args = parse_args(
            [
                "--bind",
                "0.0.0.0",
                "--port",
                "12345",
                "--ttl",
                "900",
                "--max-entries",
                "64",
                "--log-level",
                "warning",
            ]
        )

        self.assertEqual(args.bind, "0.0.0.0")
        self.assertEqual(args.port, 12345)
        self.assertEqual(args.ttl, 900)
        self.assertEqual(args.max_entries, 64)
        self.assertEqual(args.log_level, "WARNING")

    def test_log_level_is_case_insensitive(self):
        for text in ["debug", "Debug", "DEBUG"]:
            with self.subTest(text=text):
                self.assertEqual(parse_args(["--log-level", text]).log_level, "DEBUG")

    def test_numbers_may_be_written_in_hex(self):
        self.assertEqual(parse_args(["--max-entries", "0x100"]).max_entries, 256)

    def test_accepts_the_range_limits(self):
        self.assertEqual(parse_args(["--port", "1"]).port, 1)
        self.assertEqual(parse_args(["--port", "65535"]).port, 65535)
        self.assertEqual(parse_args(["--max-entries", "1"]).max_entries, 1)
        self.assertEqual(parse_args(["--max-entries", "4096"]).max_entries, 4096)
        self.assertEqual(parse_args(["--ttl", "1"]).ttl, 1)


class RejectionTests(unittest.TestCase):
    def test_bad_ports(self):
        for value in ["0", "65536", "-1", "abc", "1.5", ""]:
            with self.subTest(value=value):
                self.assertIn("--port", rejected("--port", value))

    def test_bad_ttls(self):
        for value in ["0", "-5", "abc"]:
            with self.subTest(value=value):
                self.assertIn("--ttl", rejected("--ttl", value))

    def test_max_entries_cannot_exceed_what_the_client_can_hold(self):
        # The game treats a count above 0x1000 as an error.
        for value in ["0", "-1", "4097", "100000", "abc"]:
            with self.subTest(value=value):
                self.assertIn("--max-entries", rejected("--max-entries", value))

    def test_unknown_log_level(self):
        self.assertIn("--log-level", rejected("--log-level", "chatty"))

    def test_unknown_option(self):
        self.assertIn("--nope", rejected("--nope"))

    def test_missing_value(self):
        self.assertIn("--port", rejected("--port"))


if __name__ == "__main__":
    unittest.main()
