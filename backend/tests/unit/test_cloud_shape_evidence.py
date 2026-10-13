"""Eight existing shapes cannot promote unknown IQ completeness."""
import pytest
from backend.app.schemas.data_contracts import DAXRequest,QueryShape
from backend.app.powerbi.fabric_iq_normalization import normalize_query
from backend.tests.unit.test_fabric_iq_adapter import result,MODEL

SHAPE_DAX={
    QueryShape.SCALAR:'EVALUATE ROW("probe", COUNTROWS(Facts))',
    QueryShape.ENTITY_LIST:'EVALUATE SELECTCOLUMNS(Facts,"probe",Facts[Key])',
    QueryShape.GROUPED:'EVALUATE SUMMARIZECOLUMNS(Facts[Category],"probe",COUNTROWS(Facts))',
    QueryShape.RANKING:'EVALUATE TOPN(3,SUMMARIZECOLUMNS(Facts[Category],"probe",COUNTROWS(Facts)),[probe],DESC)',
    QueryShape.MEMBER_SET:'EVALUATE SELECTCOLUMNS(DISTINCT(Facts[Category]),"probe",Facts[Category])',
    QueryShape.FILTERED_AGGREGATION:'EVALUATE ROW("probe",CALCULATE(COUNTROWS(Facts),Facts[Category]="Synthetic"))',
    QueryShape.TREND:'EVALUATE SUMMARIZECOLUMNS(Facts[Month],"probe",COUNTROWS(Facts))',
    QueryShape.BOUNDED_TREND:'EVALUATE SUMMARIZECOLUMNS(Facts[Month],FILTER(Facts,Facts[Month]>=1&&Facts[Month]<=3),"probe",COUNTROWS(Facts))',
}


@pytest.mark.parametrize('shape',list(QueryShape))
@pytest.mark.parametrize('signal',[{}, {'complete':True}, {'truncated':False}, {'totalRows':1}])
def test_all_existing_shapes_retain_unknown_completeness(shape,signal):
    # Algebraic boundedness and maxRows are not response completeness evidence.
    normalized=normalize_query(result(**signal),MODEL,DAXRequest(semantic_model_key='synthetic',
        dax=SHAPE_DAX[shape],max_rows=10))
    assert normalized.truncated


@pytest.mark.parametrize('value',['1','9007199254740993',True,1.0])
def test_int64_contract_remains_strict(value):
    from backend.app.powerbi.base import PowerBIAdapterError
    raw=result(rows=[[value]])
    with pytest.raises(PowerBIAdapterError,match='CONTRACT_DRIFT'):
        normalize_query(raw,MODEL,DAXRequest(semantic_model_key='synthetic',dax='EVALUATE ROW("probe",1)'))
