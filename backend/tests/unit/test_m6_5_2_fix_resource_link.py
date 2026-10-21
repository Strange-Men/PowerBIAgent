"""Browser links are selectors; no network occurs until exact identity parses."""
import pytest
from backend.app.application.cloud_resource_link import parse_resource_link

WS='00000000-0000-0000-0000-000000000011'
ITEM='00000000-0000-0000-0000-000000000010'


@pytest.mark.parametrize('host',['app.powerbi.com','app.fabric.microsoft.com'])
@pytest.mark.parametrize('path,kind',[('reports','Report'),('datasets','SemanticModel'),('semanticmodels','SemanticModel')])
def test_exact_link(host,path,kind):
    assert parse_resource_link(f'https://{host}/groups/{WS}/{path}/{ITEM}')==(WS,ITEM,kind)


@pytest.mark.parametrize('url',[
    f'https://evil.test/groups/{WS}/reports/{ITEM}',
    f'https://app.powerbi.com.evil.test/groups/{WS}/reports/{ITEM}',
    f'https://app.powerbi.com@evil.test/groups/{WS}/reports/{ITEM}',
    f'http://app.powerbi.com/groups/{WS}/reports/{ITEM}',
    f'https://app.powerbi.com/groups/{WS}/reports/not-an-id',
    f'https://app.powerbi.com/groups/me/reports/{ITEM}',
    f'https://app.powerbi.com/groups/{WS}/reports/{ITEM}?url=https://evil.test',
    f'https://app.powerbi.com:443/groups/{WS}/reports/{ITEM}',
])
def test_invalid_selector_is_rejected(url):
    with pytest.raises(ValueError): parse_resource_link(url)
