"""Matrix CRUD + execute + status polling routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from server.auth import User, get_current_user
from server.models.matrices import MatrixCreate
from server.services import matrix_service

router = APIRouter(tags=["matrices"])


@router.get("/analyses/{analysis_id}/matrices")
async def list_matrices(analysis_id: UUID, user: User = Depends(get_current_user)):
    matrices = await matrix_service.list_matrices(analysis_id)
    return {"matrices": matrices}


@router.post("/analyses/{analysis_id}/matrices", status_code=201)
async def create_matrix(
    analysis_id: UUID, body: MatrixCreate, user: User = Depends(get_current_user)
):
    matrix = await matrix_service.create_matrix(
        analysis_id=analysis_id,
        name=body.name,
        simulation_type=body.simulation_type,
        row_parameter=body.row_parameter,
        row_values=body.row_values,
        col_parameter=body.col_parameter,
        col_values=body.col_values,
        base_parameters=body.base_parameters,
        output_metric=body.output_metric,
        output_group_key=body.output_group_key,
        output_group_value=body.output_group_value,
        num_simulations=body.num_simulations,
        seed=body.seed,
    )
    return matrix


@router.get("/matrices/{matrix_id}")
async def get_matrix(matrix_id: UUID, user: User = Depends(get_current_user)):
    matrix = await matrix_service.get_matrix(matrix_id)
    if not matrix:
        raise HTTPException(status_code=404, detail="Matrix not found")
    return matrix


@router.delete("/matrices/{matrix_id}", status_code=204)
async def delete_matrix(matrix_id: UUID, user: User = Depends(get_current_user)):
    deleted = await matrix_service.delete_matrix(matrix_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Matrix not found")


@router.post("/matrices/{matrix_id}/run")
async def run_matrix(matrix_id: UUID, user: User = Depends(get_current_user)):
    result = await matrix_service.run_matrix(matrix_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/matrices/{matrix_id}/cells/{cell_id}/run")
async def run_cell(
    matrix_id: UUID, cell_id: UUID, user: User = Depends(get_current_user)
):
    result = await matrix_service.run_cell(matrix_id, cell_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/matrices/{matrix_id}/status")
async def poll_status(matrix_id: UUID, user: User = Depends(get_current_user)):
    matrix = await matrix_service.poll_status(matrix_id)
    if not matrix:
        raise HTTPException(status_code=404, detail="Matrix not found")
    return matrix
