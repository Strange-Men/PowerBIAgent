"""Explicit operator lifecycle: inspect, optionally upgrade, then prove readiness.

Run from the application working directory, with the same Settings environment:
python scripts/prepare_persistence.py --upgrade
Stop application workers and back up existing databases before upgrading.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command
from backend.app.config.settings import get_settings, PersistenceBackend
from backend.app.persistence.readiness import check_persistence, migration_config


def prepare(settings, *, upgrade=False):
    if settings.persistence_backend != PersistenceBackend.SQLITE:
        raise ValueError('SQLite persistence must be explicitly configured')
    before = check_persistence(settings)
    print(json.dumps({'phase':'before', **before.public()}))
    if upgrade:
        command.upgrade(migration_config(settings), 'head')
    after = check_persistence(settings)
    print(json.dumps({'phase':'after', **after.public()}))
    return after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upgrade', action='store_true', help='Explicitly execute Alembic upgrade head')
    args = parser.parse_args()
    try:
        result = prepare(get_settings(), upgrade=args.upgrade)
        return 0 if result.ready else 1
    except Exception:
        # Driver diagnostics can contain URLs or row values. Keep the CLI safe.
        print('Persistence preparation failed; verify operator configuration and backup.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
