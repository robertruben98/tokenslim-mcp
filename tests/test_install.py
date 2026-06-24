import json
from pathlib import Path

from tokenslim_mcp.install import register_mcp


def test_register_mcp(tmp_path: Path) -> None:
    config_file = tmp_path / ".claude.json"

    # 1. Test registration in clean file
    res = register_mcp(str(config_file))
    assert res is True
    assert config_file.exists()

    with open(config_file, encoding="utf-8") as f:
        data = json.load(f)
    assert "mcpServers" in data
    assert "tokenslim" in data["mcpServers"]
    assert "command" in data["mcpServers"]["tokenslim"]

    # 2. Test registration in existing file preserving other servers
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "mcpServers": {
                    "other_server": {
                        "command": "node",
                        "args": [],
                    }
                }
            },
            f,
        )

    res = register_mcp(str(config_file))
    assert res is True

    with open(config_file, encoding="utf-8") as f:
        data = json.load(f)
    assert "other_server" in data["mcpServers"]
    assert "tokenslim" in data["mcpServers"]
