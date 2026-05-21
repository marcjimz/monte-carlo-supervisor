"""Generate synthetic billing records."""

import numpy as np
import pandas as pd

from ..config import CHARGE_PARAMS, DENIAL_RATE, PAYER_REIMBURSEMENT


def generate_billing(
    encounters_df: pd.DataFrame,
    payers_df: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate one billing record per encounter.

    Charges are drawn from a normal distribution parameterised by
    encounter type (see ``config.CHARGE_PARAMS``).  Payer reimbursement
    rates and denial probabilities come from ``config.PAYER_REIMBURSEMENT``
    and ``config.DENIAL_RATE`` respectively.

    Args:
        encounters_df: DataFrame with at least ``encounter_id``,
            ``patient_id``, ``encounter_type``, ``insurance_type``, and
            ``discharge_date`` columns.
        payers_df: Reference payer DataFrame with ``payer_id`` and
            ``payer_name`` columns.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: billing_id, encounter_id, total_charges,
        payer_id, allowed_amount, paid_amount, patient_responsibility,
        claim_status, payment_date.
    """
    rng = np.random.default_rng(seed)
    n = len(encounters_df)

    # Build insurance_type -> payer_id lookup from the reference table
    insurance_to_payer: dict[str, str] = dict(
        zip(payers_df["payer_name"], payers_df["payer_id"])
    )

    # --- Vectorised generation for performance ---

    # 1. Billing IDs
    billing_ids = [f"BILL{i + 1:06d}" for i in range(n)]

    # 2. Total charges (normal distribution, clipped to positive values)
    enc_types = encounters_df["encounter_type"].values
    means = np.array([CHARGE_PARAMS[t][0] for t in enc_types], dtype=np.float64)
    stds = np.array([CHARGE_PARAMS[t][1] for t in enc_types], dtype=np.float64)

    total_charges = rng.normal(means, stds)
    # Ensure no negative charges; floor at 10 % of the mean as a reasonable min
    total_charges = np.maximum(total_charges, means * 0.10)
    total_charges = np.round(total_charges, 2)

    # 3. Payer IDs (map from patient's insurance_type)
    insurance_types = encounters_df["insurance_type"].values
    payer_ids = np.array(
        [insurance_to_payer.get(ins, insurance_to_payer.get("Other", "PAY008")) for ins in insurance_types]
    )

    # 4. Allowed amount = total_charges * reimbursement rate
    reimbursement_rates = np.array(
        [PAYER_REIMBURSEMENT.get(ins, 0.75) for ins in insurance_types],
        dtype=np.float64,
    )
    allowed_amounts = np.round(total_charges * reimbursement_rates, 2)

    # 5. Claim status: Paid 84 %, Denied 8 %, Pending 8 %
    pending_rate = DENIAL_RATE  # reuse the same 8 % rate for pending
    paid_rate = 1.0 - DENIAL_RATE - pending_rate
    claim_statuses = rng.choice(
        ["Paid", "Denied", "Pending"],
        size=n,
        p=[paid_rate, DENIAL_RATE, pending_rate],
    )

    # 6. Paid amount: for Paid claims, allowed * random factor in [0.85, 1.0]
    pay_factors = rng.uniform(0.85, 1.0, size=n)
    paid_amounts = np.where(
        claim_statuses == "Paid",
        np.round(allowed_amounts * pay_factors, 2),
        0.0,
    )

    # 7. Patient responsibility
    patient_responsibility = np.where(
        claim_statuses == "Paid",
        np.round(allowed_amounts - paid_amounts, 2),
        np.where(
            claim_statuses == "Denied",
            np.round(allowed_amounts, 2),  # patient owes full allowed amount
            0.0,  # Pending -- not yet determined
        ),
    )

    # 8. Payment date: discharge + 15-90 days for Paid, NaT otherwise
    discharge_dates = pd.to_datetime(encounters_df["discharge_date"].values)
    payment_offsets = rng.integers(15, 91, size=n)
    payment_dates = pd.Series(
        [
            discharge + pd.Timedelta(days=int(offset)) if status == "Paid" else pd.NaT
            for discharge, offset, status in zip(discharge_dates, payment_offsets, claim_statuses)
        ]
    )

    return pd.DataFrame(
        {
            "billing_id": billing_ids,
            "encounter_id": encounters_df["encounter_id"].values,
            "total_charges": total_charges,
            "payer_id": payer_ids,
            "allowed_amount": allowed_amounts,
            "paid_amount": paid_amounts,
            "patient_responsibility": patient_responsibility,
            "claim_status": claim_statuses,
            "payment_date": payment_dates,
        }
    )
