from OpenHFDS.logger import log_received_udp_data, log_sent_udp_data, Logger
from OpenHFDS.hf_session import HFSessionList, HFSession
from collections.abc import Callable
import socket

HF_REQUEST_FIELD_SEPARATOR = " "
HF_CLIENT_FIELD_MAX = (
    63  # client reads each %s into a 64-byte buffer with no bounds check
)


class HFUnknownClientRequest(RuntimeError):
    """The datagram isn't an OpenHFDS request at all (stray traffic, scanners), so it isn't worth a traceback."""


HFRequestHandler = Callable[[str, HFSessionList, socket.socket, tuple[str, int]], None]


def decode_hf_udp(data: bytes, addr: tuple[str, int]) -> tuple[str, HFRequestHandler]:
    log_received_udp_data(data, addr)

    try:
        request = data.decode("ascii")
    except UnicodeDecodeError:
        raise HFUnknownClientRequest(f"Unable to decode {data!r} as ASCII")

    if request.startswith("info"):
        return (request, handle_info)
    elif request.startswith("get"):
        return (request, handle_get)
    elif request.startswith("set"):
        return (request, handle_set)
    elif request.startswith("delete me"):
        return (request, handle_delete)
    else:
        raise HFUnknownClientRequest(f"Unable to handle '{request}'")


def handle_info(
    _request: str, sessions: HFSessionList, sock: socket.socket, addr: tuple[str, int]
) -> None:
    """Handles <info> requests. Sends the session count to the client."""
    _send(sock, f"info {sessions.count} 0 0 0 0".encode("ascii"), addr)


def handle_get(
    request: str, sessions: HFSessionList, sock: socket.socket, addr: tuple[str, int]
) -> None:
    """Handles <get STARTID STOPID> requests. Sends all available sessions in the range, one datagram each."""
    args = request.split(HF_REQUEST_FIELD_SEPARATOR)
    start = int(args[1])
    stop = (int(args[2]) if len(args) > 2 else start) + 1

    # IDs are always 0..count-1, so don't loop over absurd ranges from a bad or hostile request
    start = max(start, 0)
    stop = min(stop, sessions.count)

    for ID in range(start, stop):
        session = sessions.get_by_id(ID)

        if session is not None:
            field_values = [
                str(getattr(session, f.name)) for f in HFSession.visible_fields(session)
            ]
            # The ID is the session's position in the list, so it's written here and not stored on the session
            _send(sock, f"get {ID} {' '.join(field_values)}".encode("ascii"), addr)


def handle_set(
    request: str, sessions: HFSessionList, _sock: socket.socket, addr: tuple[str, int]
) -> None:
    """
    Handles <set NAME LOCATION CONNECTION CURPLAYERS MAXPLAYERS FLAGS VERSION> requests.

    If the session does not exist, it creates it. Otherwise, the existing entry is updated with the new values.
    Either way the `last_seen` attribute of the session is ticked, so this request also functions as a heartbeat.
    Clients should send it faster than the list's TTL setting, otherwise the session is automatically removed.
    """
    name, location, connection, current, maximum, flags, version = request.split(
        HF_REQUEST_FIELD_SEPARATOR
    )[1:]

    # Parse everything before touching the session, so a bad value can't leave an entry half-updated
    values = {
        "name": name[:HF_CLIENT_FIELD_MAX],
        "location": location[:HF_CLIENT_FIELD_MAX],
        "connection": connection[:HF_CLIENT_FIELD_MAX],
        "current_players": int(current),
        "max_players": int(maximum),
        "flags": int(flags),
        "version": version[:HF_CLIENT_FIELD_MAX],
    }

    session = sessions.get_by_hostname(addr[0])
    existing = session is not None
    session = session or HFSession(hostname=addr[0])

    for attr, value in values.items():
        setattr(session, attr, value)
    session.heartbeat()

    if not existing:
        sessions.add(session)


def handle_delete(
    _request: str, sessions: HFSessionList, _sock: socket.socket, addr: tuple[str, int]
) -> None:
    """Handles <delete me> requests. Fetches by hostname and deletes the session from the list."""
    session = sessions.get_by_hostname(addr[0])
    if session is None:
        return

    sessions.remove(session)


def _send(sock: socket.socket, data: bytes, addr: tuple[str, int]) -> None:
    log_sent_udp_data(data, addr)
    sock.sendto(data, addr)
