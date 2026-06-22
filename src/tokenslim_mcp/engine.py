"""Session engine wrapping the ``tokenslim`` core for the MCP tools.

The MCP tools operate on a single content blob, while the core ``compress()``
works on a message array. This module bridges the two: wrap the blob as a
one-message array, compress it, and pull the rewritten content + stats back
out. It also owns:

  * the **retrieval store** mapping a content hash -> original blob, and
  * **cumulative stats** across every compression in the session.

Retrieval store: the ``tokenslim`` core now ships a real CCR store
(``tokenslim.store.CCRStore``: in-memory + persistent SQLite) and a
``tokenslim.retrieve.retrieve()`` lookup. When CCR is enabled the engine puts
each full original blob into that core store (keyed by ``content_hash``, the
same key the core embeds in its markers) and resolves ``retrieve`` through the
core ``retrieve()``. With a SQLite path this is **persistent and cross-process**
— a hash produced by one server process round-trips in another.

The legacy per-process dict survives only as a fallback for when CCR is disabled
(``ccr=False``), so retrieval still works without a backing store.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from tokenslim import compress as _core_compress
from tokenslim import count_tokens
from tokenslim.ccr import content_hash
from tokenslim.config import Config
from tokenslim.retrieve import retrieve as _core_retrieve
from tokenslim.store import CCRStore, InMemoryCCRStore, SQLiteCCRStore


@dataclass(frozen=True)
class CompressResult:
    """Outcome of compressing one blob."""

    content: str
    orig_tokens: int
    new_tokens: int
    ratio: float
    changed: bool
    hash: str
    content_type: str | None


@dataclass
class SessionStats:
    """Cumulative compression accounting for the life of the server process."""

    compressions: int = 0
    orig_tokens: int = 0
    new_tokens: int = 0

    @property
    def saved_tokens(self) -> int:
        return self.orig_tokens - self.new_tokens

    @property
    def ratio(self) -> float:
        """Overall savings fraction (``1 - new/orig``); ``0.0`` when no input."""
        if self.orig_tokens <= 0:
            return 0.0
        return 1.0 - (self.new_tokens / self.orig_tokens)


class Engine:
    """Stateful, thread-safe wrapper used by the MCP tool handlers.

    Args:
        ccr: When ``True`` (default), originals are stored in — and retrieved
            from — the core CCR store, so retrieval is reversible and (with a
            SQLite path) survives across processes. When ``False``, retrieval
            falls back to a process-local dict and the core store is bypassed.
        ccr_path: Path to a SQLite database backing the CCR store. When set, the
            store is a persistent, cross-process :class:`SQLiteCCRStore`; when
            ``None`` it is a process-local :class:`InMemoryCCRStore`. Ignored
            when ``ccr=False``. Overridable so tests can point at a temp file.
        ccr_ttl: Optional TTL (seconds) for stored records; ``None`` = forever.
    """

    def __init__(
        self,
        *,
        ccr: bool = True,
        ccr_path: str | None = None,
        ccr_ttl: int | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._stats = SessionStats()
        self._ccr_path = ccr_path
        self._ccr_ttl = ccr_ttl

        # Core CCR store (the cross-process source of truth) when enabled. This
        # is the store the engine explicitly put()s full originals into and
        # reads back on retrieve. A SQLite path makes it persistent and shared
        # across processes; otherwise it is process-local but still the real
        # core store implementation.
        self._ccr_store: CCRStore | None
        if ccr:
            self._ccr_store = (
                SQLiteCCRStore(ccr_path, ttl=ccr_ttl)
                if ccr_path is not None
                else InMemoryCCRStore(ttl=ccr_ttl)
            )
        else:
            self._ccr_store = None

        # Legacy fallback: only consulted when CCR is disabled.
        self._fallback_store: dict[str, str] = {}

    def _compress_config(self) -> Config:
        """Config for a core ``compress()`` call.

        The core builds its *own* CCR store from config (it has no store
        injection point), so steer it at the same backend/path the engine uses.
        For a SQLite path this means the compressor's internal elision markers
        and the engine's full-blob records land in one shared database file.
        """
        if self._ccr_store is None:
            return Config(min_bytes=0, ccr=False)
        if self._ccr_path is not None:
            return Config(
                min_bytes=0,
                ccr=True,
                ccr_backend="sqlite",
                ccr_path=self._ccr_path,
                ccr_ttl=self._ccr_ttl,
            )
        return Config(min_bytes=0, ccr=True, ccr_ttl=self._ccr_ttl)

    def compress(self, content: str, content_type: str | None = None) -> CompressResult:
        """Compress ``content`` and register it for later retrieval.

        ``content_type`` is an advisory hint surfaced back to the caller; the
        core auto-detects the real type. ``min_bytes=0`` forces compression of
        even small blobs so the tool is deterministic for callers that pass one
        blob at a time.

        The full original is put into the engine's core CCR store under its
        ``content_hash`` so a later ``retrieve`` round-trips the exact bytes
        (cross-process when SQLite-backed). This explicit put is the source of
        truth for retrieval, independent of whatever the compressor itself
        elided.
        """
        messages = [{"role": "user", "content": content}]
        new_messages, stats = _core_compress(messages, self._compress_config())
        new_content = new_messages[0]["content"]
        if not isinstance(new_content, str):
            # Core may return structured content; fall back to the original text.
            new_content = content

        digest = content_hash(content)
        changed = stats.new_tokens < stats.orig_tokens

        if self._ccr_store is not None:
            # put() is idempotent and keyed by content_hash, so this key == digest.
            self._ccr_store.put(content)
        else:
            with self._lock:
                self._fallback_store[digest] = content

        with self._lock:
            self._stats.compressions += 1
            self._stats.orig_tokens += stats.orig_tokens
            self._stats.new_tokens += stats.new_tokens

        return CompressResult(
            content=new_content,
            orig_tokens=stats.orig_tokens,
            new_tokens=stats.new_tokens,
            ratio=stats.ratio,
            changed=changed,
            hash=digest,
            content_type=content_type,
        )

    def retrieve(self, digest: str) -> str | None:
        """Return the original content for ``digest``, or ``None`` if unknown.

        Resolves through the core CCR store (cross-process when SQLite-backed);
        falls back to the process-local dict only when CCR is disabled.
        """
        if self._ccr_store is not None:
            return _core_retrieve(digest, store=self._ccr_store)
        with self._lock:
            return self._fallback_store.get(digest)

    def stats(self) -> SessionStats:
        """Snapshot the cumulative session stats."""
        with self._lock:
            return SessionStats(
                compressions=self._stats.compressions,
                orig_tokens=self._stats.orig_tokens,
                new_tokens=self._stats.new_tokens,
            )

    @staticmethod
    def count_tokens(text: str) -> int:
        """Expose the core token counter (used in tests/diagnostics)."""
        return count_tokens(text)


def _default_engine() -> Engine:
    """Build the shared server engine, honouring CCR env configuration.

    ``TOKENSLIM_MCP_CCR_PATH`` selects a persistent SQLite store (recommended
    for a long-running server so retrieval survives restarts); unset keeps an
    in-memory store. ``TOKENSLIM_MCP_CCR=0`` disables CCR (dict fallback).
    """
    import os

    ccr = os.environ.get("TOKENSLIM_MCP_CCR", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    path = os.environ.get("TOKENSLIM_MCP_CCR_PATH") or None
    ttl_raw = os.environ.get("TOKENSLIM_MCP_CCR_TTL")
    ttl = int(ttl_raw) if ttl_raw else None
    return Engine(ccr=ccr, ccr_path=path, ccr_ttl=ttl)


# A module-level engine shared by the server's tool handlers for the session.
engine = _default_engine()
