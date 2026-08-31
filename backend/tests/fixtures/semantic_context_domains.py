"""Structurally different runtime-only models; no production language bindings."""

from dataclasses import dataclass

from backend.app.schemas.data_contracts import (
    ColumnSchema as C, MeasureSchema as M, RelationshipSchema as R,
    SemanticModelSchema as S, TableSchema as T,
)


@dataclass
class Domain:
    schema: S
    measure: str
    measure_text: str
    dimension: str
    dimension_table: str
    dimension_text: str
    month: str
    month_table: str


def domains():
    sales = S(name="Retail", key="retail-zero", tables=[
        T(name="Transactions", columns=[C(name="AreaId", data_type="Int64"), C(name="PlacedAt", data_type="DateTime")], measures=[M(name="NetRevenue", display_name="净营收")]),
        T(name="Areas", columns=[C(name="Id", data_type="Int64"), C(name="AreaName", data_type="String", description="经营分区")]),
        T(name="FiscalCalendar", columns=[C(name="Day", data_type="DateTime", is_key=True), C(name="MonthStart", data_type="DateTime", expression="DATE(YEAR([Day]),MONTH([Day]),1)")]),
    ], relationships=[R(from_table="Transactions", from_column="AreaId", to_table="Areas", to_column="Id"), R(from_table="Transactions", from_column="PlacedAt", to_table="FiscalCalendar", to_column="Day", to_cardinality="One")])
    education = S(name="Education", key="education-zero", tables=[
        T(name="Completions", columns=[C(name="ClassKey", data_type="Int64"), C(name="CompletedAt", data_type="DateTime")], measures=[M(name="PassRatio", description="课程通过率", format_string="0.0%")]),
        T(name="Classes", columns=[C(name="Key", data_type="Int64"), C(name="ProgramKey", data_type="Int64")]),
        T(name="Programs", columns=[C(name="Key", data_type="Int64"), C(name="ProgramTitle", data_type="String", display_name="学习项目")]),
        T(name="AcademicCalendar", columns=[C(name="AcademicDay", data_type="DateTime", is_key=True), C(name="AcademicMonth", data_type="DateTime", expression="DATE(YEAR([AcademicDay]),MONTH([AcademicDay]),1)")]),
    ], relationships=[R(from_table="Completions", from_column="ClassKey", to_table="Classes", to_column="Key"), R(from_table="Classes", from_column="ProgramKey", to_table="Programs", to_column="Key"), R(from_table="Completions", from_column="CompletedAt", to_table="AcademicCalendar", to_column="AcademicDay", to_cardinality="One")])
    inventory = S(name="Operations", key="operations-zero", tables=[
        T(name="Balances", columns=[C(name="Bin", data_type="String", description="存储库位"), C(name="CapturedAt", data_type="DateTime"), C(name="ArrivedAt", data_type="DateTime"), C(name="CaptureMonth", data_type="DateTime", expression="DATE(YEAR([CapturedAt]),MONTH([CapturedAt]),1)")], measures=[M(name="OnHandUnits", display_name="在库件数"), M(name="ReservedUnits", display_name="预留件数")]),
    ])
    unknown = S(name="Unregistered", key="opaque-holdout-q83", tables=[
        T(name="Observations", columns=[C(name="ObservationId", data_type="Int64"), C(name="StationCode", data_type="String", display_name="观测站"), C(name="ObservedOn", data_type="DateTime"), C(name="MonthNode", data_type="DateTime", expression="DATE(YEAR([ObservedOn]),MONTH([ObservedOn]),1)")]),
        T(name="Metrics", columns=[C(name="ObservationId", data_type="Int64")], measures=[M(name="ExposureSeconds", description="有效曝光时长")]),
        T(name="Internal", is_system_managed=True, columns=[C(name="StationCode", data_type="String")]),
    ], relationships=[R(from_table="Metrics", from_column="ObservationId", to_table="Observations", to_column="ObservationId", from_cardinality="Many", to_cardinality="One")])
    return [Domain(sales, "NetRevenue", "净营收", "AreaName", "Areas", "经营分区", "MonthStart", "FiscalCalendar"),
            Domain(education, "PassRatio", "课程通过率", "ProgramTitle", "Programs", "学习项目", "AcademicMonth", "AcademicCalendar"),
            Domain(inventory, "OnHandUnits", "在库件数", "Bin", "Balances", "存储库位", "CaptureMonth", "Balances"),
            Domain(unknown, "ExposureSeconds", "有效曝光时长", "StationCode", "Observations", "观测站", "MonthNode", "Observations")]
