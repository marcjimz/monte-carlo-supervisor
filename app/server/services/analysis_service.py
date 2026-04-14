"""Analysis CRUD + ACL service."""

from __future__ import annotations

from uuid import UUID

from server import db


async def create_analysis(name: str, description: str | None, owner_email: str) -> dict:
    """Create a new analysis."""
    row = await db.fetch_one(
        """INSERT INTO analyses (name, description, owner_email)
           VALUES ($1, $2, $3)
           RETURNING *""",
        name, description, owner_email,
    )
    return row


async def list_analyses(user_email: str) -> list[dict]:
    """List analyses visible to user (owned, collaborator, or published)."""
    return await db.fetch_all(
        """SELECT DISTINCT a.*
           FROM analyses a
           LEFT JOIN analysis_collaborators c ON c.analysis_id = a.id
           WHERE a.owner_email = $1
              OR c.user_email = $1
              OR a.status = 'published'
           ORDER BY a.updated_at DESC""",
        user_email,
    )


async def get_analysis(analysis_id: UUID) -> dict | None:
    """Get a single analysis."""
    return await db.fetch_one(
        "SELECT * FROM analyses WHERE id = $1",
        analysis_id,
    )


async def update_analysis(analysis_id: UUID, name: str | None, description: str | None) -> dict | None:
    """Update analysis name and/or description."""
    fields = []
    args = []
    idx = 1

    if name is not None:
        fields.append(f"name = ${idx}")
        args.append(name)
        idx += 1

    if description is not None:
        fields.append(f"description = ${idx}")
        args.append(description)
        idx += 1

    if not fields:
        return await get_analysis(analysis_id)

    fields.append("updated_at = NOW()")
    args.append(analysis_id)

    return await db.fetch_one(
        f"UPDATE analyses SET {', '.join(fields)} WHERE id = ${idx} RETURNING *",
        *args,
    )


async def delete_analysis(analysis_id: UUID, owner_email: str) -> bool:
    """Delete an analysis (owner only)."""
    result = await db.execute(
        "DELETE FROM analyses WHERE id = $1 AND owner_email = $2",
        analysis_id, owner_email,
    )
    return result != "DELETE 0"


async def publish_analysis(analysis_id: UUID) -> dict | None:
    """Set analysis status to published."""
    return await db.fetch_one(
        "UPDATE analyses SET status = 'published', updated_at = NOW() WHERE id = $1 RETURNING *",
        analysis_id,
    )


async def unpublish_analysis(analysis_id: UUID) -> dict | None:
    """Set analysis status back to draft."""
    return await db.fetch_one(
        "UPDATE analyses SET status = 'draft', updated_at = NOW() WHERE id = $1 RETURNING *",
        analysis_id,
    )


async def can_access(analysis_id: UUID, user_email: str) -> bool:
    """Check if a user can access an analysis."""
    row = await db.fetch_one(
        """SELECT 1 FROM analyses a
           LEFT JOIN analysis_collaborators c ON c.analysis_id = a.id
           WHERE a.id = $1
             AND (a.owner_email = $2 OR c.user_email = $2 OR a.status = 'published')""",
        analysis_id, user_email,
    )
    return row is not None


async def can_edit(analysis_id: UUID, user_email: str) -> bool:
    """Check if a user can edit an analysis (owner or editor)."""
    row = await db.fetch_one(
        """SELECT 1 FROM analyses a
           LEFT JOIN analysis_collaborators c ON c.analysis_id = a.id AND c.role = 'editor'
           WHERE a.id = $1
             AND (a.owner_email = $2 OR c.user_email = $2)""",
        analysis_id, user_email,
    )
    return row is not None


# --- Collaborators ---

async def add_collaborator(analysis_id: UUID, user_email: str, role: str = "viewer") -> dict:
    return await db.fetch_one(
        """INSERT INTO analysis_collaborators (analysis_id, user_email, role)
           VALUES ($1, $2, $3)
           ON CONFLICT (analysis_id, user_email) DO UPDATE SET role = $3
           RETURNING *""",
        analysis_id, user_email, role,
    )


async def remove_collaborator(analysis_id: UUID, user_email: str) -> bool:
    result = await db.execute(
        "DELETE FROM analysis_collaborators WHERE analysis_id = $1 AND user_email = $2",
        analysis_id, user_email,
    )
    return result != "DELETE 0"


async def list_collaborators(analysis_id: UUID) -> list[dict]:
    return await db.fetch_all(
        "SELECT * FROM analysis_collaborators WHERE analysis_id = $1",
        analysis_id,
    )


# --- Linked simulations ---

async def link_simulation(analysis_id: UUID, run_id: str, added_by: str) -> dict:
    return await db.fetch_one(
        """INSERT INTO analysis_simulations (analysis_id, run_id, added_by)
           VALUES ($1, $2, $3)
           ON CONFLICT (analysis_id, run_id) DO NOTHING
           RETURNING *""",
        analysis_id, run_id, added_by,
    )


async def unlink_simulation(analysis_id: UUID, run_id: str) -> bool:
    result = await db.execute(
        "DELETE FROM analysis_simulations WHERE analysis_id = $1 AND run_id = $2",
        analysis_id, run_id,
    )
    return result != "DELETE 0"


async def list_analysis_simulations(analysis_id: UUID) -> list[dict]:
    return await db.fetch_all(
        "SELECT * FROM analysis_simulations WHERE analysis_id = $1 ORDER BY created_at DESC",
        analysis_id,
    )
