import argparse
import socket
import sys
from datetime import datetime
from logger import Logger, set_log_level
from hf_client_request import decode_hf_udp, HFUnknownClientRequest
from hf_session import HFSessionList, DEFAULT_TTL, DEFAULT_MAX_ENTRIES

DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 10666
CLIENT_HEARTBEAT_SECONDS = 180  # how often the game re-sends "set" while hosting
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
        prog="openhfds.py",
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


def serve(sock: socket.socket, sessions: HFSessionList) -> None:
    while True:
        try:
            for session in sessions.expire():
                Logger.info(
                    f"Expire: session {session.ID} ({session.hostname}) last seen at {datetime.fromtimestamp(session.last_seen).isoformat()}"
                )
        except Exception as e:
            Logger.exception(e)

        try:
            d, addr = sock.recvfrom(65535)
        except (socket.timeout, ConnectionResetError):
            continue
        try:
            request, handler = decode_hf_udp(d, addr)
            handler(request, sessions, sock, addr)
        except HFUnknownClientRequest as e:
            Logger.warning(e)
        except Exception as e:
            Logger.exception(e)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    set_log_level(args.log_level)

    if args.ttl < CLIENT_HEARTBEAT_SECONDS:
        Logger.warning(
            f"TTL of {args.ttl} s is shorter than the game's {CLIENT_HEARTBEAT_SECONDS} s heartbeat, "
            "so hosts might drop off the list while still running"
        )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((args.bind, args.port))
    except OSError as e:
        Logger.error(f"Could not listen on {args.bind}:{args.port}: {e}")
        sock.close()
        return 1
    sock.settimeout(0.5)

    sessions = HFSessionList(ttl=args.ttl, max_entries=args.max_entries)
    Logger.info(
        f"Listening on {args.bind}:{args.port} (ttl {args.ttl}s, up to {args.max_entries} sessions)"
    )

    try:
        serve(sock, sessions)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
