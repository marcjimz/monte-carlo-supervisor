"""Distribution service — query fitted distribution specs from Lakebase."""

from __future__ import annotations

import json
import logging

from server import db

logger = logging.getLogger(__name__)


async def list_distribution_specs() -> list[dict]:
    """List all distribution specs from Lakebase sync table."""
    rows = await db.fetch_all(
        """SELECT s.simulation_type, s.distribution_name, s.version,
                  s.spec, s.fit_metadata, s.created_at
           FROM sync_distribution_specs s
           INNER JOIN (
               SELECT simulation_type, distribution_name, MAX(version) AS max_version
               FROM sync_distribution_specs
               GROUP BY simulation_type, distribution_name
           ) latest ON s.simulation_type = latest.simulation_type
                    AND s.distribution_name = latest.distribution_name
                    AND s.version = latest.max_version
           ORDER BY s.simulation_type, s.distribution_name"""
    )

    result = []
    for row in rows:
        r = dict(row)
        if r.get("spec"):
            try:
                r["spec"] = json.loads(r["spec"])
            except (json.JSONDecodeError, TypeError):
                pass
        if r.get("fit_metadata"):
            try:
                r["fit_metadata"] = json.loads(r["fit_metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        result.append(r)

    return result
