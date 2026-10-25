import logging

log_level = logging.INFO

# Create a Logger
Logger = logging.getLogger("OpenHFDS")
Logger.setLevel(log_level)

# Create console handler and set the log level
ch = logging.StreamHandler()
ch.setLevel(log_level)

# Create formatter
formatter = logging.Formatter(
    "[%(asctime)s] [%(name)s] [%(levelname)s]: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# Add formatter to console handler
ch.setFormatter(formatter)

# Add console handler to Logger
Logger.addHandler(ch)


def set_log_level(level: int | str) -> None:
    Logger.setLevel(level)
    ch.setLevel(level)


def log_received_udp_data(data: bytes, addr: tuple[str, int]):
    _log_udp_xfer("Receive", data, addr)


def log_sent_udp_data(data: bytes, addr: tuple[str, int]):
    _log_udp_xfer("Sent", data, addr)


def _log_udp_xfer(label: str, data: bytes, addr: tuple[str, int]) -> None:
    Logger.info(f"{label}: <{addr[0]}:{addr[1]} {len(data)} {repr(data)}>")
