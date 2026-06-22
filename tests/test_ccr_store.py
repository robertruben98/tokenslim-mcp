"""CCR migration tests — retrieve resolves through the core CCR store.

No live MCP host: tool handlers are called directly. The headline guarantee is
that with a SQLite-backed store a hash produced by one ``Engine`` round-trips in
a *separate* engine (a stand-in for a second server process).
"""

from __future__ import annotations

import json

from tokenslim.ccr import content_hash

from tokenslim_mcp import Engine, compress_tool, retrieve_tool

BIG_JSON = json.dumps(
    {"rows": [{"id": i, "name": f"row-{i}", "ok": True} for i in range(80)]},
    indent=2,
)


def test_retrieve_round_trips_via_core_store_in_memory():
    eng = Engine()  # default: CCR on, in-memory core store
    digest = compress_tool(eng, BIG_JSON)["hash"]

    out = retrieve_tool(eng, digest)
    assert out["found"] is True
    assert out["content"] == BIG_JSON


def test_sqlite_store_round_trips_across_engines(tmp_path):
    db = str(tmp_path / "ccr.sqlite3")

    # Process A: compress and stash into the persistent store.
    producer = Engine(ccr_path=db)
    digest = compress_tool(producer, BIG_JSON)["hash"]

    # Process B: a brand-new engine over the same DB resolves the hash.
    consumer = Engine(ccr_path=db)
    out = retrieve_tool(consumer, digest)
    assert out["found"] is True
    assert out["content"] == BIG_JSON


def test_hash_matches_core_content_hash(tmp_path):
    eng = Engine(ccr_path=str(tmp_path / "ccr.sqlite3"))
    digest = compress_tool(eng, BIG_JSON)["hash"]
    # The store key is the core content_hash of the *full* original, so an
    # independent caller can recompute the retrieval key.
    assert digest == content_hash(BIG_JSON)


def test_retrieve_unknown_hash_returns_not_found(tmp_path):
    eng = Engine(ccr_path=str(tmp_path / "ccr.sqlite3"))
    out = retrieve_tool(eng, "deadbeefdeadbeef")
    assert out["found"] is False
    assert out["content"] is None


def test_ccr_disabled_falls_back_to_process_store():
    # With CCR off there is no core store; retrieval must still round-trip via
    # the in-process fallback within the same engine.
    eng = Engine(ccr=False)
    digest = compress_tool(eng, BIG_JSON)["hash"]
    out = retrieve_tool(eng, digest)
    assert out["found"] is True
    assert out["content"] == BIG_JSON

    # ...but the fallback is process-local: a second engine cannot see it.
    other = Engine(ccr=False)
    assert retrieve_tool(other, digest)["found"] is False
