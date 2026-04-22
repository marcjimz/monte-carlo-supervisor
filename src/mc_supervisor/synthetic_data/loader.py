"""Load pre-generated CSV files into Unity Catalog tables via Spark.

Usage from a Databricks notebook:
    from mc_supervisor.synthetic_data.loader import load_all_tables
    load_all_tables(spark, catalog="my_catalog", schema="hospital_data", data_dir="/Users/me/project/data")
"""

from __future__ import annotations

import io

import pandas as pd
from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DateType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

# ---------------------------------------------------------------------------
# Schema definitions for each CSV (ensures correct types on load)
# ---------------------------------------------------------------------------

_SCHEMAS: dict[str, StructType] = {
    "patients": StructType(
        [
            StructField("patient_id", StringType(), False),
            StructField("first_name", StringType()),
            StructField("last_name", StringType()),
            StructField("date_of_birth", DateType()),
            StructField("gender", StringType()),
            StructField("zip_code", StringType()),
            StructField("insurance_type", StringType()),
            StructField("chronic_conditions", StringType()),
            StructField("num_chronic", IntegerType()),
        ]
    ),
    "facilities": StructType(
        [
            StructField("facility_id", StringType(), False),
            StructField("facility_name", StringType()),
            StructField("facility_type", StringType()),
            StructField("bed_count", IntegerType()),
            StructField("address", StringType()),
            StructField("city", StringType()),
            StructField("state", StringType()),
        ]
    ),
    "providers": StructType(
        [
            StructField("provider_id", StringType(), False),
            StructField("first_name", StringType()),
            StructField("last_name", StringType()),
            StructField("specialty", StringType()),
            StructField("npi", StringType()),
            StructField("facility_id", StringType()),
        ]
    ),
    "encounters": StructType(
        [
            StructField("encounter_id", StringType(), False),
            StructField("patient_id", StringType()),
            StructField("provider_id", StringType()),
            StructField("facility_id", StringType()),
            StructField("encounter_type", StringType()),
            StructField("department", StringType()),
            StructField("admission_date", DateType()),
            StructField("discharge_date", DateType()),
            StructField("length_of_stay", IntegerType()),
        ]
    ),
    "diagnoses": StructType(
        [
            StructField("diagnosis_id", StringType(), False),
            StructField("encounter_id", StringType()),
            StructField("icd10_code", StringType()),
            StructField("description", StringType()),
            StructField("is_primary", IntegerType()),
            StructField("sequence_num", IntegerType()),
        ]
    ),
    "procedures": StructType(
        [
            StructField("procedure_id", StringType(), False),
            StructField("encounter_id", StringType()),
            StructField("cpt_code", StringType()),
            StructField("description", StringType()),
            StructField("procedure_date", DateType()),
            StructField("provider_id", StringType()),
        ]
    ),
    "billing": StructType(
        [
            StructField("billing_id", StringType(), False),
            StructField("encounter_id", StringType()),
            StructField("total_charges", DoubleType()),
            StructField("payer_id", StringType()),
            StructField("allowed_amount", DoubleType()),
            StructField("paid_amount", DoubleType()),
            StructField("patient_responsibility", DoubleType()),
            StructField("claim_status", StringType()),
            StructField("payment_date", DateType()),
        ]
    ),
    "readmissions": StructType(
        [
            StructField("readmission_id", StringType(), False),
            StructField("original_encounter_id", StringType()),
            StructField("readmit_encounter_id", StringType()),
            StructField("days_between", IntegerType()),
            StructField("is_30_day", IntegerType()),
        ]
    ),
    "icd10_codes": StructType(
        [
            StructField("icd10_code", StringType(), False),
            StructField("description", StringType()),
            StructField("category", StringType()),
        ]
    ),
    "cpt_codes": StructType(
        [
            StructField("cpt_code", StringType(), False),
            StructField("description", StringType()),
            StructField("category", StringType()),
            StructField("fee_low", DoubleType()),
            StructField("fee_high", DoubleType()),
        ]
    ),
    "payers": StructType(
        [
            StructField("payer_id", StringType(), False),
            StructField("payer_name", StringType()),
            StructField("payer_type", StringType()),
            StructField("avg_reimbursement_rate", DoubleType()),
        ]
    ),
    "departments": StructType(
        [
            StructField("department_id", StringType(), False),
            StructField("department_name", StringType()),
        ]
    ),
}

# Order matters — dimension/reference tables first, then facts
_LOAD_ORDER = [
    "icd10_codes",
    "cpt_codes",
    "payers",
    "departments",
    "patients",
    "facilities",
    "providers",
    "encounters",
    "diagnoses",
    "procedures",
    "billing",
    "readmissions",
]


def _workspace_path(data_dir: str) -> str:
    """Normalise a workspace path for the SDK (strip /Workspace prefix)."""
    s = str(data_dir)
    if s.startswith("/Workspace"):
        s = s[len("/Workspace"):]
    return s


def load_csv_to_table(
    spark: SparkSession,
    table_name: str,
    catalog: str,
    schema: str,
    data_dir: str,
    mode: str = "overwrite",
) -> int:
    """Load a single CSV file into a Unity Catalog Delta table.

    Downloads the CSV via the Workspace REST API (no FUSE dependency),
    parses it with pandas, converts to a Spark DataFrame, and writes
    to a Delta table.

    Parameters
    ----------
    spark : SparkSession
        Active Spark session.
    table_name : str
        Name of the table (must match a key in ``_SCHEMAS`` and a CSV
        filename under *data_dir*).
    catalog : str
        Unity Catalog catalog name.
    schema : str
        Unity Catalog schema name.
    data_dir : str
        Workspace path to the directory containing CSV files,
        e.g. ``/Workspace/Users/me/project/data`` or ``/Users/me/project/data``.
    mode : str
        Spark write mode (default ``"overwrite"``).

    Returns
    -------
    int
        Number of rows loaded.
    """
    from pyspark.sql.functions import col

    ws_dir = _workspace_path(data_dir)
    csv_ws_path = f"{ws_dir}/{table_name}.csv"

    # Download CSV bytes via REST API — works reliably on serverless
    w = WorkspaceClient()
    with w.workspace.download(csv_ws_path) as f:
        raw = f.read()

    pdf = pd.read_csv(io.BytesIO(raw))

    # Create Spark DataFrame, then cast columns to match the target schema
    df = spark.createDataFrame(pdf)
    table_schema = _SCHEMAS.get(table_name)
    if table_schema:
        for field in table_schema:
            if field.name in df.columns:
                df = df.withColumn(field.name, col(field.name).cast(field.dataType))

    full_table = f"{catalog}.{schema}.{table_name}"
    df.write.format("delta").mode(mode).saveAsTable(full_table)

    count = df.count()
    print(f"  Loaded {count:>8,} rows -> {full_table}")
    return count


def load_all_tables(
    spark: SparkSession,
    catalog: str,
    schema: str,
    data_dir: str,
    mode: str = "overwrite",
) -> dict[str, int]:
    """Load all CSV files into Unity Catalog tables.

    Returns a dict mapping table names to row counts.
    """
    print(f"Loading CSVs from {data_dir} -> {catalog}.{schema}\n")

    # List files in the workspace directory to know which CSVs exist
    ws_dir = _workspace_path(data_dir)
    w = WorkspaceClient()
    try:
        available = {obj.path.rsplit("/", 1)[-1] for obj in w.workspace.list(ws_dir)}
    except Exception:
        available = set()

    results: dict[str, int] = {}
    for table_name in _LOAD_ORDER:
        csv_name = f"{table_name}.csv"
        if csv_name in available:
            results[table_name] = load_csv_to_table(
                spark, table_name, catalog, schema, data_dir, mode
            )
        else:
            print(f"  SKIP {table_name} (no CSV found)")

    total = sum(results.values())
    print(f"\nLoaded {len(results)} tables, {total:,} total rows.")
    return results
