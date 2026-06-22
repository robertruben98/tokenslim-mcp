"""Install/registry tests — every registrar points at a temp config file.

Asserts the server entry is added and that pre-existing config (other MCP
servers, unrelated top-level keys, other TOML tables) survives the merge.
"""

from __future__ import annotations

import json

import pytest

from tokenslim_mcp.install import (
    SERVER_NAME,
    ClaudeCodeRegistrar,
    CodexRegistrar,
    CursorRegistrar,
    install,
    server_command,
)

JSON_REGISTRARS = [ClaudeCodeRegistrar, CursorRegistrar]


@pytest.mark.parametrize("cls", JSON_REGISTRARS)
def test_json_registrar_creates_config(cls, tmp_path):
    cfg = tmp_path / "agent.json"
    cls(config_path=cfg).register()

    data = json.loads(cfg.read_text())
    command, args = server_command()
    assert data["mcpServers"][SERVER_NAME] == {"command": command, "args": args}


@pytest.mark.parametrize("cls", JSON_REGISTRARS)
def test_json_registrar_merges_without_clobbering(cls, tmp_path):
    cfg = tmp_path / "agent.json"
    cfg.write_text(
        json.dumps(
            {
                "theme": "dark",  # unrelated top-level key
                "mcpServers": {
                    "other": {"command": "node", "args": ["other.js"]},
                },
            }
        )
    )

    cls(config_path=cfg).register()
    data = json.loads(cfg.read_text())

    # Our entry was added...
    assert SERVER_NAME in data["mcpServers"]
    # ...the existing server and unrelated keys are untouched.
    assert data["mcpServers"]["other"] == {"command": "node", "args": ["other.js"]}
    assert data["theme"] == "dark"


@pytest.mark.parametrize("cls", JSON_REGISTRARS)
def test_json_registrar_is_idempotent(cls, tmp_path):
    cfg = tmp_path / "agent.json"
    reg = cls(config_path=cfg)
    reg.register()
    first = cfg.read_text()
    reg.register()
    assert cfg.read_text() == first


def test_codex_registrar_appends_block(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "# user config\n"
        'model = "o4"\n\n'
        "[mcp_servers.other]\n"
        'command = "node"\n'
        'args = ["other.js"]\n'
    )

    CodexRegistrar(config_path=cfg).register()
    text = cfg.read_text()

    # Existing content preserved verbatim.
    assert "# user config" in text
    assert 'model = "o4"' in text
    assert "[mcp_servers.other]" in text
    # Our table added.
    assert f"[mcp_servers.{SERVER_NAME}]" in text

    parsed = _toml_loads(text)
    command, args = server_command()
    assert parsed["mcp_servers"][SERVER_NAME]["command"] == command
    assert parsed["mcp_servers"][SERVER_NAME]["args"] == args
    assert parsed["mcp_servers"]["other"]["command"] == "node"
    assert parsed["model"] == "o4"


def test_codex_registrar_is_idempotent(tmp_path):
    cfg = tmp_path / "config.toml"
    reg = CodexRegistrar(config_path=cfg)
    reg.register()
    first = cfg.read_text()
    reg.register()
    second = cfg.read_text()
    assert first == second
    # Exactly one table for our server, not duplicated.
    assert second.count(f"[mcp_servers.{SERVER_NAME}]") == 1


def test_codex_registrar_replaces_own_block_in_place(tmp_path):
    cfg = tmp_path / "config.toml"
    # A stale block for our server (e.g. an old python path) plus a neighbour.
    cfg.write_text(
        f"[mcp_servers.{SERVER_NAME}]\n"
        'command = "/old/python"\n'
        'args = ["-m", "tokenslim_mcp"]\n\n'
        "[mcp_servers.other]\n"
        'command = "node"\n'
    )

    CodexRegistrar(config_path=cfg).register()
    parsed = _toml_loads(cfg.read_text())
    command, _ = server_command()
    # Refreshed to the current interpreter, neighbour intact, single block.
    assert parsed["mcp_servers"][SERVER_NAME]["command"] == command
    assert parsed["mcp_servers"]["other"]["command"] == "node"
    assert cfg.read_text().count(f"[mcp_servers.{SERVER_NAME}]") == 1


def test_install_targets_named_agents_with_overrides(tmp_path):
    claude_cfg = tmp_path / "claude.json"
    cursor_cfg = tmp_path / "cursor.json"

    written = install(
        agents=["claude-code", "cursor"],
        overrides={"claude-code": str(claude_cfg), "cursor": str(cursor_cfg)},
    )

    assert set(written) == {"claude-code", "cursor"}
    for path in (claude_cfg, cursor_cfg):
        data = json.loads(path.read_text())
        assert SERVER_NAME in data["mcpServers"]


def _toml_loads(text: str) -> dict:
    """tomllib (3.11+) with a tomli fallback for 3.10."""
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - exercised only on py3.10
        import tomli as tomllib  # type: ignore[no-redef]
    return tomllib.loads(text)
