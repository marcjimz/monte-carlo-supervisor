"""Load pre-generated CSV files into Unity Catalog tables via Spark.

Usage from a Databricks notebook:
    from src.databricks.synthetic_data.loader import load_all_tables
    load_all_tables(spark, catalog="monte_carlo_sim", schema="hospital_data")
"""

from __future__ import annotations

import pathlib

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DateType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

# Root of the repo — CSVs live in <repo>/data/
# loader.py is at src/databricks/synthetic_data/loader.py → parents[3] = project root
# Note: avoid .resolve() — workspace filesystem paths (/Workspace/...) are not
# real POSIX paths and resolve() can break on serverless compute.
_DEFAULT_DATA_DIR = pathlib.Path(__file__).parents[3] / "data"

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


def load_csv_to_table(
    spark: SparkSession,
    table_name: str,
    catalog: str,
    schema: str,
    data_dir: str | pathlib.Path | None = None,
    mode: str = "overwrite",
) -> int:
    """Load a single CSV file into a Unity Catalog Delta table.

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
    data_dir : str or Path, optional
        Directory containing the CSV files.  Defaults to ``<repo>/data/``.
    mode : str
        Spark write mode (default ``"overwrite"``).

    Returns
    -------
    int
        Number of rows loaded.
    """
    import pandas as pd

    data_dir = pathlib.Path(data_dir) if data_dir else _DEFAULT_DATA_DIR
    csv_path = data_dir / f"{table_name}.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    # Read via pandas to avoid Spark file-URI issues on serverless compute
    # (@ in workspace email paths breaks Spark's file: URI parser).
    # Create DataFrame without schema first (natural Arrow mapping), then
    # cast columns to the target types using Spark's cast() which handles
    # string-to-date, int-to-string, etc. gracefully.
    from pyspark.sql.functions import col

    pdf = pd.read_csv(str(csv_path))
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
    data_dir: str | pathlib.Path | None = None,
    mode: str = "overwrite",
) -> dict[str, int]:
    """Load all CSV files into Unity Catalog tables.

    Returns a dict mapping table names to row counts.
    """
    data_dir = pathlib.Path(data_dir) if data_dir else _DEFAULT_DATA_DIR
    print(f"Loading CSVs from {data_dir} -> {catalog}.{schema}\n")

    results: dict[str, int] = {}
    for table_name in _LOAD_ORDER:
        csv_path = data_dir / f"{table_name}.csv"
        if csv_path.exists():
            results[table_name] = load_csv_to_table(
                spark, table_name, catalog, schema, data_dir, mode
            )
        else:
            print(f"  SKIP {table_name} (no CSV found)")

    total = sum(results.values())
    print(f"\nLoaded {len(results)} tables, {total:,} total rows.")
    return results
