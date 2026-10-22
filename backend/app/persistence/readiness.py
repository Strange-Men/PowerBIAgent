"""One non-migrating Cloud persistence readiness gate.

Only schema metadata is read. Migration belongs to the explicit operator helper,
never application startup. Missing databases are not implicitly created.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import os
import re
import sqlite3
from contextlib import closing
from tempfile import TemporaryFile

from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.app.config.settings import IdentityMode, PersistenceBackend, PowerBIMode

REPOSITORY = Path(__file__).resolve().parents[3]


def migration_config(settings):
    """Ignore ini defaults: the operator and application target the same Settings."""
    from backend.app.persistence.database import build_sqlite_url
    config = Config()
    config.set_main_option('script_location', str(REPOSITORY / 'backend/alembic'))
    config.set_main_option('sqlalchemy.url', build_sqlite_url(settings).replace('%', '%%'))
    return config


def expected_revision():
    config = Config()
    config.set_main_option('script_location', str(REPOSITORY / 'backend/alembic'))
    return ScriptDirectory.from_config(config).get_current_head()


def required(settings):
    return (settings.identity_mode == IdentityMode.ENTRA_BFF
        and settings.powerbi_mode == PowerBIMode.FABRIC_IQ
        and settings.allow_business_persistence
        and settings.persistence_backend == PersistenceBackend.SQLITE)


@dataclass(frozen=True)
class PersistenceReadiness:
    ready: bool
    reason: str | None
    current_revision: str | None
    expected_revision: str

    def public(self):
        values = asdict(self)
        return {'persistence_ready': values.pop('ready'),
                'persistence_reason': values.pop('reason'), **values}

    def require_ready(self):
        if not self.ready:
            raise PersistenceNotReady(self)


class PersistenceNotReady(RuntimeError):
    def __init__(self, result):
        self.readiness = result
        super().__init__(result.reason)


def check_persistence(settings):
    """Check exact revision/tables, DB access and disposable artifact write probe."""
    head = expected_revision()
    current = None
    path = Path(settings.persistence_database_path).resolve()
    try:
        if not path.exists():
            return PersistenceReadiness(False, 'PERSISTENCE_SCHEMA_OUTDATED', None, head)
        if not path.is_file() or not os.access(path, os.R_OK | os.W_OK) or not os.access(path.parent, os.W_OK):
            return PersistenceReadiness(False, 'PERSISTENCE_UNAVAILABLE', None, head)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'alembic_version' in tables:
                revisions = [row[0] for row in conn.execute('SELECT version_num FROM alembic_version')]
                current = revisions[0] if len(revisions) == 1 and isinstance(revisions[0], str) and re.fullmatch(r'[a-zA-Z0-9_]{1,32}', revisions[0]) else None
            from backend.app.persistence.models import Base
            if current != head or not set(Base.metadata.tables).issubset(tables):
                return PersistenceReadiness(False, 'PERSISTENCE_SCHEMA_OUTDATED', current, head)
        root = Path(settings.report_artifacts_path).resolve()
        root.mkdir(parents=True, exist_ok=True)
        with TemporaryFile(dir=root) as probe:
            probe.write(b'readiness')
            probe.flush()
        return PersistenceReadiness(True, None, current, head)
    except (OSError, sqlite3.Error):
        return PersistenceReadiness(False, 'PERSISTENCE_UNAVAILABLE', current, head)
