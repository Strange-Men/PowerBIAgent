"""Secret-safe runtime build identity for the local PowerBIAgent process.

Every startup, health response and diagnostic line can be tied to the exact
worktree that is actually running: a commit SHA plus a short fingerprint of the
uncommitted diff.  This permanently prevents "I am testing a stale backend" from
being invisible.

Only a commit SHA and a content hash are produced.  No source text, no absolute
path beyond the repository root, no secret, prompt or business value is ever
returned, logged or raised.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_UNKNOWN = "unknown"
_GIT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class RuntimeBuildIdentity:
    """Bounded, non-identifying description of the running revision."""

    head: str
    dirty: bool
    fingerprint: str
    build_id: str

    def public(self) -> dict[str, object]:
        return {
            "runtime_head": self.head,
            "runtime_dirty": self.dirty,
            "runtime_fingerprint": self.fingerprint,
            "runtime_build_id": self.build_id,
        }


def _git(*args: str) -> str | None:
    """Run one bounded git command from the repository root; return stdout only.

    Any failure (git absent, not a repository, timeout) yields ``None`` so the
    caller can fall back to a safe placeholder.  Stderr is never surfaced.
    """
    try:
        completed = subprocess.run(
            ("git", *args),
            cwd=_REPOSITORY_ROOT,
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.decode("utf-8", "replace")


def _short_hash(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.hexdigest()[:16]


def compute_runtime_build_identity() -> RuntimeBuildIdentity:
    head_raw = _git("rev-parse", "HEAD")
    head = head_raw.strip() if head_raw and head_raw.strip() else _UNKNOWN

    status = _git("status", "--porcelain")
    diff = _git("diff", "HEAD")
    if status is None or diff is None:
        return RuntimeBuildIdentity(
            head=head,
            dirty=False,
            fingerprint=_UNKNOWN,
            build_id=f"{head[:12] or _UNKNOWN}",
        )

    dirty = bool(status.strip())
    if not dirty:
        return RuntimeBuildIdentity(
            head=head, dirty=False, fingerprint=_UNKNOWN, build_id=head[:12] or _UNKNOWN
        )

    # Hash only the change *shape and content*: the diff text and the sorted
    # name/status list.  Nothing from it is retained beyond the digest length.
    tracked = "\n".join(sorted(line for line in diff.splitlines()))
    names = "\n".join(sorted(status.splitlines()))
    fingerprint = _short_hash(tracked.encode("utf-8"), names.encode("utf-8"))
    return RuntimeBuildIdentity(
        head=head,
        dirty=True,
        fingerprint=fingerprint,
        build_id=f"{head[:12]}-dirty-{fingerprint[:8]}",
    )


@lru_cache(maxsize=1)
def runtime_build_identity() -> RuntimeBuildIdentity:
    """Process-scoped identity, computed once at first use and then frozen."""
    return compute_runtime_build_identity()