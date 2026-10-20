"""Run local tests with repository-external cache, output and owned temp paths.

CI continues to use its existing commands. PBIAGENT_TEST_ROOT must point to an
absolute PBIAgentTest directory outside the repository.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]


def frontend_commands(command: list[str], cache: Path) -> list[list[str]]:
    """Route standard frontend validation outputs outside the checkout."""
    if command[0] not in {'npm', 'npm.cmd'}:
        return [command]
    npx = shutil.which('npx.cmd' if os.name == 'nt' else 'npx') or 'npx'
    typecheck = [[npx, 'tsc', '-p', 'tsconfig.' + name + '.json', '--incremental',
                  '--tsBuildInfoFile', str(cache / (name + '.tsbuildinfo'))]
                 for name in ('app', 'node')]
    if command[1:] == ['test']:
        return [[npx, 'vitest', 'run', '--configLoader', 'runner']]
    if command[1:] == ['run', 'typecheck']:
        return typecheck
    if command[1:] == ['run', 'build']:
        return typecheck + [[npx, 'vite', 'build', '--configLoader', 'runner']]
    return [command]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--milestone', required=True)
    parser.add_argument('--frontend', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    configured = os.environ.get('PBIAGENT_TEST_ROOT', '')
    root = Path(configured)
    if not configured or not root.is_absolute():
        parser.error('PBIAGENT_TEST_ROOT must be an absolute external directory')
    root = root.resolve()
    if root.name != 'PBIAgentTest' or root.is_relative_to(REPO) or REPO.is_relative_to(root):
        parser.error('PBIAGENT_TEST_ROOT must be a separate PBIAgentTest root')
    if not args.milestone.startswith('M') or not args.milestone.replace('.', '').isalnum():
        parser.error('invalid milestone')
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('command required')
    # Keep Windows paths short enough for descriptive pytest node names and
    # owner-scoped report storage below basetemp. Record the time in the receipt.
    run = uuid4().hex[:8]
    output = root / args.milestone / 'Acceptance' / run
    cache = root / args.milestone / 'Cache' / run
    output.mkdir(parents=True)
    cache.mkdir(parents=True)
    commands = frontend_commands(command, cache) if args.frontend else [command]
    if os.name == 'nt':
        for step in commands:
            if step[0] in {'npm', 'npx'}:
                step[0] = shutil.which(step[0] + '.cmd') or step[0] + '.cmd'
    cwd = REPO / 'frontend' if args.frontend else REPO
    record = dict(milestone=args.milestone, run=run,
                  started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  cwd=str(cwd), cache=str(cache),
                  output=str(output / 'output.txt'), exit_code=None, temp_cleanup=False)
    try:
        with tempfile.TemporaryDirectory(prefix='T-', dir=cache) as task_temp:
            temp = Path(task_temp)
            options = shlex.join(['-o', 'cache_dir=' + cache.as_posix(),
                                  '--basetemp=' + (temp / 'pytest').as_posix()])
            env = os.environ.copy()
            env.update(PBIAGENT_TEST_ROOT=str(root), PBIAGENT_VALIDATION_MILESTONE=args.milestone, TEMP=str(temp), TMP=str(temp),
                       PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1',
                       PYTHONDONTWRITEBYTECODE='1',
                       PBIAGENT_VALIDATION_CACHE=str(cache / 'vite'),
                       PBIAGENT_VALIDATION_OUTPUT=str(output / 'dist'),
                       npm_config_cache=str(cache / 'npm'),
                       PYTEST_ADDOPTS=options, PBI_SYNTHETIC_PYTHON=sys.executable)
            with (output / 'output.txt').open('w', encoding='utf-8') as log:
                for step in commands:
                    result = subprocess.run(step, cwd=cwd, env=env, stdout=log,
                                            stderr=subprocess.STDOUT)
                    if result.returncode:
                        break
            record['exit_code'] = result.returncode
        record['temp_cleanup'] = not temp.exists()
    finally:
        (output / 'receipt.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        print(json.dumps(record), flush=True)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
