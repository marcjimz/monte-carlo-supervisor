"""Thread CRUD + message routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from server.auth import User, get_current_user
from server.models.threads import MessageCreate, ThreadCreate, ThreadUpdate
from server.services import thread_service

router = APIRouter(tags=["threads"])


@router.get("/analyses/{analysis_id}/threads")
async def list_threads(analysis_id: UUID, user: User = Depends(get_current_user)):
    threads = await thread_service.list_threads(analysis_id)
    return {"threads": threads}


@router.post("/analyses/{analysis_id}/threads", status_code=201)
async def create_thread(
    analysis_id: UUID, body: ThreadCreate, user: User = Depends(get_current_user)
):
    thread = await thread_service.create_thread(
        analysis_id, user.email, body.title, body.icon
    )
    return thread


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: UUID, user: User = Depends(get_current_user)):
    thread = await thread_service.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@router.patch("/threads/{thread_id}")
async def update_thread(
    thread_id: UUID, body: ThreadUpdate, user: User = Depends(get_current_user)
):
    thread = await thread_service.update_thread(thread_id, body.title, body.icon)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: UUID, user: User = Depends(get_current_user)):
    deleted = await thread_service.delete_thread(thread_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")


@router.post("/threads/{thread_id}/messages")
async def send_message(
    thread_id: UUID, body: MessageCreate, user: User = Depends(get_current_user)
):
    result = await thread_service.send_message(thread_id, body.content)
    return result


@router.post("/threads/{thread_id}/messages/stream")
async def send_message_stream(
    thread_id: UUID, body: MessageCreate, user: User = Depends(get_current_user)
):
    return StreamingResponse(
        thread_service.send_message_stream(thread_id, body.content),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
