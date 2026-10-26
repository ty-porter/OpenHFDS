# HFDS Protocol

HellFighter's directory server (HFDS) is a tiny UDP service. It doesn't run any part of the game. Hosts tell it "I'm running a session," joiners ask it "who's running a session," and then the game clients connect to each other directly using DirectPlay.

There was never any public documentation for it. Everything here comes from decompiling `HellFighter.exe` (the v21.01 client) and then checking it against a real client talking to OpenHFDS. Where I'm only inferring something, I say so.

## The Basics

- The client sends everything to `hfds.dracova.com`, UDP port 10666. That host no longer exists, which is the whole reason this project exists.
- Messages are plain ASCII, space separated, and one message is one datagram.
- The client uses a single MFC `CAsyncSocket` bound to port 0. Its source port is ephemeral, so a server can't identify a host by `IP:port`. OpenHFDS identifies a host by IP address alone.
- The client parses replies with `sscanf`, and `%s` stops at whitespace. A name with a space in it would break the parse, so the client swaps spaces for underscores before sending, and swaps them back for display. This only happens for `name`, `location`, and `connection`.

## Messages

There are four. Two are requests that expect a reply (`info`, `get`) and two are fire-and-forget (`set`, `delete me`).

### `info`

The client asks how many sessions there are.

```
info
```

The server replies with the count, plus four more integers:

```
info <count> 0 0 0 0
```

- The client parses this with `sscanf("info %d %d %d %d %d")` and needs all five. Anything less logs `Couldn't parse info response`.
- Only `count` is ever used. The other four get stored and then never read. I have no idea what the original server used them for, so OpenHFDS sends zeros.
- If nothing answers within 3 seconds, the client gives up with `Directory server didn't respond to info command`.
- A count of 0 logs `No sessions in directory`. Anything over `0x1000` (4096, the client's `HFDS_MAX_ENTRIES`) is treated as an error.

### `get`

The client asks for a range of sessions by ID. The range is inclusive on both ends.

```
get <first> <last>
```

The server answers with one datagram per session, not one big list:

```
get <ID> <hostname> <name> <location> <connection> <cur> <max> <flags> <version>
```

For example:

```
get 0 203.0.113.7 Hell_Fighter_Server Unknown Unknown 1 24 0 v21.01
```

A few things worth knowing:

- The first request is always `get 0 <count-1>`.
- The client allows 10 seconds for all of this. Every 3 seconds of silence it re-requests only the IDs it's missing. Duplicate replies are normal and harmless.
- The ID is the client's index into its own table. The IDs **must** be contiguous, `0` to `count-1`. If there's a gap, the client never fills it. This is why OpenHFDS renumbers every session whenever one is added or removed.
- Each string is read into a 64-byte slot with no bounds check. Keep every field to 63 characters or less, or you overwrite whatever's next to it. OpenHFDS truncates on the way in to be nice.
- `hostname` is the host's IP address as the server saw it. It is not underscore-converted, but `name`, `location`, and `connection` are.

### `set`

A host registers (or refreshes) its session. There's no reply.

```
set <name> <location> <connection> <cur> <max> <flags> <version>
```

For example:

```
set Hell_Fighter_Server Unknown Unknown 1 24 0 v21.01
```

- The client builds it with `sprintf("set %s %d %d %d %s", ...)`, where the first `%s` is already `"<name> <location> <connection>"`. That's why those three fields look like one blob in the decompile.
- It doesn't send a hostname or ID. The server fills the hostname in from the sender's address and assigns the ID itself.
- `version` isn't sanitized, and it carries a leading `v` (`v21.01`).
- The client sends it when a public session starts (usually twice, in the same tick) and then every 180 seconds from a timer. That second part is the heartbeat, and it matters, because...

**Players joining or leaving does not send a `set`.** The listed `cur` only updates on the next 3 minute heartbeat. If the number in the browser looks stale, that's the client's fault, not the server's. The only thing a join or leave does is play a sound.

### `delete me`

A host leaving a public session.

```
delete me
```

There's no reply. The client sends it twice, which is harmless.

## What the Client Shows

The session list has columns for name, location, connection, `cur/max`, a flag marker, and version.

- `flags` bit 0 means the session is password protected, and the client appends a `P` to the listing.
- It's unclear what any of the other `flags` bits do.
- The list stops at the first entry with an empty name. Missing entries show up as `[N/A]`.

## What a Server Has to Do

Boiled down, a server for this client needs to:

- Hand out contiguous IDs starting at 0, and renumber them when sessions come and go.
- Key hosts by source IP.
- Keep a session alive for longer than 180 seconds between `set` messages. OpenHFDS defaults to 600 so one dropped packet doesn't make a host vanish.
- Truncate every string field to 63 characters.
- Answer `info` with exactly five integers.

OpenHFDS also does a few things the original probably didn't need to, like ignoring junk datagrams instead of crashing and clamping `get` ranges to the real session count so nobody can ask for four billion IDs.

## Open Questions

- **The four extra `info` integers.** They're unused by this client, and I don't know what they were meant for.
- **`flags` above bit 0.** No idea.
- **What the original server did for unknown IDs.** The client just retries, then gives up.
- **The intermittent `Couldn't parse info response` in `HellFighter.log`.** My theory is that the client never drains its socket and doesn't NUL-terminate its receive buffer, so a late duplicate `get` reply from an earlier refresh gets parsed as the `info` reply. I haven't tested it.

## Where This Lives in the Client

For anyone who wants to continue building, these are the addresses in `HellFighter.exe` (image base `0x400000`) as seen in Ghidra:

| Address | What it is |
| --- | --- |
| `0x42dbf0` | Lazily creates the global socket (`0x495ba0`) |
| `0x42dc90` | Sends `set` |
| `0x42de30` | Sends `delete me` |
| `0x42de90` | Fetches the directory (`info` then `get`). Ghidra doesn't define this as a function until you create it manually |
| `0x42e360` - `0x42e4a0` | Accessors for name, location, version, connection, hostname, `cur/max`, and the flag marker |
| `0x404420` | Timer callback that sends the `set` heartbeat |
| `0x402690` | Fills the session list UI |
| `0x48eb88` | Session count. The table of record pointers is at `0x48eb9c` |
