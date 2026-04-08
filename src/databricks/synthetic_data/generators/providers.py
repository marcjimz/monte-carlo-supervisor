"""Generate synthetic provider and facility records."""

import numpy as np
import pandas as pd
from faker import Faker

from ..config import SPECIALTIES


def generate_facilities(num_facilities: int = 15, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic healthcare facility records.

    Args:
        num_facilities: Number of facilities to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: facility_id, facility_name, facility_type,
        bed_count, address, city, state.
    """
    rng = np.random.default_rng(seed)
    fake = Faker()
    Faker.seed(seed)

    facility_types = ["Hospital", "Clinic", "Urgent Care"]
    # Weights: more hospitals, fewer urgent-care centres
    type_weights = np.array([0.50, 0.30, 0.20])

    facility_ids: list[str] = []
    facility_names: list[str] = []
    types: list[str] = []
    bed_counts: list[int] = []
    addresses: list[str] = []
    cities: list[str] = []
    states: list[str] = []

    # Hospital-name suffixes for variety
    hospital_suffixes = [
        "Medical Center",
        "General Hospital",
        "Regional Hospital",
        "Community Hospital",
        "Memorial Hospital",
    ]
    clinic_suffixes = [
        "Family Clinic",
        "Health Clinic",
        "Medical Group",
        "Physicians Clinic",
    ]
    urgent_care_suffixes = [
        "Urgent Care",
        "Express Care",
        "Walk-In Clinic",
    ]

    for i in range(num_facilities):
        fac_id = f"FAC{i + 1:03d}"
        fac_type = rng.choice(facility_types, p=type_weights)

        # Generate a plausible facility name
        city = fake.city()
        if fac_type == "Hospital":
            name = f"{city} {rng.choice(hospital_suffixes)}"
            beds = int(rng.integers(50, 501))  # 50-500
        elif fac_type == "Clinic":
            name = f"{city} {rng.choice(clinic_suffixes)}"
            beds = int(rng.integers(0, 11))  # 0-10 (clinics have few/no beds)
        else:  # Urgent Care
            name = f"{city} {rng.choice(urgent_care_suffixes)}"
            beds = int(rng.integers(0, 6))  # 0-5

        facility_ids.append(fac_id)
        facility_names.append(name)
        types.append(fac_type)
        bed_counts.append(beds)
        addresses.append(fake.street_address())
        cities.append(city)
        states.append(fake.state_abbr())

    return pd.DataFrame(
        {
            "facility_id": facility_ids,
            "facility_name": facility_names,
            "facility_type": types,
            "bed_count": bed_counts,
            "address": addresses,
            "city": cities,
            "state": states,
        }
    )


def generate_providers(
    num_providers: int = 500,
    facilities_df: pd.DataFrame | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic healthcare provider records.

    Each provider is assigned a specialty from the config list, an NPI
    (National Provider Identifier), and a facility from the supplied
    facilities DataFrame.

    Args:
        num_providers: Number of provider records to generate.
        facilities_df: DataFrame of facilities (must contain ``facility_id``).
            If ``None``, ``generate_facilities()`` is called internally.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: provider_id, first_name, last_name,
        specialty, facility_id, npi.
    """
    rng = np.random.default_rng(seed)
    fake = Faker()
    Faker.seed(seed)

    if facilities_df is None:
        facilities_df = generate_facilities(seed=seed)

    facility_ids = facilities_df["facility_id"].tolist()

    provider_ids: list[str] = []
    first_names: list[str] = []
    last_names: list[str] = []
    specialties: list[str] = []
    assigned_facilities: list[str] = []
    npis: list[str] = []

    # Pre-generate a pool of unique NPIs
    npi_set: set[str] = set()
    while len(npi_set) < num_providers:
        npi_set.add(str(rng.integers(1_000_000_000, 10_000_000_000)))
    npi_pool = list(npi_set)

    for i in range(num_providers):
        provider_ids.append(f"PROV{i + 1:04d}")
        first_names.append(fake.first_name())
        last_names.append(fake.last_name())
        specialties.append(rng.choice(SPECIALTIES))
        assigned_facilities.append(rng.choice(facility_ids))
        npis.append(npi_pool[i])

    return pd.DataFrame(
        {
            "provider_id": provider_ids,
            "first_name": first_names,
            "last_name": last_names,
            "specialty": specialties,
            "facility_id": assigned_facilities,
            "npi": npis,
        }
    )
