# tokenslim-mcp

MCP server exposing the [`tokenslim`](https://github.com/robertruben98/tokenslim)
context-compression engine to any MCP host (Claude Code, Cursor, …). Stdio
transport, built on the official Python `mcp` SDK (`FastMCP`).

## Tools

| Tool | Args | Returns |
| --- | --- | --- |
| `tokenslim_compress` | `content: str`, `content_type?: str` | Compressed text, CCR `hash`, `changed`, and `stats` (`orig_tokens` / `new_tokens` / `saved_tokens` / `ratio`). |
| `tokenslim_retrieve` | `hash: str` | `{ found, hash, content }` — the original blob, or `found: false` if the hash is unknown. Resolved through the core CCR store (persistent across processes when SQLite-backed). |
| `tokenslim_stats` | — | Cumulative session savings: `compressions`, `orig_tokens`, `new_tokens`, `saved_tokens`, `ratio`. |

`content_type` is an advisory hint echoed back; the core auto-detects the real
type (JSON / log / code / diff / search / markdown / text) and picks a compressor.

## Install & register

```bash
pip install -e .   # pulls the tokenslim core via git
```

One command registers the server into every detected agent (Claude Code,
Cursor, Codex), merging into existing config without touching other keys:

```bash
tokenslim-mcp install            # all detected agents
tokenslim-mcp install --agent cursor   # one agent (repeatable)
tokenslim-mcp install --all      # force-write all, even if not detected
tokenslim-mcp install --list     # show target config paths + detection
```

| Agent | Config | Shape |
| --- | --- | --- |
| Claude Code | `~/.claude.json` | top-level `mcpServers.tokenslim` |
| Cursor | `~/.cursor/mcp.json` | `mcpServers.tokenslim` |
| Codex | `~/.codex/config.toml` | `[mcp_servers.tokenslim]` table |

The entry is the standard stdio shape, pointed at the interpreter the server
was installed into:

```json
{ "mcpServers": { "tokenslim": { "command": "/path/to/python", "args": ["-m", "tokenslim_mcp"] } } }
```

Or run the server directly: `tokenslim-mcp` / `python -m tokenslim_mcp`.

## How it works

Each `tokenslim_compress` call wraps the blob as a one-message array, runs it
through the core `compress()` (with `min_bytes=0` so single blobs always get
compressed), and returns the rewritten text plus token stats. The original is
put into the core **CCR store** under its `tokenslim.ccr.content_hash`, and
`tokenslim_retrieve` resolves the hash back through `tokenslim.retrieve.retrieve`
— so retrieval is reversible. `tokenslim_stats` reports the running total.

### Retrieval store (CCR)

By default the store is in-memory (process-local). Set `TOKENSLIM_MCP_CCR_PATH`
to a SQLite file to make retrieval **persistent and cross-process** — a hash
produced by one server process round-trips in another:

| Env var | Effect |
| --- | --- |
| `TOKENSLIM_MCP_CCR_PATH` | SQLite path → persistent, cross-process store |
| `TOKENSLIM_MCP_CCR_TTL` | record TTL in seconds (default: keep forever) |
| `TOKENSLIM_MCP_CCR=0` | disable CCR → fall back to a process-local dict |

## Development

```bash
pip install -e ".[dev]"
ruff check .
python -m pytest -q
```

Tests call the tool handlers directly and exercise the FastMCP dispatch — no
live MCP host or API keys required.

## Known gaps

- **Cross-process retrieval needs SQLite.** Persistence is only on when
  `TOKENSLIM_MCP_CCR_PATH` points at a SQLite file; the default in-memory store
  is process-local, so a hash from another process reports `found: false` until
  a path is configured.
- The core builds its own CCR store from config (no store-injection hook), so
  the engine steers it via `Config(ccr_backend/ccr_path)` to share the SQLite
  file; with the in-memory backend the compressor's internal elision markers and
  the engine's full-blob records live in separate stores (the engine's explicit
  `put` of the full blob remains the source of truth for `tokenslim_retrieve`).
- Compression depth is whatever the core provides; this server adds no
  algorithms of its own.

## License

Apache-2.0
