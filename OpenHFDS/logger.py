import logging

formatter = logging.Formatter(
    "[%(asctime)s] [%(name)s] [%(levelname)s]: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# Importing OpenHFDS must not change the host program's logging, so only the server's main() adds a console handler
Logger = logging.getLogger("OpenHFDS")
Logger.addHandler(logging.NullHandler())

_console: logging.Handler | None = None


def configure_logging(level: int | str) -> None:
    """Sends the logger's output to the console at the given level."""
    global _console

    if _console is None:
        _console = logging.StreamHandler()
        _console.setFormatter(formatter)
        Logger.addHandler(_console)

    Logger.setLevel(level)
    _console.setLevel(level)


def log_received_udp_data(data: bytes, addr: tuple[str, int]):
    _log_udp_xfer("Receive", data, addr)


def log_sent_udp_data(data: bytes, addr: tuple[str, int]):
    _log_udp_xfer("Sent", data, addr)


def _log_udp_xfer(label: str, data: bytes, addr: tuple[str, int]) -> None:
    Logger.info(f"{label}: <{addr[0]}:{addr[1]} {len(data)} {repr(data)}>")
