"""Cloud primitive types do not grant temporal grouping authority."""
import pytest
from backend.app.query_plan.semantic_catalog import SemanticCatalogBuilder
from backend.app.query_plan.completeness import CanonicalShapeCompletenessGate, CanonicalShapeCompletenessError
from backend.app.schemas.data_contracts import (
    SemanticModelSchema, TableSchema, ColumnSchema, MeasureSchema, CanonicalQueryPlan, QueryShape,
)


@pytest.mark.parametrize('field,type_name', [('FiscalYear','Integer'), ('PeriodStart','DateTime')])
def test_unproved_cloud_temporal_grain_stays_closed(field, type_name):
    schema=SemanticModelSchema(name='Synthetic',key='model',metadata_source='fabric_iq',
        tables=[TableSchema(name='Events',columns=[ColumnSchema(name=field,data_type=type_name,
            expression=None,description=None,format_string='0' if type_name=='Integer' else 'D')],
            measures=[MeasureSchema(name='Metric',data_type='Decimal')])])
    catalog=SemanticCatalogBuilder().build(schema)
    assert all(obj.temporal_grouping is None for obj in catalog.objects)
    plan=CanonicalQueryPlan(normalized_question='synthetic trend',semantic_model_key='model',
        query_shape=QueryShape.TREND,measures=['Metric'],dimensions=[field],dimension_order='asc',
        dimension_tables={field:'Events'})
    with pytest.raises(CanonicalShapeCompletenessError,match='canonical_shape_trend_temporal_dimension_required'):
        CanonicalShapeCompletenessGate().validate(plan,catalog=catalog)
