"""Tool-handler tests — call the implementations directly, no live MCP host."""

from __future__ import annotations

import json

import pytest

from tokenslim_mcp import Engine, compress_tool, retrieve_tool, stats_tool

# A large pretty-printed JSON blob the core will compress.
BIG_JSON = json.dumps(
    {"rows": [{"id": i, "name": f"row-{i}", "ok": True} for i in range(80)]},
    indent=2,
)

# A repetitive log blob (exercises a different compressor path).
BIG_LOG = "\n".join(f"2024-01-01 12:00:{i:02d} INFO worker did a thing #{i}" for i in range(120))


@pytest.fixture
def engine() -> Engine:
    return Engine()


def test_compress_shrinks_json_and_reports_stats(engine: Engine):
    result = compress_tool(engine, BIG_JSON, content_type="json")

    assert result["changed"] is True
    assert result["content_type"] == "json"
    stats = result["stats"]
    assert stats["orig_tokens"] > 0
    assert stats["new_tokens"] < stats["orig_tokens"]
    assert stats["saved_tokens"] == stats["orig_tokens"] - stats["new_tokens"]
    assert 0.0 < stats["ratio"] <= 1.0
    # A hash is always emitted for retrieval.
    assert isinstance(result["hash"], str) and len(result["hash"]) > 0


def test_compress_shrinks_log(engine: Engine):
    result = compress_tool(engine, BIG_LOG)
    assert result["stats"]["new_tokens"] < result["stats"]["orig_tokens"]
    assert result["changed"] is True


def test_retrieve_round_trips_original(engine: Engine):
    result = compress_tool(engine, BIG_JSON)
    digest = result["hash"]

    retrieved = retrieve_tool(engine, digest)
    assert retrieved["found"] is True
    assert retrieved["hash"] == digest
    # The retrieved content is byte-for-byte the original, even though the
    # compressed `content` differs.
    assert retrieved["content"] == BIG_JSON
    assert result["content"] != BIG_JSON


def test_retrieve_unknown_hash_returns_not_found(engine: Engine):
    out = retrieve_tool(engine, "deadbeefdeadbeef")
    assert out["found"] is False
    assert out["content"] is None


def test_retrieve_rejects_empty_hash(engine: Engine):
    with pytest.raises(ValueError):
        retrieve_tool(engine, "")


def test_compress_rejects_non_string(engine: Engine):
    with pytest.raises(ValueError):
        compress_tool(engine, 123)  # type: ignore[arg-type]


def test_stats_accumulate_across_calls(engine: Engine):
    empty = stats_tool(engine)
    assert empty["compressions"] == 0
    assert empty["orig_tokens"] == 0
    assert empty["ratio"] == 0.0

    r1 = compress_tool(engine, BIG_JSON)
    r2 = compress_tool(engine, BIG_LOG)

    s = stats_tool(engine)
    assert s["compressions"] == 2
    assert s["orig_tokens"] == r1["stats"]["orig_tokens"] + r2["stats"]["orig_tokens"]
    assert s["new_tokens"] == r1["stats"]["new_tokens"] + r2["stats"]["new_tokens"]
    assert s["saved_tokens"] == s["orig_tokens"] - s["new_tokens"]
    assert s["saved_tokens"] > 0
    assert 0.0 < s["ratio"] <= 1.0


def test_same_content_hashes_stably(engine: Engine):
    a = compress_tool(engine, BIG_JSON)
    b = compress_tool(engine, BIG_JSON)
    # content_hash is deterministic over the input.
    assert a["hash"] == b["hash"]
