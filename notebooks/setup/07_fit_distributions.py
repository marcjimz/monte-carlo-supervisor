# Databricks notebook source
# MAGIC %md
# MAGIC # Setup Step 7: Fit Distributions from Historical Data
# MAGIC
# MAGIC Reads historical encounter and billing data, fits statistical distributions
# MAGIC for each simulation type's required distributions, and writes the fitted
# MAGIC specs to the `distribution_specs` table with an incremented version.

# COMMAND ----------

dbutils.widgets.text("catalog", "lakebase_hls_workshop_catalog", "Unity Catalog Name")
dbutils.widgets.text("schema", "hospital_data", "Schema Name")

# COMMAND ----------

# Add bundle root to sys.path so `src` package is importable
import sys
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = "/Workspace" + "/".join(_nb.split("/")[:-3])
if _root not in sys.path:
    sys.path.insert(0, _root)

# COMMAND ----------

import json
from datetime import datetime, timezone

import numpy as np

from src.databricks.monte_carlo import config_loader
from src.databricks.monte_carlo.fitting import fit_distribution
from src.databricks.monte_carlo.results import get_latest_distribution_version

# COMMAND ----------

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Catalog/Schema: {catalog}.{schema}")

# COMMAND ----------

# ---------- Step 1: Determine next version ----------

# Find the max version across all simulation types
all_types = config_loader.get_valid_types()
max_version = 0
for sim_type in all_types:
    v = get_latest_distribution_version(spark, catalog, schema, sim_type)
    if v is not None and v > max_version:
        max_version = v

next_version = max_version + 1
print(f"Current max version: {max_version}, fitting version: {next_version}")

# COMMAND ----------

# ---------- Step 2: Define fitting queries ----------
#
# Each entry maps (simulation_type, distribution_name) to:
#   - query: SQL to extract raw data from historical tables
#   - dist_type: which distribution family to fit
#   - column: which column in the query result contains the values

FITTING_SOURCES = {
    ("patient_volume", "encounter_volume"): {
        "query": f"""
            SELECT COUNT(*) AS monthly_encounters
            FROM {catalog}.{schema}.encounters
            GROUP BY YEAR(admission_date), MONTH(admission_date)
        """,
        "column": "monthly_encounters",
        "dist_type": "normal",
    },
    ("revenue", "gross_charges"): {
        "query": f"""
            SELECT SUM(b.total_charges) AS monthly_charges
            FROM {catalog}.{schema}.encounters e
            JOIN {catalog}.{schema}.billing b ON e.encounter_id = b.encounter_id
            GROUP BY YEAR(e.admission_date), MONTH(e.admission_date)
        """,
        "column": "monthly_charges",
        "dist_type": "normal",
    },
    ("revenue", "denial_rate"): {
        "query": f"""
            SELECT
                CASE WHEN p.payer_name LIKE '%Self%' THEN 0.15
                     WHEN p.payer_name = 'Medicaid' THEN 0.12
                     ELSE 0.06 END AS denial_rate
            FROM {catalog}.{schema}.billing b
            JOIN {catalog}.{schema}.payers p ON b.payer_id = p.payer_id
        """,
        "column": "denial_rate",
        "dist_type": "beta",
    },
    ("cost_comparison", "inperson_cost"): {
        # All synthetic encounters are in-person (100% baseline)
        "query": f"""
            SELECT b.total_charges AS cost
            FROM {catalog}.{schema}.encounters e
            JOIN {catalog}.{schema}.billing b ON e.encounter_id = b.encounter_id
            WHERE b.total_charges > 0
        """,
        "column": "cost",
        "dist_type": "lognormal",
    },
    # virtual_cost is NOT fitted — no historical virtual encounters exist.
    # Falls back to config.yaml default spec.
    ("system_cost_roi", "baseline_cost"): {
        "query": f"""
            SELECT SUM(b.total_charges) AS annual_cost
            FROM {catalog}.{schema}.encounters e
            JOIN {catalog}.{schema}.billing b ON e.encounter_id = b.encounter_id
            GROUP BY YEAR(e.admission_date)
        """,
        "column": "annual_cost",
        "dist_type": "lognormal",
    },
    ("system_cost_roi", "reduction_noise"): {
        # Reduction noise is synthetic — we use a standard normal fit
        # from monthly encounter volume variation as a proxy
        "query": f"""
            SELECT (cnt - avg_cnt) / NULLIF(std_cnt, 0) AS z_score
            FROM (
                SELECT COUNT(*) AS cnt,
                       AVG(COUNT(*)) OVER () AS avg_cnt,
                       STDDEV(COUNT(*)) OVER () AS std_cnt
                FROM {catalog}.{schema}.encounters
                GROUP BY YEAR(admission_date), MONTH(admission_date)
            )
            WHERE std_cnt > 0
        """,
        "column": "z_score",
        "dist_type": "normal",
    },
}

# COMMAND ----------

# ---------- Step 3: Fit distributions and collect results ----------

now = datetime.now(timezone.utc).isoformat()
rows = []
summary = []

for (sim_type, dist_name), source in FITTING_SOURCES.items():
    print(f"\nFitting {sim_type}.{dist_name} ({source['dist_type']})...")
    try:
        df = spark.sql(source["query"])
        values = np.array([row[source["column"]] for row in df.collect() if row[source["column"]] is not None])

        if len(values) < 10:
            print(f"  [SKIP] Only {len(values)} data points — need at least 10")
            continue

        result = fit_distribution(values, source["dist_type"])
        spec = result["spec"]
        metadata = result["metadata"]

        print(f"  Fitted: {json.dumps(spec)}")
        print(f"  KS stat: {metadata['ks_statistic']:.4f}, p-value: {metadata['p_value']:.4f}")
        print(f"  n_samples: {metadata['n_samples']}")

        rows.append((
            sim_type,
            dist_name,
            next_version,
            json.dumps(spec),
            json.dumps(metadata),
            now,
        ))
        summary.append({
            "sim_type": sim_type,
            "dist_name": dist_name,
            "type": spec["type"],
            "ks_stat": metadata["ks_statistic"],
            "p_value": metadata["p_value"],
            "n_samples": metadata["n_samples"],
        })

    except Exception as exc:
        print(f"  [ERROR] Failed to fit {sim_type}.{dist_name}: {exc}")

# COMMAND ----------

# ---------- Step 4: Write to distribution_specs table ----------

if rows:
    from pyspark.sql.types import IntegerType, StringType, StructField, StructType

    spec_schema = StructType([
        StructField("simulation_type", StringType(), False),
        StructField("distribution_name", StringType(), False),
        StructField("version", IntegerType(), False),
        StructField("spec", StringType(), False),
        StructField("fit_metadata", StringType(), True),
        StructField("created_at", StringType(), False),
    ])

    spec_df = spark.createDataFrame(rows, schema=spec_schema)
    table = f"{catalog}.{schema}.distribution_specs"
    spec_df.write.format("delta").mode("append").saveAsTable(table)
    print(f"\nWrote {len(rows)} distribution specs to {table} (version {next_version})")
else:
    print("\n[WARN] No distribution specs were fitted — table not updated")

# COMMAND ----------

# ---------- Step 5: Print summary ----------

print("\n" + "=" * 70)
print(f"Distribution Fitting Summary (version {next_version})")
print("=" * 70)
for s in summary:
    status = "PASS" if s["p_value"] > 0.05 else "WARN"
    print(f"  [{status}] {s['sim_type']}.{s['dist_name']} "
          f"({s['type']}, n={s['n_samples']}) "
          f"KS={s['ks_stat']:.4f}, p={s['p_value']:.4f}")
print("=" * 70)
