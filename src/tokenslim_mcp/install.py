"""Helper to register TokenSlim MCP server in Claude Code and Cursor configs."""

from __future__ import annotations

import json
import os
import shutil
import sys

__all__ = ["install_mcp_configs", "register_mcp"]


def get_server_command() -> tuple[str, list[str]]:
    """Determine the command and arguments to start the stdio server."""
    path = shutil.which("tokenslim-mcp")
    if path:
        return path, []
    return sys.executable, ["-m", "tokenslim_mcp"]


def register_mcp(config_path: str, name: str = "tokenslim") -> bool:
    """Write the MCP server configuration block to a host's JSON config."""
    try:
        config_dir = os.path.dirname(config_path)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)

        config_data = {}
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                try:
                    config_data = json.load(f)
                except json.JSONDecodeError:
                    pass

        if not isinstance(config_data, dict):
            config_data = {}

        if "mcpServers" not in config_data:
            config_data["mcpServers"] = {}

        cmd, args = get_server_command()
        config_data["mcpServers"][name] = {"command": cmd, "args": args, "env": {}}

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error writing configuration to {config_path}: {e}", file=sys.stderr)
        return False


def install_mcp_configs() -> None:
    """Register the MCP server in Claude Code and Cursor configurations."""
    home = os.path.expanduser("~")

    # 1. Claude Code
    claude_path = os.path.join(home, ".claude.json")
    print(f"Registering in Claude Code config ({claude_path})...")
    if register_mcp(claude_path):
        print("✓ Claude Code registration successful!")
    else:
        print("✗ Claude Code registration failed.")

    # 2. Cursor
    cursor_path = os.path.join(home, ".cursor", "mcp.json")
    print(f"Registering in Cursor config ({cursor_path})...")
    if register_mcp(cursor_path):
        print("✓ Cursor registration successful!")
    else:
        print("✗ Cursor registration failed.")
