"""Session engine wrapping the ``tokenslim`` core for the MCP tools.

The MCP tools operate on a single content blob, while the core ``compress()``
works on a message array. This module bridges the two: wrap the blob as a
one-message array, compress it, and pull the rewritten content + stats back
out. It also owns:

  * a per-session **retrieval store** mapping a content hash -> original blob,
    and
  * **cumulative stats** across every compression in the session.

Retrieval store note (Known gap): the ``tokenslim`` core ships CCR *markers*
and ``content_hash`` (``tokenslim.ccr``) but does not yet expose a
``retrieve()`` / persistent store on ``main``. Until that lands, retrieval is
backed by this in-process dict, populated by ``compress``. The hash is computed
with the core's ``content_hash`` so the keys are already compatible with the
future core store.
TODO(core-ccr): switch ``retrieve`` to ``tokenslim.ccr.retrieve`` once merged.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from tokenslim import compress as _core_compress
from tokenslim import count_tokens
from tokenslim.ccr import content_hash


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
    """Stateful, thread-safe wrapper used by the MCP tool handlers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, str] = {}
        self._stats = SessionStats()

    def compress(self, content: str, content_type: str | None = None) -> CompressResult:
        """Compress ``content`` and register it for later retrieval.

        ``content_type`` is an advisory hint surfaced back to the caller; the
        core auto-detects the real type. ``min_bytes=0`` forces compression of
        even small blobs so the tool is deterministic for callers that pass one
        blob at a time.
        """
        messages = [{"role": "user", "content": content}]
        new_messages, stats = _core_compress(messages, min_bytes=0)
        new_content = new_messages[0]["content"]
        if not isinstance(new_content, str):
            # Core may return structured content; fall back to the original text.
            new_content = content

        digest = content_hash(content)
        changed = stats.new_tokens < stats.orig_tokens

        with self._lock:
            self._store[digest] = content
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
        """Return the original content for ``digest``, or ``None`` if unknown."""
        with self._lock:
            return self._store.get(digest)

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


# A module-level engine shared by the server's tool handlers for the session.
engine = Engine()
