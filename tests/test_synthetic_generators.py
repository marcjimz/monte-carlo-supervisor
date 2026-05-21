"""Tests for synthetic data generators — Women's Health focus, pure Python, no Spark required."""

import pandas as pd
import pytest

from src.mc_supervisor.synthetic_data.generators.patients import generate_patients
from src.mc_supervisor.synthetic_data.generators.providers import (
    generate_facilities,
    generate_providers,
)
from src.mc_supervisor.synthetic_data.generators.encounters import generate_encounters
from src.mc_supervisor.synthetic_data.generators.diagnoses import generate_diagnoses
from src.mc_supervisor.synthetic_data.generators.reference_data import (
    generate_cpt_codes,
    generate_departments,
    generate_icd10_codes,
    generate_payers,
)

# ---------------------------------------------------------------------------
# Small counts for fast tests
# ---------------------------------------------------------------------------
NUM_PATIENTS = 100
NUM_FACILITIES = 5
NUM_PROVIDERS = 10
NUM_ENCOUNTERS = 500
SEED = 42

VALID_ENCOUNTER_TYPES = {"Outpatient", "Emergency", "Inpatient", "Observation"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def patients_df() -> pd.DataFrame:
    return generate_patients(num_patients=NUM_PATIENTS, seed=SEED)


@pytest.fixture(scope="module")
def facilities_df() -> pd.DataFrame:
    return generate_facilities(num_facilities=NUM_FACILITIES, seed=SEED)


@pytest.fixture(scope="module")
def providers_df(facilities_df: pd.DataFrame) -> pd.DataFrame:
    return generate_providers(
        num_providers=NUM_PROVIDERS,
        facilities_df=facilities_df,
        seed=SEED,
    )


@pytest.fixture(scope="module")
def encounters_df(patients_df: pd.DataFrame, providers_df: pd.DataFrame) -> pd.DataFrame:
    return generate_encounters(
        num_encounters=NUM_ENCOUNTERS,
        patients_df=patients_df,
        providers_df=providers_df,
        seed=SEED,
    )


# ---------------------------------------------------------------------------
# Patient tests
# ---------------------------------------------------------------------------


class TestGeneratePatients:
    def test_row_count(self, patients_df: pd.DataFrame):
        assert len(patients_df) == NUM_PATIENTS

    def test_expected_columns(self, patients_df: pd.DataFrame):
        expected_cols = {
            "patient_id",
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "zip_code",
            "insurance_type",
            "chronic_conditions",
            "num_chronic",
        }
        assert expected_cols.issubset(set(patients_df.columns))

    def test_all_female(self, patients_df: pd.DataFrame):
        """All patients must be female for WH cohort."""
        assert set(patients_df["gender"].unique()) == {"F"}

    def test_all_adults(self, patients_df: pd.DataFrame):
        """All patients should be 18+ (adult women's health)."""
        ref_date = pd.Timestamp("2026-03-01")
        ages = (ref_date - patients_df["date_of_birth"]).dt.days / 365.25
        assert ages.min() >= 17.5  # allow small rounding tolerance

    def test_deterministic_with_same_seed(self):
        df1 = generate_patients(num_patients=50, seed=99)
        df2 = generate_patients(num_patients=50, seed=99)
        pd.testing.assert_frame_equal(df1, df2)


# ---------------------------------------------------------------------------
# Facility tests
# ---------------------------------------------------------------------------


class TestGenerateFacilities:
    def test_row_count(self, facilities_df: pd.DataFrame):
        assert len(facilities_df) == NUM_FACILITIES

    def test_expected_columns(self, facilities_df: pd.DataFrame):
        expected_cols = {
            "facility_id",
            "facility_name",
            "facility_type",
            "bed_count",
            "address",
            "city",
            "state",
        }
        assert expected_cols == set(facilities_df.columns)


# ---------------------------------------------------------------------------
# Provider tests
# ---------------------------------------------------------------------------


class TestGenerateProviders:
    def test_row_count(self, providers_df: pd.DataFrame):
        assert len(providers_df) == NUM_PROVIDERS

    def test_expected_columns(self, providers_df: pd.DataFrame):
        expected_cols = {
            "provider_id",
            "first_name",
            "last_name",
            "specialty",
            "facility_id",
            "npi",
        }
        assert expected_cols == set(providers_df.columns)

    def test_valid_facility_ids(self, providers_df: pd.DataFrame, facilities_df: pd.DataFrame):
        valid_ids = set(facilities_df["facility_id"])
        assert set(providers_df["facility_id"]).issubset(valid_ids)


# ---------------------------------------------------------------------------
# Encounter tests
# ---------------------------------------------------------------------------


class TestGenerateEncounters:
    def test_row_count(self, encounters_df: pd.DataFrame):
        assert len(encounters_df) == NUM_ENCOUNTERS

    def test_expected_columns(self, encounters_df: pd.DataFrame):
        expected_cols = {
            "encounter_id",
            "patient_id",
            "provider_id",
            "facility_id",
            "encounter_type",
            "department",
            "admission_date",
            "discharge_date",
            "length_of_stay",
        }
        assert expected_cols == set(encounters_df.columns)

    def test_valid_encounter_types(self, encounters_df: pd.DataFrame):
        actual_types = set(encounters_df["encounter_type"].unique())
        assert actual_types.issubset(VALID_ENCOUNTER_TYPES)


# ---------------------------------------------------------------------------
# Diagnosis tests
# ---------------------------------------------------------------------------


class TestGenerateDiagnoses:
    def test_expected_columns(self, encounters_df: pd.DataFrame):
        icd10_df = generate_icd10_codes()
        diagnoses_df = generate_diagnoses(encounters_df, icd10_df, seed=SEED)

        expected_cols = {
            "diagnosis_id",
            "encounter_id",
            "icd10_code",
            "description",
            "is_primary",
            "sequence_num",
        }
        assert expected_cols == set(diagnoses_df.columns)

    def test_at_least_one_per_encounter(self, encounters_df: pd.DataFrame):
        """Each encounter should have at least one diagnosis (1-3 per encounter)."""
        icd10_df = generate_icd10_codes()
        diagnoses_df = generate_diagnoses(encounters_df, icd10_df, seed=SEED)

        encounter_ids_with_dx = set(diagnoses_df["encounter_id"])
        encounter_ids_all = set(encounters_df["encounter_id"])
        # Every encounter should have at least one diagnosis
        assert encounter_ids_with_dx == encounter_ids_all

    def test_has_womens_health_codes(self, encounters_df: pd.DataFrame):
        """ICD-10 codes should include women's health category."""
        icd10_df = generate_icd10_codes()
        assert "Women's Health" in icd10_df["category"].values


# ---------------------------------------------------------------------------
# Reference data tests
# ---------------------------------------------------------------------------


class TestGenerateReferenceData:
    def test_icd10_columns(self):
        df = generate_icd10_codes()
        assert {"icd10_code", "description", "category"} == set(df.columns)
        assert len(df) > 0

    def test_icd10_has_womens_health(self):
        df = generate_icd10_codes()
        categories = set(df["category"].unique())
        assert "Women's Health" in categories

    def test_cpt_columns(self):
        df = generate_cpt_codes()
        assert {"cpt_code", "description", "category", "fee_low", "fee_high"} == set(df.columns)
        assert len(df) > 0

    def test_cpt_has_gyn_procedures(self):
        df = generate_cpt_codes()
        # Should have hysteroscopy (58558) and lap hysterectomy (58571)
        codes = set(df["cpt_code"])
        assert "58558" in codes
        assert "58571" in codes

    def test_payers_columns(self):
        df = generate_payers()
        assert {"payer_id", "payer_name", "payer_type", "avg_reimbursement_rate"} == set(df.columns)
        assert len(df) > 0

    def test_departments_columns(self):
        df = generate_departments()
        assert {"department_id", "department_name"} == set(df.columns)
        assert len(df) > 0

    def test_departments_has_obgyn(self):
        df = generate_departments()
        assert "OB/GYN" in df["department_name"].values


# ---------------------------------------------------------------------------
# Determinism test
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    def test_same_seed_produces_identical_patients(self):
        df1 = generate_patients(num_patients=50, seed=123)
        df2 = generate_patients(num_patients=50, seed=123)
        pd.testing.assert_frame_equal(df1, df2)

    def test_same_seed_produces_identical_facilities(self):
        df1 = generate_facilities(num_facilities=5, seed=123)
        df2 = generate_facilities(num_facilities=5, seed=123)
        pd.testing.assert_frame_equal(df1, df2)

    def test_same_seed_produces_identical_encounters(self):
        df1 = generate_encounters(num_encounters=100, seed=123)
        df2 = generate_encounters(num_encounters=100, seed=123)
        pd.testing.assert_frame_equal(df1, df2)
