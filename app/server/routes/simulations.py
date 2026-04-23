"""Simulation browse + check + trigger routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from server.auth import User, get_current_user
from server.models.simulations import CheckRequest, SubmitRequest, TriggerRequest
from server.services import simulation_service

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.get("")
async def list_simulations(
    simulation_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    runs = await simulation_service.list_simulations(simulation_type, status, limit)
    return {"simulations": runs}


@router.get("/by-hash/{params_hash}")
async def get_simulation_by_hash(params_hash: str, user: User = Depends(get_current_user)):
    """Look up the most recent simulation by params_hash (stable across placeholder cleanup)."""
    run = await simulation_service.get_simulation_by_hash(params_hash)
    if not run:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return run


@router.get("/{run_id}")
async def get_simulation(run_id: str, user: User = Depends(get_current_user)):
    run = await simulation_service.get_simulation(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Simulation not found")

    results = await simulation_service.get_simulation_results(run_id)
    return {**run, "results": results}


@router.post("/check")
async def check_simulation(body: CheckRequest, user: User = Depends(get_current_user)):
    result = await simulation_service.check_simulation(
        body.simulation_type, body.parameters, body.num_simulations, body.seed
    )
    return result


@router.post("/trigger")
async def trigger_simulation(body: TriggerRequest, user: User = Depends(get_current_user)):
    result = await simulation_service.trigger_simulation(
        body.simulation_type, body.parameters, body.num_simulations, body.seed
    )
    return result


@router.post("/internal/submit-simulation")
async def submit_simulation_internal(body: SubmitRequest):
    """Called by UC trigger_simulation via http_request(). No user auth — App proxy handles it."""
    result = await simulation_service.submit_to_delta(
        body.simulation_type, body.parameters, int(body.num_simulations), int(body.seed)
    )
    return result
