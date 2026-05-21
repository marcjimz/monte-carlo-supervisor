"""Seed demo data — Ali's published showcase + presenter's draft walkthrough."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from server import db

logger = logging.getLogger(__name__)

# --- Ali's published showcase ---

DEMO_OWNER = "rob.allen@imail.org"
DEMO_ANALYSIS_NAME = "Encounter Margin Sensitivity Study"

# --- Presenter's draft walkthrough ---

PRESENTER_OWNER = "marcin.jimenez@databricks.com"
PRESENTER_ANALYSIS_NAME = "WH Penetration Impact Analysis"


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
        "Analyzing the sensitivity of encounter direct margin to growth rate and "
        "cost inflation assumptions. Builds a matrix of scenarios to identify "
        "the conditions under which margin erodes or improves over 12 months.",
        DEMO_OWNER,
        "published",
    )
    analysis_id = analysis["id"]

    # 2. Encounter margin sensitivity matrix (3x3: growth_rate vs cost_inflation)
    matrix = await db.fetch_one(
        """INSERT INTO analysis_matrices
           (analysis_id, name, description, simulation_type, row_parameter, row_values,
            col_parameter, col_values, base_parameters, output_metric,
            output_group_key, output_group_value, num_simulations, seed)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
           RETURNING id""",
        analysis_id,
        "Growth Rate vs Cost Inflation",
        "Direct margin per encounter across growth and inflation scenarios over 12 months",
        "encounter_margin",
        "growth_rate",
        json.dumps([0.01, 0.02, 0.03]),
        "cost_inflation",
        json.dumps([0.02, 0.035, 0.05]),
        json.dumps({"num_months": 12}),
        "simulated_direct_margin",
        "month",
        "M12",
        10000,
        42,
    )
    matrix_id = matrix["id"]

    # 3. Matrix cells — realistic results (margin improves with growth, erodes with inflation)
    cells = [
        # (growth_rate, cost_inflation, mean, p05, p50, p95)
        (0.01, 0.02, 4620000, 3200000, 4610000, 6050000),
        (0.01, 0.035, 4480000, 3100000, 4470000, 5870000),
        (0.01, 0.05, 4340000, 3000000, 4330000, 5690000),
        (0.02, 0.02, 4720000, 3270000, 4710000, 6180000),
        (0.02, 0.035, 4580000, 3170000, 4570000, 6000000),
        (0.02, 0.05, 4440000, 3070000, 4430000, 5820000),
        (0.03, 0.02, 4820000, 3340000, 4810000, 6310000),
        (0.03, 0.035, 4680000, 3240000, 4670000, 6130000),
        (0.03, 0.05, 4540000, 3140000, 4530000, 5950000),
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
        analysis_id, DEMO_OWNER, "Margin Sensitivity Hypothesis", "chat",
    )
    thread_id = thread["id"]

    messages = [
        (
            "user",
            "I want to understand how sensitive our encounter margin is to "
            "different growth and cost inflation assumptions over the next year.",
        ),
        (
            "assistant",
            "Great question! Let me set up a sensitivity analysis.\n\n"
            "I'll run an **encounter_margin** simulation matrix varying growth rate "
            "against cost inflation:\n\n"
            "| Parameter | Values |\n"
            "|---|---|\n"
            "| Growth Rate | 1%, 2%, 3% |\n"
            "| Cost Inflation | 2%, 3.5%, 5% |\n"
            "| Forecast Horizon | 12 months |\n"
            "| Trials per Cell | 10,000 |\n\n"
            "This gives us **9 scenarios** showing how margin evolves under "
            "different economic conditions.\n\n"
            "Shall I run this matrix?",
        ),
        (
            "user",
            "Yes, run it. I want to see which scenarios erode margin the most.",
        ),
        (
            "assistant",
            "The matrix has completed — all 9 cells finished (10,000 trials each). "
            "Here are the Month 12 direct margin results:\n\n"
            "### Direct Margin at Month 12\n\n"
            "| Growth \\ Inflation | 2% | 3.5% | 5% |\n"
            "|---|---|---|---|\n"
            "| **1%** | $4.6M | $4.5M | $4.3M |\n"
            "| **2%** | $4.7M | $4.6M | $4.4M |\n"
            "| **3%** | $4.8M | $4.7M | $4.5M |\n\n"
            "### Key Findings\n\n"
            "1. **Growth outpaces inflation** — even at 1% growth vs 5% inflation, "
            "margin stays positive at $4.3M\n"
            "2. **Sweet spot at 3% growth / 2% inflation** — highest margin at $4.8M, "
            "a 7% improvement over the worst case\n"
            "3. **Cost inflation is the bigger risk** — moving from 2% to 5% inflation "
            "erodes ~$280K regardless of growth rate\n"
            "4. **Confidence intervals are wide** — P05-P95 spans ~$2.8M, suggesting "
            "high variance in monthly outcomes\n\n"
            "Would you like to drill into the month-by-month trajectory for any "
            "specific scenario, or compare this with WH vs non-WH margin splits?",
        ),
        (
            "user",
            "What's the margin per encounter at 2% growth and 3.5% inflation?",
        ),
        (
            "assistant",
            "Based on the simulation at **2% growth / 3.5% inflation**:\n\n"
            "```\n"
            "Month 12 Direct Margin:     $4,580,000\n"
            "Month 12 Encounter Volume:  ~6,400\n"
            "Margin per Encounter:       ~$716\n"
            "```\n\n"
            "This is our baseline scenario (using config defaults). The margin "
            "per encounter stays relatively stable month over month because growth "
            "and inflation roughly offset each other at these rates.\n\n"
            "To understand the WH population's contribution to this margin, "
            "I'd recommend running a **wh_margin_comparison** simulation — it "
            "shows how WH encounters ($850/encounter) lift the blended average "
            "and what happens if we increase WH penetration from 35% to 50%.\n\n"
            "Want me to set that up?",
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
        "Evaluating the financial impact of increasing Women's Health program "
        "penetration from 35% to 50%. Comparing per-encounter margins between "
        "WH and non-WH populations to build the business case for expansion.",
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
