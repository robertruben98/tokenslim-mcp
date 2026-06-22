"""Stdio MCP server exposing the TokenSlim compression tools.

Built on the official Python ``mcp`` SDK (``FastMCP``). Run it as::

    tokenslim-mcp            # console script
    python -m tokenslim_mcp  # module entrypoint

then register it with an MCP host (Claude Code, Cursor, …) as a stdio server.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .engine import Engine, engine
from .tools import compress_tool, retrieve_tool, stats_tool


def build_server(session_engine: Engine | None = None) -> FastMCP:
    """Construct a :class:`FastMCP` server with the three TokenSlim tools bound.

    A dedicated :class:`Engine` can be injected (tests do this); otherwise the
    shared module-level engine is used so a long-running server accumulates
    session stats and a retrieval store across calls.
    """
    eng = session_engine or engine
    mcp = FastMCP(
        "tokenslim",
        instructions=(
            "Context compression for LLM agents. Use tokenslim_compress to shrink "
            "large tool outputs, logs, JSON or files before they enter context; "
            "tokenslim_retrieve to fetch the original by its hash; and "
            "tokenslim_stats for cumulative session savings."
        ),
    )

    @mcp.tool(
        name="tokenslim_compress",
        description=(
            "Compress a content blob (tool output, log, JSON, file, RAG chunk). "
            "Returns compressed text, token stats (orig/new/saved/ratio), and a "
            "CCR hash usable with tokenslim_retrieve."
        ),
    )
    def tokenslim_compress(content: str, content_type: str | None = None) -> dict[str, Any]:
        return compress_tool(eng, content, content_type=content_type)

    @mcp.tool(
        name="tokenslim_retrieve",
        description="Return the original, uncompressed content for a CCR hash.",
    )
    def tokenslim_retrieve(hash: str) -> dict[str, Any]:  # noqa: A002
        return retrieve_tool(eng, hash)

    @mcp.tool(
        name="tokenslim_stats",
        description="Report cumulative compression savings for the current session.",
    )
    def tokenslim_stats() -> dict[str, Any]:
        return stats_tool(eng)

    return mcp


def main(argv: list[str] | None = None) -> None:
    """Console-script entrypoint.

    ``tokenslim-mcp``            runs the stdio MCP server (default).
    ``tokenslim-mcp install ...`` registers the server into agent configs and
    exits; all flags after ``install`` are handled by :func:`install.main`.
    """
    import sys

    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "install":
        from .install import main as install_main

        raise SystemExit(install_main(args[1:]))

    build_server().run("stdio")


if __name__ == "__main__":
    main()
