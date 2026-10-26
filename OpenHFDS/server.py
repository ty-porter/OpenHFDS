import socket
from datetime import datetime
from OpenHFDS.logger import Logger, configure_logging
from OpenHFDS.hf_client_request import decode_hf_udp, HFUnknownClientRequest
from OpenHFDS.hf_session import HFSessionList, CLIENT_HEARTBEAT_SECONDS
from OpenHFDS.cli import parse_args
from OpenHFDS.version import __version__


def serve(sock: socket.socket, sessions: HFSessionList) -> None:
    while True:
        try:
            for session in sessions.expire():
                Logger.info(
                    f"Expire: session <{session.hostname}> last seen at {datetime.fromtimestamp(session.last_seen).isoformat()}"
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
    configure_logging(args.log_level)

    Logger.info(f"OpenHFDS v{__version__} -- Open HellFighter Directory Server")

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
