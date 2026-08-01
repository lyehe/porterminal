"""REST fallback routes for agent terminal sessions."""

import uuid

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .common import get_container

router = APIRouter(tags=["agent"])


class AgentRunRequest(BaseModel):
    command: str
    timeout: float = 30
    session_id: str | None = None


class AgentKeysRequest(BaseModel):
    session_id: str
    text: str


class AgentSignalRequest(BaseModel):
    session_id: str
    signal: str


def _new_session_id() -> str:
    return f"rest-{uuid.uuid4().hex}"


def _valid_session_id(session_id: str | None) -> bool:
    return bool(session_id and session_id.startswith("rest-"))


def _bad_session_id() -> JSONResponse:
    return JSONResponse(
        {"error": "session_id must come from a prior REST agent API response"},
        status_code=400,
    )


@router.post("/api/agent/run")
async def agent_rest_run(body: AgentRunRequest, request: Request):
    """Run a command through the REST fallback agent API."""
    command = body.command.strip()
    if not command:
        return JSONResponse({"error": "command is required"}, status_code=400)

    session_id = body.session_id or _new_session_id()
    if not _valid_session_id(session_id):
        return _bad_session_id()

    result = await get_container(request).agent_terminal_service.run_command(
        session_id,
        command,
        body.timeout,
        reap_on_disconnect=False,
    )
    return {"session_id": session_id, **result}


@router.get("/api/agent/screen")
async def agent_rest_screen(request: Request, session_id: str = Query(...)):
    """Read the current rendered screen for a REST agent session."""
    if not _valid_session_id(session_id):
        return _bad_session_id()

    result = await get_container(request).agent_terminal_service.read_screen(
        session_id,
        reap_on_disconnect=False,
    )
    return {"session_id": session_id, **result}


@router.post("/api/agent/keys")
async def agent_rest_keys(body: AgentKeysRequest, request: Request):
    """Send raw keystrokes to a REST agent session."""
    if not _valid_session_id(body.session_id):
        return _bad_session_id()

    result = await get_container(request).agent_terminal_service.send_keys(
        body.session_id,
        body.text,
        reap_on_disconnect=False,
    )
    return {"session_id": body.session_id, **result}


@router.post("/api/agent/signal")
async def agent_rest_signal(body: AgentSignalRequest, request: Request):
    """Send a control signal to a REST agent session."""
    if not _valid_session_id(body.session_id):
        return _bad_session_id()

    result = await get_container(request).agent_terminal_service.send_signal(
        body.session_id,
        body.signal,
        reap_on_disconnect=False,
    )
    return {"session_id": body.session_id, **result}


@router.delete("/api/agent/session")
async def agent_rest_close(request: Request, session_id: str = Query(...)):
    """Close a REST agent session and its visible agent tab."""
    if not _valid_session_id(session_id):
        return _bad_session_id()

    closed = await get_container(request).agent_terminal_service.close_session(session_id)
    return {"session_id": session_id, "closed": closed}
