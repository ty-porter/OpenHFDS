import random
import time
from dataclasses import dataclass, field, fields, Field
from OpenHFDS.logger import Logger

DEFAULT_TTL = 600  # seconds before a silent host is dropped; the client re-sends "set" every 180 s
DEFAULT_MAX_ENTRIES = 0x1000  # client's HFDS_MAX_ENTRIES
CLIENT_HEARTBEAT_SECONDS = 180  # how often the game re-sends "set" while hosting

# spoof() mixes these into names like "Leviathan_Outnumbered". No spaces, since the client sends and shows _ as a space.
# Ship names are picked from the game's NAMES.DAT, which it uses to name the ships in a battle.
SPOOF_SHIP_NAMES = [
    "Leviathan",
    "Nemesis",
    "Infernal",
    "Behemoth",
    "Cthulhu",
    "Titan",
    "Zeus",
    "Shiva",
    "Yamato",
    "Excalibur",
    "Armageddon",
    "Overlord",
    "Tyrant",
    "Pegasus",
    "Decimator",
    "Merciless",
    "Reaper",
    "Berserker",
    "Gargoyle",
    "Manticore",
    "Chimera",
    "Punisher",
    "Tormentor",
    "Vengeance",
    "Tiamat",
    "Sphinx",
]
# Battle names come from the game's .HFB battle files: ESCORT1-3, OUTNUM, SHRIKES, WYVERNS, TIMING, LESSON1-2, NET.
SPOOF_BATTLE_NAMES = [
    "Escort",
    "Outnumbered",
    "Shrikes",
    "Wyverns",
    "Timing",
    "Lesson",
    "Net",
]


@dataclass
class HFSession:
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
    """
    The sessions currently listed.

    A session's ID is its position in the list. The client asks for IDs 0..count-1 (count being the first "info" int)
    and uses the ID in each record as its table index, so IDs have to stay contiguous. Removing a session shifts the
    ones after it down, which keeps them that way.
    """

    def __init__(
        self,
        ttl: int = DEFAULT_TTL,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._sessions: list[HFSession] = []
        self._by_host: dict[str, HFSession] = {}

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

        # remove() mutates _by_host, so iterate over a copy
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
        self._sessions.append(session)

    def get_by_id(self, ID: int) -> HFSession | None:
        """Returns a session by ID, if it exists."""
        # a negative ID would otherwise index from the end of the list
        if 0 <= ID < len(self._sessions):
            return self._sessions[ID]

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
            self._sessions.remove(session)


    def spoof(self, n: int, seed: int | None = None) -> None:
        """
        Fills the list with up to n made-up sessions, for trying out the game's server browser without real hosts.

        The hostnames come from 10.200.0.0/16, which isn't going to be a real host, so joining one won't work.
        Spoofed sessions are never refreshed, so they expire after the TTL like any silent host.
        Pass a seed to get the same sessions every time.
        """
        rng = random.Random(seed)
        added = 0
        candidate = 0

        while added < n and self.count < self.max_entries:
            hostname = f"10.200.{candidate // 256}.{candidate % 256}"
            candidate += 1

            if hostname in self._by_host:
                continue

            max_players = rng.choice([8, 16, 24])
            self.add(
                HFSession(
                    hostname=hostname,
                    name=f"{rng.choice(SPOOF_SHIP_NAMES)}_{rng.choice(SPOOF_BATTLE_NAMES)}",
                    location=rng.choice(["Unknown", "North_America", "Europe", "Asia"]),
                    connection=rng.choice(["Unknown", "LAN", "Internet", "Modem"]),
                    current_players=rng.randint(0, max_players),
                    max_players=max_players,
                    flags=rng.choice([0, 0, 0, 1]),
                )
            )
            added += 1