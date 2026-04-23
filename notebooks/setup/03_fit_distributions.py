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
dbutils.widgets.text("metric_view", "", "Metric View (fully qualified, or empty for default)")

# COMMAND ----------

# Install project package from bundled wheel
import subprocess, sys
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = "/Workspace" + "/".join(_nb.split("/")[:-3])
subprocess.check_call([sys.executable, "-m", "pip", "install", f"{_root}/dist/monte_carlo_supervisor-1.0.0-py3-none-any.whl", "-q", "--disable-pip-version-check"])

# COMMAND ----------

import json
from datetime import datetime, timezone

import numpy as np

from mc_supervisor.monte_carlo import config_loader
from mc_supervisor.monte_carlo.fitting import fit_distribution
from mc_supervisor.monte_carlo.results import get_latest_distribution_version

# COMMAND ----------

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
metric_view = dbutils.widgets.get("metric_view").strip() or f"{metric_view}"

print(f"Catalog/Schema: {catalog}.{schema}")
print(f"Metric View:    {metric_view}")

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

# All fitting queries use MEASURE() against the metric view. This is the key
# abstraction: customers create mv_accelerate_encounters pointing to their own
# encounter table, and fitting works against their data without code changes.
FITTING_SOURCES = {
    ("encounter_margin", "monthly_margin"): {
        "query": f"""
            SELECT MEASURE(`Direct Margin`) AS monthly_margin
            FROM {metric_view}
            GROUP BY DATE_TRUNC('MONTH', admit_date)
        """,
        "column": "monthly_margin",
        "dist_type": "normal",
    },
    ("encounter_margin", "encounter_volume"): {
        "query": f"""
            SELECT MEASURE(`Encounter Count`) AS enc_count
            FROM {metric_view}
            GROUP BY DATE_TRUNC('MONTH', admit_date)
        """,
        "column": "enc_count",
        "dist_type": "normal",
    },
    ("encounter_margin", "cost_per_encounter"): {
        "query": f"""
            SELECT MEASURE(`Total Cost`) / MEASURE(`Encounter Count`) AS avg_cost
            FROM {metric_view}
            GROUP BY DATE_TRUNC('MONTH', admit_date)
        """,
        "column": "avg_cost",
        "dist_type": "lognormal",
    },
    ("wh_margin_comparison", "wh_margin"): {
        "query": f"""
            SELECT MEASURE(`Direct Margin`) / MEASURE(`Encounter Count`) AS margin_per_enc
            FROM {metric_view}
            WHERE is_custom_womens_health_population = 1
            GROUP BY DATE_TRUNC('MONTH', admit_date)
        """,
        "column": "margin_per_enc",
        "dist_type": "normal",
    },
    ("wh_margin_comparison", "non_wh_margin"): {
        "query": f"""
            SELECT MEASURE(`Direct Margin`) / MEASURE(`Encounter Count`) AS margin_per_enc
            FROM {metric_view}
            WHERE is_custom_womens_health_population = 0
            GROUP BY DATE_TRUNC('MONTH', admit_date)
        """,
        "column": "margin_per_enc",
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
