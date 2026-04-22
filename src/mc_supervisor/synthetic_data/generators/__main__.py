"""CLI entrypoint: generate all synthetic data CSVs.

Usage:
    python -m src.databricks.synthetic_data.generators
    python -m src.databricks.synthetic_data.generators --output-dir data --seed 42
"""

import argparse
import pathlib
import time

import pandas as pd

from ..config import (
    NUM_ENCOUNTERS,
    NUM_FACILITIES,
    NUM_PATIENTS,
    NUM_PROVIDERS,
    SEED,
)
from .billing import generate_billing
from .diagnoses import generate_diagnoses, generate_readmissions
from .encounters import generate_encounters
from .patients import generate_patients
from .procedures import generate_procedures
from .providers import generate_facilities, generate_providers
from .reference_data import (
    generate_cpt_codes,
    generate_departments,
    generate_icd10_codes,
    generate_payers,
)


def _write(df: pd.DataFrame, output_dir: pathlib.Path, name: str) -> None:
    """Write a DataFrame to CSV and print a summary."""
    path = output_dir / f"{name}.csv"
    df.to_csv(path, index=False)
    print(f"  {name:.<30s} {len(df):>8,} rows -> {path}")


def main(output_dir: str = "data", seed: int = SEED) -> None:
    """Generate all synthetic data CSVs in dependency order."""
    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Generating synthetic data (seed={seed}) -> {out.resolve()}\n")
    t0 = time.perf_counter()

    # --- Reference tables (no dependencies) ---
    print("Reference tables:")
    icd10_df = generate_icd10_codes()
    _write(icd10_df, out, "icd10_codes")

    cpt_df = generate_cpt_codes()
    _write(cpt_df, out, "cpt_codes")

    payers_df = generate_payers()
    _write(payers_df, out, "payers")

    departments_df = generate_departments()
    _write(departments_df, out, "departments")

    # --- Dimension tables ---
    print("\nDimension tables:")
    patients_df = generate_patients(num_patients=NUM_PATIENTS, seed=seed)
    _write(patients_df, out, "patients")

    facilities_df = generate_facilities(num_facilities=NUM_FACILITIES, seed=seed)
    _write(facilities_df, out, "facilities")

    providers_df = generate_providers(
        num_providers=NUM_PROVIDERS, facilities_df=facilities_df, seed=seed
    )
    _write(providers_df, out, "providers")

    # --- Fact tables ---
    print("\nFact tables:")
    encounters_df = generate_encounters(
        num_encounters=NUM_ENCOUNTERS,
        patients_df=patients_df,
        providers_df=providers_df,
        seed=seed,
    )
    _write(encounters_df, out, "encounters")

    diagnoses_df = generate_diagnoses(
        encounters_df=encounters_df, icd10_df=icd10_df, seed=seed
    )
    _write(diagnoses_df, out, "diagnoses")

    procedures_df = generate_procedures(
        encounters_df=encounters_df, cpt_df=cpt_df, seed=seed
    )
    _write(procedures_df, out, "procedures")

    readmissions_df = generate_readmissions(encounters_df=encounters_df, seed=seed)
    _write(readmissions_df, out, "readmissions")

    # Billing needs insurance_type from patients merged onto encounters
    encounters_with_insurance = encounters_df.merge(
        patients_df[["patient_id", "insurance_type"]], on="patient_id", how="left"
    )
    billing_df = generate_billing(
        encounters_df=encounters_with_insurance, payers_df=payers_df, seed=seed
    )
    _write(billing_df, out, "billing")

    elapsed = time.perf_counter() - t0
    print(f"\nDone in {elapsed:.1f}s. {len(list(out.glob('*.csv')))} CSV files generated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic women's health data CSVs")
    parser.add_argument(
        "--output-dir", default="data", help="Output directory (default: data)"
    )
    parser.add_argument(
        "--seed", type=int, default=SEED, help=f"Random seed (default: {SEED})"
    )
    args = parser.parse_args()
    main(output_dir=args.output_dir, seed=args.seed)
