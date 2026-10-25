# OpenHFDS

OpenHFDS is an open-source session directory server for HellFighter v21.0+ clients. HellFighter uses DirectPlay peering for the actual game code, but the v21.0 client is hard-coded to search for peer sessions at `hfds.dracova.com` which is now no longer serving traffic, so the only way to play online is via direct IP connections.

OpenHFDS implements the custom UDP protocol needed to search for HellFighter sessions to enable easy network play.

## Installation

OpenHFDS is dependency-free and only requires a recent Python to function. Installation is as simple as obtaining source code for this repo.

## Usage

Most people should use the default options provided by OpenHFDS. Unpatched HellFighter clients connect to the HFDS on UDP port 10666.

```sh
python openhfds.py
```

### All CLI Flags

```
usage: openhfds.py [-h] [--bind ADDRESS] [--port PORT] [--ttl SECONDS] [--max-entries COUNT] [--log-level {DEBUG,INFO,WARNING,ERROR}]

HellFighter directory server: lists hosted game sessions for the game's server browser.

options:
  -h, --help            show this help message and exit
  --bind ADDRESS        address to listen on; use 0.0.0.0 to accept other machines (default: 127.0.0.1)
  --port PORT           UDP port to listen on; the game itself always uses 10666 (default: 10666)
  --ttl SECONDS         drop a host after this long without a 'set'; by default the game sends one every 180s (default: 600)
  --max-entries COUNT   most sessions to list; the game can't hold more than 4096 (default: 4096)
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        logging verbosity; INFO includes every packet received and sent (default: INFO)
```

## HFDS Protocol

Please see [docs/protocol.md](docs/protocol.md) for details about how the directory server protocol works.

## Contributing

### Installing Locally

OpenHFDS uses `uv` to manage dependencies.

```sh
uv sync --group dev
```

#### Running Tests

```sh
uv run python -m unittest
```

#### Lint

```sh
uv run black .
```

#### Typechecking

```sh
uv run mypy .
```

## Contact

Ty Porter

tyler.b.porter@gmail.com