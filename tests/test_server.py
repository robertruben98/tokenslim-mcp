"""Server-wiring tests: tools are registered and dispatch through FastMCP."""

from __future__ import annotations

import json

from tokenslim_mcp import Engine, build_server

BIG_JSON = json.dumps({"rows": [{"id": i, "v": i * i} for i in range(60)]}, indent=2)


async def test_three_tools_are_registered():
    mcp = build_server(Engine())
    names = {t.name for t in await mcp.list_tools()}
    assert names == {"tokenslim_compress", "tokenslim_retrieve", "tokenslim_stats"}


async def test_compress_then_retrieve_through_call_tool():
    mcp = build_server(Engine())

    _, compressed = await mcp.call_tool("tokenslim_compress", {"content": BIG_JSON})
    assert compressed["changed"] is True
    digest = compressed["hash"]

    _, retrieved = await mcp.call_tool("tokenslim_retrieve", {"hash": digest})
    assert retrieved["found"] is True
    assert retrieved["content"] == BIG_JSON

    _, stats = await mcp.call_tool("tokenslim_stats", {})
    assert stats["compressions"] == 1
    assert stats["saved_tokens"] > 0


async def test_each_server_has_isolated_engine():
    a = build_server(Engine())
    b = build_server(Engine())

    _, ca = await a.call_tool("tokenslim_compress", {"content": BIG_JSON})
    # The hash exists in a's store but not b's.
    _, ra = await a.call_tool("tokenslim_retrieve", {"hash": ca["hash"]})
    _, rb = await b.call_tool("tokenslim_retrieve", {"hash": ca["hash"]})
    assert ra["found"] is True
    assert rb["found"] is False
