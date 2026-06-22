"""tokenslim-mcp — MCP server exposing the TokenSlim compression engine.

Tools: ``tokenslim_compress``, ``tokenslim_retrieve``, ``tokenslim_stats``.
"""

from __future__ import annotations

from .engine import CompressResult, Engine, SessionStats, engine
from .install import (
    ClaudeCodeRegistrar,
    CodexRegistrar,
    CursorRegistrar,
    Registrar,
    install,
)
from .server import build_server, main
from .tools import compress_tool, retrieve_tool, stats_tool

__version__ = "0.0.1"

__all__ = [
    "__version__",
    "Engine",
    "engine",
    "CompressResult",
    "SessionStats",
    "build_server",
    "main",
    "compress_tool",
    "retrieve_tool",
    "stats_tool",
    "install",
    "Registrar",
    "ClaudeCodeRegistrar",
    "CursorRegistrar",
    "CodexRegistrar",
]
