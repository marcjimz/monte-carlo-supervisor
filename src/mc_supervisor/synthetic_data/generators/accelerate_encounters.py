"""Generate synthetic Project Accelerate encounter data.

Produces ~75,000 encounter rows matching the project_accelerate_encounters
table schema, including nested diagnoses array<struct>. Returns a list of
dicts suitable for conversion to a Spark DataFrame.

This generator is for demo/feasibility testing only. Customers bring their own
encounter table and skip this entirely.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from ..config import (
    ACCELERATE_DATE_END,
    ACCELERATE_DATE_START,
    ACCELERATE_NUM_ENCOUNTERS,
    ACCELERATE_NUM_PATIENTS,
    SEED,
)
from .accelerate_reference import (
    BASE_CLASS_WEIGHTS,
    BUSINESS_UNITS,
    CHARGE_LOG_PARAMS,
    COST_TO_CHARGE,
    FIN_CLASS_WEIGHTS,
    FIRST_NAMES,
    ICD_SG2_MAPPING,
    LAST_NAMES,
    LOS_LOG_PARAMS,
    PATIENT_CLASS_INNER_WEIGHTS,
    PATIENT_CLASS_MAP,
    REIMBURSEMENT_RATES,
    SOURCE_SYSTEM_WEIGHTS,
    SOURCE_SYSTEMS,
    WH_SERVICE_LINE,
)


def _generate_patients(rng: np.random.Generator, n: int) -> list[dict]:
    """Generate unique patient records."""
    patients = []
    for i in range(n):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        # Bimodal age: 40% reproductive (18-45), 60% perimenopause+ (45-90)
        if rng.random() < 0.40:
            age = int(rng.integers(18, 46))
        else:
            age = int(rng.integers(45, 91))

        patients.append({
            "cdm_patient_key": f"PAT-{i + 1:06d}",
            "patient_enterprise_id": f"ENT-{i + 1:08d}",
            "patient_xmrn": f"XMRN-{i + 1:08d}",
            "patient_name": f"{last}, {first}",
            "patient_gender": "Female",
            "patient_age_years": age,
        })
    return patients


def _seasonal_date(rng: np.random.Generator, start: date, end: date) -> date:
    """Generate a date with seasonal patterns (higher volume in winter)."""
    total_days = (end - start).days
    day_offset = int(rng.integers(0, total_days))
    d = start + timedelta(days=day_offset)
    # Seasonal acceptance: higher in winter/spring, lower in summer
    seasonal_prob = {
        1: 1.0, 2: 1.0, 3: 0.95, 4: 0.90, 5: 0.85, 6: 0.80,
        7: 0.78, 8: 0.80, 9: 0.85, 10: 0.90, 11: 0.95, 12: 0.98,
    }
    if rng.random() < seasonal_prob.get(d.month, 0.85):
        return d
    # Retry once for a different date
    day_offset = int(rng.integers(0, total_days))
    return start + timedelta(days=day_offset)


def generate_accelerate_encounters(
    num_encounters: int | None = None,
    num_patients: int | None = None,
    seed: int | None = None,
) -> list[dict]:
    """Generate Project Accelerate encounter records.

    Returns a list of dicts with a ``diagnoses`` key containing a list of
    diagnosis structs (0-2 per encounter). Suitable for Spark DataFrame
    creation with ArrayType(StructType(...)).
    """
    num_encounters = num_encounters or ACCELERATE_NUM_ENCOUNTERS
    num_patients = num_patients or ACCELERATE_NUM_PATIENTS
    seed = seed if seed is not None else SEED
    rng = np.random.default_rng(seed)

    start_date = date.fromisoformat(ACCELERATE_DATE_START)
    end_date = date.fromisoformat(ACCELERATE_DATE_END)

    patients = _generate_patients(rng, num_patients)

    # Pre-compute choice arrays
    base_classes = list(BASE_CLASS_WEIGHTS.keys())
    base_weights = np.array(list(BASE_CLASS_WEIGHTS.values()))
    base_weights /= base_weights.sum()

    fin_classes = list(FIN_CLASS_WEIGHTS.keys())
    fin_weights = np.array(list(FIN_CLASS_WEIGHTS.values()))
    fin_weights /= fin_weights.sum()

    wh_icd = [r for r in ICD_SG2_MAPPING if r[2] == WH_SERVICE_LINE]
    non_wh_icd = [r for r in ICD_SG2_MAPPING if r[2] != WH_SERVICE_LINE]

    rows: list[dict] = []
    for i in range(num_encounters):
        patient = patients[int(rng.integers(0, num_patients))]

        # IDs
        enc_key = f"ENC-{i + 1:08d}"
        billing_id = f"BILL-{i + 1:08d}"
        cln_key = f"CLN-{i + 1:08d}"
        cln_id = f"CID-{i + 1:08d}"

        # Classification
        base_class = str(rng.choice(base_classes, p=base_weights))
        pc_options = PATIENT_CLASS_MAP[base_class]
        pc_w = np.array(PATIENT_CLASS_INNER_WEIGHTS[base_class])
        pc_w = pc_w / pc_w.sum()
        patient_class = str(rng.choice(pc_options, p=pc_w))

        source_system = str(rng.choice(SOURCE_SYSTEMS, p=SOURCE_SYSTEM_WEIGHTS))
        hb_pb = "HB" if rng.random() < 0.60 else "PB"
        bu = BUSINESS_UNITS[int(rng.integers(0, len(BUSINESS_UNITS)))]
        fin_class = str(rng.choice(fin_classes, p=fin_weights))
        surgery_flag = 1 if rng.random() < 0.15 else 0
        is_wh = 1 if rng.random() < 0.35 else 0

        # Dates
        admit = _seasonal_date(rng, start_date, end_date)
        los_mu, los_sigma = LOS_LOG_PARAMS[base_class]
        los_days = max(0, int(round(float(rng.lognormal(los_mu, los_sigma)))))
        if base_class == "Outpatient":
            los_days = 0
        discharge = admit + timedelta(days=los_days)

        # Financials
        ch_mu, ch_sigma = CHARGE_LOG_PARAMS[base_class]
        total_charge = float(rng.lognormal(ch_mu, ch_sigma))

        reimb_rate = REIMBURSEMENT_RATES.get(fin_class, 0.75)
        custom_expected_payment = total_charge * reimb_rate

        ctc_lo, ctc_hi = COST_TO_CHARGE[base_class]
        ctc = float(rng.uniform(ctc_lo, ctc_hi))
        total_cost = total_charge * ctc
        total_direct_cost = total_cost * 0.70
        total_variable_cost = total_cost * 0.45
        total_margin = custom_expected_payment - total_cost
        direct_margin = custom_expected_payment - total_direct_cost
        variable_margin = custom_expected_payment - total_variable_cost

        # Diagnoses (0-2 per encounter)
        n_dx = int(rng.choice([0, 1, 2], p=[0.05, 0.60, 0.35]))
        diagnoses: list[dict] = []
        for dx_idx in range(n_dx):
            if is_wh and rng.random() < 0.70:
                icd_row = wh_icd[int(rng.integers(0, len(wh_icd)))]
            else:
                icd_row = non_wh_icd[int(rng.integers(0, len(non_wh_icd)))]
            icd_code, dx_name, svc_line, care_fam, disease_base = icd_row

            dx_type = "hosp_acct_final_dx" if hb_pb == "HB" else "phys_billing_encounter_dx"
            # Second diagnosis may be the other type (both-billed)
            if dx_idx == 1 and rng.random() < 0.20:
                dx_type = (
                    "phys_billing_encounter_dx"
                    if dx_type == "hosp_acct_final_dx"
                    else "hosp_acct_final_dx"
                )

            diagnoses.append({
                "diagnosis_type": dx_type,
                "diagnosis_name": dx_name,
                "icd_code_value": icd_code,
                "sg2_service_line_group": svc_line,
                "sg2_care_family_group": care_fam,
                "sg2_disease_base_group": disease_base,
                "is_custom_womens_health_population": 1 if svc_line == WH_SERVICE_LINE else 0,
            })

        rows.append({
            "cdm_billing_encounter_key": enc_key,
            "billing_encounter_id": billing_id,
            "cdm_clinical_contact_key": cln_key,
            "clinical_contact_id": cln_id,
            "cdm_patient_key": patient["cdm_patient_key"],
            "patient_enterprise_id": patient["patient_enterprise_id"],
            "patient_xmrn": patient["patient_xmrn"],
            "patient_name": patient["patient_name"],
            "patient_gender": patient["patient_gender"],
            "patient_age_years": patient["patient_age_years"],
            "source_system_name": source_system,
            "hb_pb": hb_pb,
            "admit_date": admit,
            "discharge_date": discharge,
            "base_class_config_name": base_class,
            "patient_class_config_name": patient_class,
            "surgery_flag": surgery_flag,
            "business_unit_id": bu["id"],
            "business_unit_name": bu["name"],
            "region_name": bu["region"],
            "fin_class": fin_class,
            "is_custom_womens_health_population": is_wh,
            "total_charge": round(total_charge, 2),
            "custom_expected_payment": round(custom_expected_payment, 2),
            "total_cost": round(total_cost, 2),
            "total_direct_cost": round(total_direct_cost, 2),
            "total_variable_cost": round(total_variable_cost, 2),
            "total_margin": round(total_margin, 2),
            "direct_margin": round(direct_margin, 2),
            "variable_margin": round(variable_margin, 2),
            "diagnoses": diagnoses,
        })

    return rows
