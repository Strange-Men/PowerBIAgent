"""Stdio-only Synthetic host for the real React fetch/client integration test.

No listening socket, real identity, external LLM or Fabric request. Reuses the
same offline factual fixture as the API E2E. Only synthetic public API output
crosses stdout. Temp artifacts are owned by this test, outside the repository.
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))

from backend.tests.api.test_cloud_factual_e2e import factual_product


def main():
    root = Path('D:/AAA_Workfile/PBIAgentTest')
    with tempfile.TemporaryDirectory(prefix='m64-synthetic-ui-',dir=root if root.is_dir() else None) as folder:
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
