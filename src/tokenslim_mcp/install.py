"""One-command install: register this MCP server into agent configs.

Each supported agent (Claude Code, Cursor, Codex) has a small :class:`Registrar`
that knows where its config lives and how to splice in an ``mcpServers`` entry
for the TokenSlim stdio server **without clobbering unrelated keys** — existing
servers and settings are merged, never overwritten.

The server entry is the standard stdio shape every MCP host understands::

    {"command": "<python>", "args": ["-m", "tokenslim_mcp"]}

Config paths are overridable (``config_path=...``) so tests can point a
registrar at a temp file and assert the merge in isolation.

Usage (CLI)::

    tokenslim-mcp install                 # all detected agents
    tokenslim-mcp install --agent cursor  # one agent
    tokenslim-mcp install --list          # show targets & detection

Adding an agent = subclass :class:`Registrar`, set ``name``/``default_path``,
implement ``_merge``, and list it in :data:`REGISTRARS`.
"""

from __future__ import annotations

import json
import os
import re
import sys
from abc import ABC, abstractmethod
from pathlib import Path

__all__ = [
    "Registrar",
    "ClaudeCodeRegistrar",
    "CursorRegistrar",
    "CodexRegistrar",
    "REGISTRARS",
    "server_command",
    "install",
    "main",
]

# The MCP server entry registered into each host. ``content`` is the logical
# server name MCP hosts key on; we use "tokenslim".
SERVER_NAME = "tokenslim"


def server_command() -> tuple[str, list[str]]:
    """Return ``(command, args)`` launching this server over stdio.

    Uses the *current* interpreter so the registered entry points at the same
    environment ``tokenslim-mcp`` was installed into (venv-safe).
    """
    return sys.executable, ["-m", "tokenslim_mcp"]


class Registrar(ABC):
    """Registers the TokenSlim MCP server into one agent's config file."""

    #: Human-facing agent id (used by ``--agent`` and reports).
    name: str = ""

    def __init__(self, config_path: str | os.PathLike[str] | None = None) -> None:
        self.config_path = Path(config_path) if config_path is not None else self.default_path()

    @abstractmethod
    def default_path(self) -> Path:
        """The agent's real config path when none is overridden."""

    @abstractmethod
    def _merge(self, existing: str | None) -> str:
        """Return new file contents with our server merged into ``existing``.

        ``existing`` is the current file text, or ``None`` if absent. Must
        preserve every unrelated key already present.
        """

    def detected(self) -> bool:
        """True when the agent looks installed (its config dir exists)."""
        return self.config_path.parent.exists()

    def register(self) -> Path:
        """Write the merged config, creating parent dirs as needed.

        Idempotent: running twice yields the same content. Returns the path
        written.
        """
        existing = (
            self.config_path.read_text(encoding="utf-8") if self.config_path.exists() else None
        )
        merged = self._merge(existing)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(merged, encoding="utf-8")
        return self.config_path


def _merge_json_mcp_servers(existing: str | None) -> str:
    """Merge our server into a JSON config's ``mcpServers`` object.

    Shared by the JSON-config agents (Claude Code, Cursor). Loads the existing
    document (empty object if absent/blank), sets only
    ``mcpServers["tokenslim"]``, and re-serialises — every other key survives.
    """
    data: dict = {}
    if existing and existing.strip():
        data = json.loads(existing)
        if not isinstance(data, dict):
            raise ValueError("config root must be a JSON object")

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    command, args = server_command()
    servers[SERVER_NAME] = {"command": command, "args": args}
    data["mcpServers"] = servers
    return json.dumps(data, indent=2) + "\n"


class ClaudeCodeRegistrar(Registrar):
    """Claude Code — top-level ``mcpServers`` in ``~/.claude.json``."""

    name = "claude-code"

    def default_path(self) -> Path:
        return Path.home() / ".claude.json"

    def _merge(self, existing: str | None) -> str:
        return _merge_json_mcp_servers(existing)


class CursorRegistrar(Registrar):
    """Cursor — ``mcpServers`` in ``~/.cursor/mcp.json``."""

    name = "cursor"

    def default_path(self) -> Path:
        return Path.home() / ".cursor" / "mcp.json"

    def _merge(self, existing: str | None) -> str:
        return _merge_json_mcp_servers(existing)


class CodexRegistrar(Registrar):
    """Codex CLI — a ``[mcp_servers.<name>]`` table in ``~/.codex/config.toml``.

    Codex config is TOML. To merge without a full TOML serialiser (which would
    drop comments/formatting from unrelated sections), we splice only our own
    ``[mcp_servers.tokenslim]`` block: replace it in place if present, else
    append it. All other file content is preserved byte-for-byte.
    """

    name = "codex"

    def default_path(self) -> Path:
        return Path.home() / ".codex" / "config.toml"

    def _block(self) -> str:
        command, args = server_command()
        args_toml = ", ".join(json.dumps(a) for a in args)
        return (
            f"[mcp_servers.{SERVER_NAME}]\ncommand = {json.dumps(command)}\nargs = [{args_toml}]\n"
        )

    def _merge(self, existing: str | None) -> str:
        block = self._block()
        if not existing or not existing.strip():
            return block

        # Match our own table: its header line plus every following line that is
        # NOT a new table header (a line beginning with "["). Matching whole
        # lines — rather than "up to the next '['" — is essential because TOML
        # values (e.g. ``args = [...]``) legitimately contain "[". Flags inline
        # for py3.10 compatibility.
        pattern = re.compile(
            r"(?m)^\[mcp_servers\." + re.escape(SERVER_NAME) + r"\][^\n]*\n(?:^(?!\[)[^\n]*\n?)*"
        )
        if pattern.search(existing):
            return pattern.sub(block, existing, count=1)

        sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
        return existing + sep + block


# Registry of every supported agent. Extend by appending a Registrar subclass.
REGISTRARS: tuple[type[Registrar], ...] = (
    ClaudeCodeRegistrar,
    CursorRegistrar,
    CodexRegistrar,
)


def _registrar_for(name: str, overrides: dict[str, str] | None = None) -> Registrar:
    overrides = overrides or {}
    for cls in REGISTRARS:
        if cls.name == name:
            return cls(config_path=overrides.get(name))
    raise ValueError(f"unknown agent {name!r} (known: {[c.name for c in REGISTRARS]})")


def install(
    agents: list[str] | None = None,
    *,
    only_detected: bool = True,
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Register the server into the given agents (default: all supported).

    Args:
        agents: Agent ids to target; ``None`` means every entry in
            :data:`REGISTRARS`.
        only_detected: When ``True`` (and ``agents`` is ``None``), skip agents
            whose config dir is absent. An explicitly named agent is always
            written.
        overrides: ``{agent_name: config_path}`` to redirect specific agents
            (tests point these at temp files).

    Returns:
        ``{agent_name: written_path}`` for every agent registered.
    """
    names = agents if agents is not None else [c.name for c in REGISTRARS]
    explicit = agents is not None
    written: dict[str, str] = {}
    for name in names:
        reg = _registrar_for(name, overrides)
        if not explicit and only_detected and not reg.detected():
            continue
        written[name] = str(reg.register())
    return written


def main(argv: list[str] | None = None) -> int:
    """``tokenslim-mcp install`` CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="tokenslim-mcp install",
        description="Register the TokenSlim MCP server into Claude Code / Cursor / Codex.",
    )
    parser.add_argument(
        "--agent",
        action="append",
        choices=[c.name for c in REGISTRARS],
        help="Target only this agent (repeatable). Default: all detected.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Register into every supported agent, even if not detected.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List target agents and their config paths, then exit.",
    )
    args = parser.parse_args(argv)

    if args.list:
        for cls in REGISTRARS:
            reg = cls()
            mark = "detected" if reg.detected() else "not detected"
            print(f"{cls.name:12} {reg.config_path}  [{mark}]")
        return 0

    written = install(agents=args.agent, only_detected=not args.all)
    if not written:
        print("No agents detected. Re-run with --all or --agent <name> to force.")
        return 0
    command, cmd_args = server_command()
    print(f"Registered '{SERVER_NAME}' ({command} {' '.join(cmd_args)}) into:")
    for name, path in written.items():
        print(f"  {name:12} {path}")
    return 0
