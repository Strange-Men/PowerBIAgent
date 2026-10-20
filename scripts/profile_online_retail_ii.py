"""Offline public-data profile and independent oracle; never a product authority.

Run with the bundled spreadsheet Python through run_local_validation.py.
All downloaded data and outputs must be below PBIAgentTest/M6.5.
No row deletion, deduplication, imputation, or model publication is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from decimal import Decimal
from pathlib import Path
import urllib.request
import zipfile


SOURCE = "https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip"
HEADERS = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate",
           "Price", "Customer ID", "Country"]
SCALE = 10000
CONTRACT = "M6.5-DRAFT-GROSS-POSITIVE-v1"


def external_path(value: str) -> Path:
    path = Path(value).resolve()
    repo = Path(__file__).resolve().parents[1]
    if path.is_relative_to(repo) or not any(
        a.name == "M6.5" and a.parent.name == "PBIAgentTest" for a in (path, *path.parents)
    ):
        raise ValueError("output/input must be under external PBIAgentTest/M6.5")
    return path


def price_units(value) -> int:
    number = Decimal(str(value))
    scaled = number * SCALE
    if not number.is_finite() or scaled != scaled.to_integral_value():
        raise ValueError("price cannot be represented exactly at scale 4")
    return int(scaled)


def amount(units: int) -> str:
    return format(Decimal(int(units)) / SCALE, ".4f")


def identifier(value) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, (int, float)):
        number = Decimal(str(value))
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError("nonintegral identifier")
        return str(int(number))
    return str(value)


def download(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "online_retail_ii.zip"
    if not archive.exists():
        with urllib.request.urlopen(SOURCE, timeout=120) as response, archive.open("xb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    with zipfile.ZipFile(archive) as zipped:
        members = [n for n in zipped.namelist() if n.lower().endswith(".xlsx")]
        if len(members) != 1:
            raise ValueError("expected one workbook")
        workbook = root / "online_retail_II.xlsx"
        content = zipped.read(members[0])  # CRC checked; no extractall/path traversal.
        if workbook.exists() and hashlib.sha256(workbook.read_bytes()).digest() != hashlib.sha256(content).digest():
            raise ValueError("existing workbook differs; preserve and investigate")
        if not workbook.exists():
            workbook.write_bytes(content)
    return workbook


def profile(workbook: Path, output: Path) -> dict:
    import numpy as np
    import pandas as pd

    frames, sheets = [], []
    source_bytes = workbook.read_bytes()
    # An immutable read snapshot prevents a concurrent external download from
    # silently mixing workbook versions during a long profile run.
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as source_zip:
        if source_zip.testzip() is not None:
            raise ValueError("invalid workbook CRC")
    excel = pd.ExcelFile(io.BytesIO(source_bytes), engine="openpyxl")
    for name in excel.sheet_names:
        frame = pd.read_excel(excel, sheet_name=name, dtype={"Invoice": object,
            "StockCode": object, "Customer ID": object}, keep_default_na=False)
        if list(frame.columns) != HEADERS:
            raise ValueError("unexpected source headers")
        sheets.append({"name": name, "rows": len(frame), "headers": list(frame.columns)})
        frames.append(frame)
        print(json.dumps({"sheet_profiled": name, "rows": len(frame)}), flush=True)
    excel.close()
    raw = pd.concat(frames, ignore_index=True)
    missing = {c: int((raw[c].isna() | raw[c].eq("")).sum()) for c in HEADERS}
    duplicate_excess = int(raw.duplicated(subset=HEADERS).sum())
    duplicate_rows = int(raw.duplicated(subset=HEADERS, keep=False).sum())
    raw["Invoice"] = raw["Invoice"].map(identifier)
    raw["StockCode"] = raw["StockCode"].map(identifier)
    raw["Customer ID"] = raw["Customer ID"].map(identifier)
    if raw["Invoice"].isna().any() or raw["StockCode"].isna().any():
        raise ValueError("missing source invoice/product")
    quantity = pd.to_numeric(raw["Quantity"], errors="raise")
    if not np.isfinite(quantity).all() or (quantity != np.trunc(quantity)).any():
        raise ValueError("invalid quantity")
    raw["Quantity"] = quantity.astype("int64")
    raw["PriceUnits"] = raw["Price"].map(price_units).astype("int64")
    # Python integer bound check before vector arithmetic or aggregation.
    bound = int(raw["Quantity"].abs().max()) * int(raw["PriceUnits"].abs().max())
    if bound > np.iinfo(np.int64).max:
        raise ValueError("potential signed integer overflow")
    raw["AmountUnits"] = raw["Quantity"] * raw["PriceUnits"]
    if sum(abs(int(v)) for v in raw["AmountUnits"]) > np.iinfo(np.int64).max:
        raise ValueError("potential aggregate signed integer overflow")
    raw["InvoiceDate"] = pd.to_datetime(raw["InvoiceDate"], errors="raise")
    if raw["InvoiceDate"].isna().any():
        raise ValueError("missing timestamp")
    raw["Month"] = raw["InvoiceDate"].dt.strftime("%Y-%m")
    cancelled = raw["Invoice"].str.upper().str.startswith("C")
    eligible = ~cancelled & raw["Quantity"].gt(0) & raw["PriceUnits"].gt(0)
    sales = raw.loc[eligible]
    def metric(frame):
        units = int(frame["AmountUnits"].sum())
        orders = int(frame["Invoice"].nunique())
        return {"Total Sales": amount(units), "Total Quantity": int(frame["Quantity"].sum()),
            "Total Orders": orders, "Unique Customers": int(frame["Customer ID"].nunique()),
            "Average Order Value": str(Decimal(units) / SCALE / orders) if orders else None}
    def groups(frame, field):
        values = frame.groupby(field, dropna=False)["AmountUnits"].sum()
        return [{field: str(key), "Total Sales": amount(int(value))} for key, value in values.items()]
    country_groups = groups(sales, "Country")
    country_rank = sorted(country_groups, key=lambda r: (-Decimal(r["Total Sales"]), r["Country"]))
    products = sales.groupby("StockCode")["Quantity"].sum()
    product_rank = sorted([{"StockCode": str(k), "Total Quantity": int(v)} for k, v in products.items()],
                          key=lambda r: (-r["Total Quantity"], r["StockCode"]))
    months = groups(sales, "Month")
    countries = sorted(str(x) for x in raw["Country"].unique())
    subset = ["United Kingdom", "France", "Germany"]
    if not set(subset).issubset(countries):
        raise ValueError("candidate countries absent; regenerate corpus")
    first, last = raw["InvoiceDate"].min(), raw["InvoiceDate"].max()
    summary = {
        "contract": CONTRACT, "status": "OFFLINE_ORACLE_ONLY_CLOUD_NOT_RUN",
        "source_url": SOURCE, "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_bytes": len(source_bytes), "sheets": sheets, "row_count": len(raw),
        "missing": missing, "duplicate_excess_preserved": duplicate_excess,
        "duplicate_participating_rows": duplicate_rows,
        "invoice_timestamp_min": first.isoformat(), "invoice_timestamp_max": last.isoformat(),
        "timezone": "UNDECLARED", "currency": "GBP", "countries": countries,
        "country_count": len(countries), "product_count": int(raw["StockCode"].nunique()),
        "source_customer_count": int(raw["Customer ID"].nunique()),
        "cancelled_rows": int(cancelled.sum()), "cancelled_orders": int(raw.loc[cancelled,"Invoice"].nunique()),
        "cancelled_positive_quantity_rows": int((cancelled & raw["Quantity"].gt(0)).sum()),
        "negative_quantity_rows": int(raw["Quantity"].lt(0).sum()),
        "noncancelled_negative_quantity_rows": int((~cancelled & raw["Quantity"].lt(0)).sum()),
        "zero_quantity_rows": int(raw["Quantity"].eq(0).sum()),
        "zero_price_rows": int(raw["PriceUnits"].eq(0).sum()),
        "negative_price_rows": int(raw["PriceUnits"].lt(0).sum()),
        "fractional_price_beyond_2dp_rows": int((raw["PriceUnits"] % 100 != 0).sum()),
        "eligible_sale_rows": len(sales), "excluded_sale_rows": len(raw)-len(sales),
        "raw_signed_amount": amount(int(raw["AmountUnits"].sum())),
        "excluded_signed_amount": amount(int(raw.loc[~eligible,"AmountUnits"].sum())),
        "cancelled_signed_amount_positive_price": amount(int(raw.loc[cancelled & raw["PriceUnits"].gt(0),"AmountUnits"].sum())),
        "stockcodes_multiple_descriptions": int((raw.groupby("StockCode")["Description"].nunique()>1).sum()),
        "invoices_multiple_countries": int((raw.groupby("Invoice")["Country"].nunique()>1).sum()),
        "invoices_multiple_customers": int((raw.groupby("Invoice")["Customer ID"].nunique()>1).sum()),
        "offline_expected": {"all": metric(sales), "by_country": country_groups,
            "top5_country": country_rank[:5], "top10_product_quantity": product_rank[:10],
            "member_set": [r for r in country_groups if r["Country"] in subset],
            "member_set_aggregate": metric(sales[sales["Country"].isin(subset)]),
            "by_month": months,
            "2011_Jan_Jun": metric(sales[(sales["InvoiceDate"]>=pd.Timestamp("2011-01-01")) &
                                            (sales["InvoiceDate"]<pd.Timestamp("2011-07-01"))]),
            "france_2011_Jan_Jun": metric(sales[(sales["Country"]=="France") &
                (sales["InvoiceDate"]>=pd.Timestamp("2011-01-01")) & (sales["InvoiceDate"]<pd.Timestamp("2011-07-01"))])},
    }
    # Orthogonal Decimal loop reconciles amount eligibility and aggregation.
    independent = sum((Decimal(str(p)) * int(q) for inv,q,p in
        raw[["Invoice","Quantity","Price"]].itertuples(index=False, name=None)
        if not inv.upper().startswith("C") and int(q)>0 and Decimal(str(p))>0), Decimal(0))
    if independent != Decimal(summary["offline_expected"]["all"]["Total Sales"]):
        raise ValueError("independent Decimal reconciliation failed")
    summary["decimal_reconciliation"] = "PASS"
    output.mkdir(parents=True, exist_ok=True)
    target = output / "profile-oracle.json"
    if target.exists():
        raise ValueError("fresh run directory required; preserve existing evidence")
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"row_count": len(raw), "sha256": summary["source_sha256"],
        "output": str(target), "decimal_reconciliation": "PASS"}), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    root, output = external_path(args.dataset_dir), external_path(args.output_dir)
    workbook = download(root) if args.download else root / "online_retail_II.xlsx"
    profile(workbook, output)


if __name__ == "__main__":
    main()
