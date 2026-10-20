"""Stdio-only Synthetic host for the real React fetch/client integration test.

No listening socket, real identity, external LLM or Fabric request. Reuses the
same offline factual fixture as the API E2E. Only synthetic public API output
crosses stdout. Temp artifacts are owned by this test, outside the repository.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))

from backend.tests.api.test_cloud_factual_e2e import factual_product


def main():
    configured_root = os.environ.get('PBIAGENT_TEST_ROOT')
    root = Path(configured_root) / os.environ.get('PBIAGENT_VALIDATION_MILESTONE','M6.5.1') / 'Acceptance' if configured_root else None
    if root is not None:
        root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='synthetic-ui-',dir=root) as folder:
        patch = pytest.MonkeyPatch()
        fixture = factual_product.__wrapped__(Path(folder),patch)
        try:
            client,app,headers,selection,identity,facts,llm,results = next(fixture)
            print(json.dumps({'ready':True,'session':client.get('/auth/session').json()}),flush=True)
            for line in sys.stdin:
                command = json.loads(line)
                if command.get('close'): break
                response = client.request(command['method'],command['path'],
                    headers=command.get('headers'),content=command.get('body'))
                print(json.dumps({'id':command['id'],'status':response.status_code,
                    'body':response.text,'headers':dict(response.headers)}),flush=True)
        finally:
            fixture.close()
            patch.undo()


if __name__=='__main__': main()
