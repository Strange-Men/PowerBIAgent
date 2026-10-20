"""Gate mutation tests prevent a vacuous resource-completeness claim."""
from scripts.check_localization_completeness import compare,load,run_checks
import pytest


def test_resource_contract_and_real_catalogs():
    assert run_checks()==[]
    assert compare({'greeting':'你好 {name}'},{'greeting':'Hello {name}'})==[]
    assert compare({'count':'{{count}} 项'},{'count':'{{total}} items'},frontend=True)
    assert compare({'one':'一'},{'other':'Other'})


def test_duplicate_key_and_non_utf8_fail_closed(tmp_path):
    path=tmp_path/'duplicate.json'
    path.write_text('{"retry":"a","retry":"b"}',encoding='utf-8')
    with pytest.raises(ValueError,match='duplicate_key'):load(path)
    path.write_bytes(b'\xff\xfe')
    with pytest.raises(UnicodeError):load(path)
