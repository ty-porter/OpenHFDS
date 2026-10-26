import argparse
from OpenHFDS.hf_session import (
    DEFAULT_TTL,
    DEFAULT_MAX_ENTRIES,
    CLIENT_HEARTBEAT_SECONDS,
)

DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 10666
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def _int_in_range(name: str, low: int, high: int | None = None):
    def parse(text: str) -> int:
        try:
            value = int(text, 0)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{text!r} is not a whole number")

        if value < low or (high is not None and value > high):
            bounds = f"at least {low}" if high is None else f"between {low} and {high}"
            raise argparse.ArgumentTypeError(f"{name} must be {bounds}, got {value}")

        return value

    return parse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="openhfds",
        description="HellFighter directory server: lists hosted game sessions for the game's server browser.",
    )
    parser.add_argument(
        "--bind",
        default=DEFAULT_BIND,
        metavar="ADDRESS",
        help="address to listen on; use 0.0.0.0 to accept other machines (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=_int_in_range("port", 1, 65535),
        default=DEFAULT_PORT,
        help="UDP port to listen on; the game itself always uses %(default)s (default: %(default)s)",
    )
    parser.add_argument(
        "--ttl",
        type=_int_in_range("ttl", 1),
        default=DEFAULT_TTL,
        metavar="SECONDS",
        help=f"drop a host after this long without a 'set'; by default the game sends one every {CLIENT_HEARTBEAT_SECONDS}s "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--max-entries",
        type=_int_in_range("max-entries", 1, DEFAULT_MAX_ENTRIES),
        default=DEFAULT_MAX_ENTRIES,
        metavar="COUNT",
        help=f"most sessions to list; the game can't hold more than {DEFAULT_MAX_ENTRIES} (default: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=LOG_LEVELS,
        default="INFO",
        help="logging verbosity; INFO includes every packet received and sent (default: %(default)s)",
    )

    return parser.parse_args(argv)
