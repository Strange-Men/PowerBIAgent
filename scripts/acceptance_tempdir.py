"""M5.8.3 acceptance-only temp lifecycle; never a product resource cleaner.

mkdtemp creates a private directory; the context's finally owns cleanup. There
is deliberately no GC finalizer which could bypass marker/identity validation.
No scanning, wildcard deletion, permission changes or alternate cleanup paths.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

MARKER = ".powerbiagent-acceptance-owner.json"
PREFIXES = frozenset({
    "powerbiagent-context-real-", "powerbiagent-m583-validation-",
    "powerbiagent-context-audit-", "powerbiagent-semantic-comparison-",
})


def _identity(path: Path) -> tuple[int, int]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError("ownership_mismatch")
    return info.st_dev, info.st_ino


def _delete_owned_tree(path: Path) -> None:
    shutil.rmtree(path)


def _present(path: Path) -> bool:
    # Do not confuse "cannot inspect" with absence; broken links also count.
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


@contextmanager
def owned_acceptance_tempdir(*, prefix: str, parent: Path | None = None):
    """Yield one owned absolute path; preserve failures and report real residual.

    Cleanup is attempted on normal exit, exception, SystemExit and cancellation.
    An OS/executor denial is a cleanup warning, not a product failure. The final
    release caller must still inspect temporary_residual; it is never inferred
    from whether the acceptance body succeeded.
    """
    if prefix not in PREFIXES:
        raise ValueError("acceptance_prefix_not_allowed")
    base = (parent or Path(tempfile.gettempdir())).resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix=prefix, dir=base)).absolute()
    created_identity = None
    marker = {"project":"PowerBIAgent", "milestone":"M5.8.3", "run_id":uuid.uuid4().hex,
        "path":str(root), "parent":str(base), "prefix":prefix}
    marker_path = root / MARKER
    try:
        created_identity = _identity(root)
        marker_path.write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
        yield root
    finally:
        warning = None
        if _present(root):
            try:
                if (root.parent != base or root.resolve() != root or not root.name.startswith(prefix)
                        or _identity(root) != created_identity or not marker_path.is_file()
                        or marker_path.is_symlink()):
                    raise ValueError("ownership_mismatch")
                _identity(marker_path)
                if json.loads(marker_path.read_text(encoding="utf-8")) != marker:
                    raise ValueError("ownership_mismatch")
                # Reject nested reparse points too. Do not follow a substituted
                # directory into a different user's/project's files.
                for directory, dirs, files in os.walk(root, followlinks=False):
                    for name in (*dirs, *files):
                        _identity(Path(directory) / name)
                _delete_owned_tree(root)
            except ValueError:
                warning = "ownership_mismatch"
            except Exception as error:
                warning = type(error).__name__
            if _present(root) and warning is None:
                warning = "cleanup_incomplete"
        residual = int(_present(root))
        report = {"path":str(root), "temporary_residual":residual}
        if warning:
            print(json.dumps({**report, "cleanup_warning":warning}), file=sys.stderr, flush=True)
        print(json.dumps(report), flush=True)
