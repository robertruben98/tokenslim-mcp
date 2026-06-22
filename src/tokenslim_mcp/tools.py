"""Pure tool implementations, decoupled from the MCP transport.

Each function takes an :class:`Engine` and returns a plain JSON-serializable
dict. The MCP server (``server.py``) binds these to ``@mcp.tool`` handlers, and
tests call them directly — no live MCP host required.
"""

from __future__ import annotations

from typing import Any

from .engine import Engine


def compress_tool(engine: Engine, content: str, content_type: str | None = None) -> dict[str, Any]:
    """Compress a content blob and register it for retrieval.

    Returns the compressed text, token stats, and the CCR content hash that
    :func:`retrieve_tool` can later resolve back to the original.
    """
    if not isinstance(content, str):
        raise ValueError("`content` must be a string.")

    result = engine.compress(content, content_type=content_type)
    return {
        "content": result.content,
        "hash": result.hash,
        "changed": result.changed,
        "content_type": result.content_type,
        "stats": {
            "orig_tokens": result.orig_tokens,
            "new_tokens": result.new_tokens,
            "saved_tokens": result.orig_tokens - result.new_tokens,
            "ratio": round(result.ratio, 6),
        },
    }


def retrieve_tool(engine: Engine, hash: str) -> dict[str, Any]:  # noqa: A002
    """Return the original content for a CCR ``hash``.

    ``found`` is ``False`` (with ``content: null``) when the hash is unknown to
    this session, rather than raising, so hosts can branch on a normal result.
    """
    if not isinstance(hash, str) or not hash:
        raise ValueError("`hash` must be a non-empty string.")

    original = engine.retrieve(hash)
    return {
        "found": original is not None,
        "hash": hash,
        "content": original,
    }


def stats_tool(engine: Engine) -> dict[str, Any]:
    """Report cumulative compression savings for the session."""
    s = engine.stats()
    return {
        "compressions": s.compressions,
        "orig_tokens": s.orig_tokens,
        "new_tokens": s.new_tokens,
        "saved_tokens": s.saved_tokens,
        "ratio": round(s.ratio, 6),
    }
