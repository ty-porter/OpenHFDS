import time
from dataclasses import dataclass, field, fields, Field
from OpenHFDS.logger import Logger

DEFAULT_TTL = 600  # seconds before a silent host is dropped; the client re-sends "set" every 180 s
DEFAULT_MAX_ENTRIES = 0x1000  # client's HFDS_MAX_ENTRIES
CLIENT_HEARTBEAT_SECONDS = 180  # how often the game re-sends "set" while hosting


@dataclass
class HFSession:
    ID: int = -1  # the session list controls this ID via _renumber()
    hostname: str = "hfds.dracova.com"
    name: str = "Hell_Fighter_Server"
    location: str = "Unknown"
    connection: str = "Unknown"
    current_players: int = 0
    max_players: int = 24
    flags: int = 0
    version: str = "v21.01"

    last_seen: float = field(
        default_factory=time.time, metadata={"hf_request_exclude": True}
    )

    def heartbeat(self) -> None:
        self.last_seen = time.time()

    @staticmethod
    def visible_fields(session: "HFSession") -> list[Field]:
        return [f for f in fields(session) if not f.metadata.get("hf_request_exclude")]


class HFSessionList:
    def __init__(
        self,
        existing_by_id: dict[int, HFSession] | None = None,
        existing_by_host: dict[str, HFSession] | None = None,
        ttl: int = DEFAULT_TTL,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._by_id = {} if existing_by_id is None else existing_by_id
        self._by_host = {} if existing_by_host is None else existing_by_host

        self.ttl = ttl
        self.max_entries = max_entries

    @property
    def count(self) -> int:
        """The number of sessions in the list."""
        return len(self._by_host)

    def expire(self) -> list[HFSession]:
        """Removes sessions whose heartbeat has not been received since the configured TTL."""
        now = time.time()

        removed = []

        # remove() renumbers _by_id, so iterate over a copy
        for session in list(self._by_host.values()):
            if now - session.last_seen < self.ttl:
                continue

            self.remove(session)
            removed.append(session)

        return removed

    def add(self, session: HFSession) -> None:
        """Adds a session to the list."""
        if session.hostname in self._by_host:
            # Session already exists, so carry on
            return

        if self.count >= self.max_entries:
            Logger.warning(
                f"Full: not adding {session.hostname}, list already has {self.count} sessions"
            )
            return

        self._by_host[session.hostname] = session
        self._renumber()

    def get_by_id(self, ID: int) -> HFSession | None:
        """Returns a session by ID, if it exists."""
        if ID in self._by_id:
            return self._by_id[ID]

        return None

    def get_by_hostname(self, hostname: str) -> HFSession | None:
        """Returns a session by hostname, if it exists."""
        if hostname in self._by_host:
            return self._by_host[hostname]

        return None

    def remove(self, session: HFSession) -> None:
        """Removes a session from the list."""
        if session.hostname in self._by_host:
            del self._by_host[session.hostname]
            self._renumber()

    def _renumber(self):
        """
        Renumbers the session IDs to ensure they remain contiguous.

        The client asks for IDs 0..count-1 where count is the first "info" int, and uses the ID in each record as its table index.
        """
        self._by_id.clear()

        for i, session in enumerate(self._by_host.values()):
            session.ID = i
            self._by_id[session.ID] = session
