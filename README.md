# OpenHFDS

[![pypi Badge](https://img.shields.io/pypi/v/OpenHFDS)](https://pypi.org/project/OpenHFDS/)

OpenHFDS is an open-source session directory server for HellFighter v21.0+ clients. HellFighter uses DirectPlay peering for the actual game code, but the v21.0 client is hard-coded to search for peer sessions at `hfds.dracova.com` which is now no longer serving traffic, so the only way to play online is via direct IP connections.

OpenHFDS implements the custom UDP protocol needed to search for HellFighter sessions to enable easy network play.

## Installation

OpenHFDS is dependency-free and only requires Python 3.11 or newer. Installation is as simple as obtaining the source code for this repo and running `python openhfds.py`.

If you'd prefer, you can also grab the latest version from PyPi:

```sh
pip install OpenHFDS
```

## Usage

Most people should use the default options provided by OpenHFDS. Unpatched HellFighter clients connect to the HFDS on UDP port 10666.

```sh
python openhfds.py
```

If you installed the package (for example with `pip install`), the same server is available as the `openhfds` command or `python -m OpenHFDS`.

### Connecting the game to your server

The game looks for the directory server at the hostname `hfds.dracova.com`, so every player (hosts and joiners) has to make that name point at the machine running OpenHFDS. The simplest way is a `hosts` file entry on each player's computer:

```
<address of the OpenHFDS machine> hfds.dracova.com
```

The hosts file is `C:\Windows\System32\drivers\etc\hosts` on Windows (edit it as an administrator) and `/etc/hosts` on Linux and macOS.

Which address to use depends on where the server runs:

- **Same computer as the game:** use `127.0.0.1`. The default `--bind 127.0.0.1` is enough.
- **Other players on your network or the internet:** start the server with `--bind 0.0.0.0` and use that machine's LAN or public IP. UDP port 10666 must be reachable, so allow it through the firewall and forward it if you're behind a router.

OpenHFDS only lists sessions. Once a player picks one, the game connects to the host directly using DirectPlay, so the host's game must also be reachable by the joiner.

Players only appear in the list once their game has registered, and a host's listed player count can lag by a few minutes because the game only refreshes it periodically.

### All CLI Flags

```
usage: openhfds [-h] [--bind ADDRESS] [--port PORT] [--ttl SECONDS] [--max-entries COUNT] [--log-level {DEBUG,INFO,WARNING,ERROR}]

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

## Known Issues

- **`get` requests can be used for amplification.** A `get` request is a few bytes, but the server answers it with one datagram for every session in the requested range, and there is no rate limiting. UDP source addresses can be forged, so a public server could be used to send traffic at a third party. The impact grows with the number of registered sessions. Keep the default `--bind 127.0.0.1`, or only expose the server to people you trust (for example, a firewall that allows your friends' addresses).
- **Requests are not authenticated.** The HellFighter protocol has no authentication, and OpenHFDS identifies a host by the IP address its packets come from. Anyone who can send UDP to the server can list, add, change, or delete sessions, including by forging another host's address.
- **Hosts behind the same public IP address collide.** Because a host is identified by IP address, two people hosting from behind the same router share one entry in the list, and the most recent `set` wins.
- **The listed player count can be out of date.** The game only re-registers its session every 3 minutes (and when it starts), not when players join or leave.

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