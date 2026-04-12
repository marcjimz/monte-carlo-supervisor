"""Analysis CRUD + collaborators + publish routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from server.auth import User, get_current_user
from server.models.analyses import (
    AnalysisCreate,
    AnalysisUpdate,
    CollaboratorAdd,
)
from server.services import analysis_service

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.get("")
async def list_analyses(user: User = Depends(get_current_user)):
    analyses = await analysis_service.list_analyses(user.email)
    return {"analyses": analyses}


@router.post("", status_code=201)
async def create_analysis(body: AnalysisCreate, user: User = Depends(get_current_user)):
    analysis = await analysis_service.create_analysis(body.name, body.description, user.email)
    return analysis


@router.get("/{analysis_id}")
async def get_analysis(analysis_id: UUID, user: User = Depends(get_current_user)):
    if not await analysis_service.can_access(analysis_id, user.email):
        raise HTTPException(status_code=403, detail="Access denied")

    analysis = await analysis_service.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    collaborators = await analysis_service.list_collaborators(analysis_id)
    simulations = await analysis_service.list_analysis_simulations(analysis_id)

    return {**analysis, "collaborators": collaborators, "simulations": simulations}


@router.patch("/{analysis_id}")
async def update_analysis(
    analysis_id: UUID, body: AnalysisUpdate, user: User = Depends(get_current_user)
):
    if not await analysis_service.can_edit(analysis_id, user.email):
        raise HTTPException(status_code=403, detail="Edit access denied")

    analysis = await analysis_service.update_analysis(analysis_id, body.name, body.description)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@router.delete("/{analysis_id}", status_code=204)
async def delete_analysis(analysis_id: UUID, user: User = Depends(get_current_user)):
    deleted = await analysis_service.delete_analysis(analysis_id, user.email)
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis not found or not owner")


@router.post("/{analysis_id}/publish")
async def publish_analysis(analysis_id: UUID, user: User = Depends(get_current_user)):
    if not await analysis_service.can_edit(analysis_id, user.email):
        raise HTTPException(status_code=403, detail="Edit access denied")

    analysis = await analysis_service.publish_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


# --- Collaborators ---


@router.post("/{analysis_id}/collaborators", status_code=201)
async def add_collaborator(
    analysis_id: UUID, body: CollaboratorAdd, user: User = Depends(get_current_user)
):
    if not await analysis_service.can_edit(analysis_id, user.email):
        raise HTTPException(status_code=403, detail="Edit access denied")

    collab = await analysis_service.add_collaborator(analysis_id, body.user_email, body.role)
    return collab


@router.delete("/{analysis_id}/collaborators/{email}", status_code=204)
async def remove_collaborator(
    analysis_id: UUID, email: str, user: User = Depends(get_current_user)
):
    if not await analysis_service.can_edit(analysis_id, user.email):
        raise HTTPException(status_code=403, detail="Edit access denied")

    await analysis_service.remove_collaborator(analysis_id, email)


# --- Linked simulations ---


@router.post("/{analysis_id}/simulations", status_code=201)
async def link_simulation(
    analysis_id: UUID, body: dict, user: User = Depends(get_current_user)
):
    if not await analysis_service.can_edit(analysis_id, user.email):
        raise HTTPException(status_code=403, detail="Edit access denied")

    run_id = body.get("run_id")
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id required")

    result = await analysis_service.link_simulation(analysis_id, run_id, user.email)
    return result


@router.delete("/{analysis_id}/simulations/{run_id}", status_code=204)
async def unlink_simulation(
    analysis_id: UUID, run_id: str, user: User = Depends(get_current_user)
):
    if not await analysis_service.can_edit(analysis_id, user.email):
        raise HTTPException(status_code=403, detail="Edit access denied")

    await analysis_service.unlink_simulation(analysis_id, run_id)
