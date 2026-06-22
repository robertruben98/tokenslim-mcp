# tokenslim-mcp

MCP server exposing the [`tokenslim`](https://github.com/robertruben98/tokenslim)
context-compression engine to any MCP host (Claude Code, Cursor, …). Stdio
transport, built on the official Python `mcp` SDK (`FastMCP`).

## Tools

| Tool | Args | Returns |
| --- | --- | --- |
| `tokenslim_compress` | `content: str`, `content_type?: str` | Compressed text, CCR `hash`, `changed`, and `stats` (`orig_tokens` / `new_tokens` / `saved_tokens` / `ratio`). |
| `tokenslim_retrieve` | `hash: str` | `{ found, hash, content }` — the original blob, or `found: false` if unknown to this session. |
| `tokenslim_stats` | — | Cumulative session savings: `compressions`, `orig_tokens`, `new_tokens`, `saved_tokens`, `ratio`. |

`content_type` is an advisory hint echoed back; the core auto-detects the real
type (JSON / log / code / diff / search / markdown / text) and picks a compressor.

## Install & register

```bash
pip install -e .   # pulls the tokenslim core via git
```

Register as a stdio MCP server. Example (Claude Code `mcpServers`):

```json
{
  "mcpServers": {
    "tokenslim": { "command": "tokenslim-mcp" }
  }
}
```

or run directly: `tokenslim-mcp` / `python -m tokenslim_mcp`.

## How it works

Each `tokenslim_compress` call wraps the blob as a one-message array, runs it
through the core `compress()` (with `min_bytes=0` so single blobs always get
compressed), and returns the rewritten text plus token stats. The original is
stored under its `tokenslim.ccr.content_hash` so `tokenslim_retrieve` can return
it verbatim. `tokenslim_stats` reports the running total.

## Development

```bash
pip install -e ".[dev]"
ruff check .
python -m pytest -q
```

Tests call the tool handlers directly and exercise the FastMCP dispatch — no
live MCP host or API keys required.

## Known gaps

- **Retrieval store is in-process.** The core ships CCR markers + `content_hash`
  but not yet a `retrieve()` / persistent store on `main`, so retrieval is
  backed by a per-session dict populated by `tokenslim_compress`. Hashes already
  use the core's `content_hash`, so this will switch to the core CCR store once
  merged (`TODO(core-ccr)` in `engine.py`). A hash from a previous process (or
  another server instance) will report `found: false`.
- Compression depth is whatever the core provides; this server adds no
  algorithms of its own.

## License

Apache-2.0
