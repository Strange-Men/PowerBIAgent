"""Registered KPI requirements retain their identities with numeric schema types."""
import pytest

from backend.app.report.capability import compute_section_capabilities, SectionKey
from backend.app.report.contracts import ReportContractValidator
from backend.app.schemas.data_contracts import SemanticModelSchema, TableSchema, MeasureSchema


def schema(kind):
    return SemanticModelSchema(key='local_desktop_model', name='Synthetic sales', tables=[TableSchema(
        name='Sales', measures=[MeasureSchema(name=name, data_type=kind) for name in
            ('Total Sales', 'Total Quantity', 'Total Orders', 'Average Order Value')])])


@pytest.mark.parametrize('kind', ['Double', 'Int64', 'Decimal', 'Integer'])
def test_registered_numeric_kpis_accept_exact_numeric_schema_types(kind):
    model = schema(kind)
    contract = ReportContractValidator().validate('sales_report', model).contract
    capabilities = compute_section_capabilities('sales_report', contract, model)
    assert all(capabilities[key].available for key in (
        SectionKey.SALES_KPI, SectionKey.QUANTITY_KPI,
        SectionKey.ORDERS_KPI, SectionKey.AOV_KPI))
    assert not capabilities[SectionKey.CATEGORY_CONTRIBUTION].available


@pytest.mark.parametrize('kind', ['String', 'Boolean', 'Unknown', None])
def test_nonnumeric_or_unknown_types_never_make_kpi_eligible(kind):
    model = schema(kind)
    contract = ReportContractValidator().validate('sales_report', model).contract
    capabilities = compute_section_capabilities('sales_report', contract, model)
    assert not any(item.available for item in capabilities.values())


def test_numeric_type_does_not_authorize_another_measure_identity():
    model = schema('Decimal')
    model.tables[0].measures[0].name = 'Other Revenue'
    contract = ReportContractValidator().validate('sales_report', model).contract
    assert not compute_section_capabilities('sales_report', contract, model)[SectionKey.SALES_KPI].available
