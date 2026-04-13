"""Seed demo data — Ali's published showcase + presenter's draft walkthrough."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from server import db

logger = logging.getLogger(__name__)

# --- Ali's published showcase ---

DEMO_OWNER = "ali.ghodsi@databricks.com"
DEMO_ANALYSIS_NAME = "Virtual Care Cost Impact Study"

# --- Presenter's draft walkthrough ---

PRESENTER_OWNER = "marcin.jimenez@databricks.com"
PRESENTER_ANALYSIS_NAME = "Postpartum Care Virtual Pilot"


# =========================================================================
# Delete helpers
# =========================================================================

async def _delete_analysis_cascade(owner_email: str, name: str):
    """Delete an analysis and all related data by owner + name."""
    existing = await db.fetch_one(
        "SELECT id FROM analyses WHERE owner_email = $1 AND name = $2",
        owner_email,
        name,
    )
    if not existing:
        return
    analysis_id = existing["id"]

    # Delete in dependency order
    await db.execute(
        "DELETE FROM thread_messages WHERE thread_id IN "
        "(SELECT id FROM agent_threads WHERE analysis_id = $1)",
        analysis_id,
    )
    await db.execute("DELETE FROM agent_threads WHERE analysis_id = $1", analysis_id)
    await db.execute(
        "DELETE FROM matrix_cells WHERE matrix_id IN "
        "(SELECT id FROM analysis_matrices WHERE analysis_id = $1)",
        analysis_id,
    )
    await db.execute("DELETE FROM analysis_matrices WHERE analysis_id = $1", analysis_id)
    await db.execute("DELETE FROM analysis_simulations WHERE analysis_id = $1", analysis_id)
    await db.execute("DELETE FROM analysis_collaborators WHERE analysis_id = $1", analysis_id)
    await db.execute("DELETE FROM analyses WHERE id = $1", analysis_id)
    logger.info("Deleted data for analysis=%s (%s)", analysis_id, name)


async def delete_demo_data():
    """Delete all demo data for re-seeding."""
    await _delete_analysis_cascade(DEMO_OWNER, DEMO_ANALYSIS_NAME)
    await _delete_analysis_cascade(PRESENTER_OWNER, PRESENTER_ANALYSIS_NAME)


# =========================================================================
# Seed: Ali's published showcase (completed matrix + conversation thread)
# =========================================================================

async def _seed_ali_showcase():
    """Seed Ali's published analysis with matrix and thread."""
    existing = await db.fetch_one(
        "SELECT id FROM analyses WHERE owner_email = $1 AND name = $2",
        DEMO_OWNER,
        DEMO_ANALYSIS_NAME,
    )
    if existing:
        logger.info("Ali showcase already exists, skipping")
        return

    logger.info("Seeding Ali showcase...")

    # 1. Analysis
    analysis = await db.fetch_one(
        """INSERT INTO analyses (name, description, owner_email, status)
           VALUES ($1, $2, $3, $4)
           RETURNING id""",
        DEMO_ANALYSIS_NAME,
        "Analyzing the cost impact of virtual care adoption for women's health "
        "services across Intermountain Health. Compares blended cost per encounter "
        "at varying virtual penetration rates and population sizes.",
        DEMO_OWNER,
        "published",
    )
    analysis_id = analysis["id"]

    # 2. Cost comparison matrix (3x3)
    matrix = await db.fetch_one(
        """INSERT INTO analysis_matrices
           (analysis_id, name, description, simulation_type, row_parameter, row_values,
            col_parameter, col_values, base_parameters, output_metric,
            output_group_key, output_group_value, num_simulations, seed)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
           RETURNING id""",
        analysis_id,
        "Virtual Penetration vs Population Size",
        "Blended cost per encounter at 20-40% virtual care penetration across 30K-70K member populations",
        "cost_comparison",
        "virtual_penetration",
        json.dumps([0.20, 0.30, 0.40]),
        "member_count",
        json.dumps([30000, 50000, 70000]),
        json.dumps({"annual_encounter_rate": 2.5, "num_months": 12}),
        "simulated_cost_per_encounter",
        "care_model",
        "blended",
        10000,
        42,
    )
    matrix_id = matrix["id"]

    # 3. Matrix cells — realistic results (cost decreases with penetration)
    cells = [
        (0.20, 30000, 1102.0, 1048.0, 1100.0, 1158.0),
        (0.20, 50000, 1098.0, 1045.0, 1097.0, 1153.0),
        (0.20, 70000, 1105.0, 1051.0, 1104.0, 1161.0),
        (0.30, 30000, 1018.0, 968.0, 1017.0, 1070.0),
        (0.30, 50000, 1022.0, 972.0, 1021.0, 1074.0),
        (0.30, 70000, 1025.0, 974.0, 1024.0, 1078.0),
        (0.40, 30000, 948.0, 901.0, 947.0, 997.0),
        (0.40, 50000, 952.0, 904.0, 951.0, 1002.0),
        (0.40, 70000, 955.0, 907.0, 954.0, 1005.0),
    ]

    for rv, cv, mean, p05, p50, p95 in cells:
        run_id = f"demo_{uuid4().hex[:12]}"
        await db.execute(
            """INSERT INTO matrix_cells
               (matrix_id, row_value, col_value, run_id, status,
                result_mean, result_p05, result_p50, result_p95)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            matrix_id, rv, cv, run_id, "completed", mean, p05, p50, p95,
        )

    # 4. Thread with hypothesis-chasing conversation
    thread = await db.fetch_one(
        """INSERT INTO agent_threads (analysis_id, owner_email, title, icon)
           VALUES ($1, $2, $3, $4)
           RETURNING id""",
        analysis_id, DEMO_OWNER, "Virtual Care Cost Hypothesis", "chat",
    )
    thread_id = thread["id"]

    messages = [
        (
            "user",
            "I believe increasing virtual care penetration to 40% could reduce "
            "blended costs by 10-15%. Can we test this?",
        ),
        (
            "assistant",
            "Great hypothesis! Let me structure a simulation plan to test it.\n\n"
            "I'll run a **cost_comparison** simulation matrix comparing virtual "
            "penetration rates against population sizes:\n\n"
            "| Parameter | Values |\n"
            "|---|---|\n"
            "| Virtual Penetration | 20%, 30%, 40% |\n"
            "| Population Size | 30K, 50K, 70K |\n"
            "| Encounters/Member/Year | 2.5 |\n"
            "| Trials per Cell | 10,000 |\n\n"
            "This gives us **9 scenarios** with confidence intervals. "
            "The baseline (20% penetration) serves as our control.\n\n"
            "Shall I run this matrix?",
        ),
        (
            "user",
            "Yes, run that matrix. I want confidence intervals too.",
        ),
        (
            "assistant",
            "The matrix has completed — all 9 cells finished (10,000 trials each). "
            "Here are the results:\n\n"
            "### Blended Cost per Encounter\n\n"
            "| Penetration | 30K Members | 50K Members | 70K Members |\n"
            "|---|---|---|---|\n"
            "| **20%** (baseline) | $1,102 | $1,098 | $1,105 |\n"
            "| **30%** | $1,018 | $1,022 | $1,025 |\n"
            "| **40%** | $948 | $952 | $955 |\n\n"
            "### Key Findings\n\n"
            "1. **Your hypothesis is confirmed** — at 40% penetration, blended cost "
            "drops to ~$950/encounter vs ~$1,100 at baseline, a **13.3% reduction**\n"
            "2. **Confidence intervals are tight** — P05-P95 spans ~$100 across all "
            "scenarios, indicating stable projections\n"
            "3. **Scale-independent** — costs remain consistent across 30K-70K "
            "members, suggesting the model scales well\n"
            "4. **30% is the sweet spot** for moderate risk — $1,020/encounter "
            "(7.2% reduction) with less operational change\n\n"
            "Would you like to calculate total annual savings, or run a "
            "**system_cost_roi** simulation to model net ROI including "
            "infrastructure investment?",
        ),
        (
            "user",
            "What are total annual savings for 50K members at 40%?",
        ),
        (
            "assistant",
            "Based on the simulation results for **50K members at 40% virtual "
            "penetration**:\n\n"
            "```\n"
            "Baseline cost (20%):    $1,098/encounter\n"
            "Target cost (40%):      $  952/encounter\n"
            "Savings per encounter:  $  146 (13.3%)\n"
            "\n"
            "Annual encounters:      50,000 × 2.5 = 125,000\n"
            "Annual gross savings:   125,000 × $146 = $18.3M\n"
            "```\n\n"
            "**Important caveats:**\n"
            "- These are **gross savings** before implementation costs\n"
            "- Technology platform, training, and change management are not included\n"
            "- Savings assume full adoption ramp is achieved within the modeled period\n"
            "- Actual encounter mix may shift as virtual care attracts different acuity\n\n"
            "I'd recommend running the **system_cost_roi** simulation next — it "
            "models net ROI including technology investment, phased rollout, and "
            "fixed-cost absorption. This will tell you whether the $18.3M in gross "
            "savings translates to a positive net return.\n\n"
            "Shall I set that up?",
        ),
    ]

    for role, content in messages:
        await db.execute(
            """INSERT INTO thread_messages (thread_id, role, content)
               VALUES ($1, $2, $3)""",
            thread_id, role, content,
        )

    logger.info(
        "Ali showcase seeded: analysis=%s, matrix=%s, thread=%s",
        analysis_id, matrix_id, thread_id,
    )


# =========================================================================
# Seed: Presenter's draft analysis (clean slate for live demo walkthrough)
# =========================================================================

async def _seed_presenter_draft():
    """Seed a fresh draft analysis for the demo presenter."""
    existing = await db.fetch_one(
        "SELECT id FROM analyses WHERE owner_email = $1 AND name = $2",
        PRESENTER_OWNER,
        PRESENTER_ANALYSIS_NAME,
    )
    if existing:
        logger.info("Presenter draft already exists, skipping")
        return

    logger.info("Seeding presenter draft for %s...", PRESENTER_OWNER)

    analysis = await db.fetch_one(
        """INSERT INTO analyses (name, description, owner_email, status)
           VALUES ($1, $2, $3, $4)
           RETURNING id""",
        PRESENTER_ANALYSIS_NAME,
        "Evaluating the financial impact of introducing virtual follow-up visits "
        "for postpartum care. Comparing blended cost per encounter across adoption "
        "rates and population sizes to build the business case for a pilot program.",
        PRESENTER_OWNER,
        "draft",
    )

    logger.info("Presenter draft seeded: analysis=%s", analysis["id"])


# =========================================================================
# Public API
# =========================================================================

async def seed_demo_data():
    """Seed all demo data. Idempotent — skips if exists."""
    await _seed_ali_showcase()
    await _seed_presenter_draft()
