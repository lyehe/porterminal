"""Management and terminal WebSocket route handlers."""

import logging
from contextlib import suppress

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from porterminal.domain import UserId
from porterminal.infrastructure.auth import authenticate_connection, validate_auth_message
from porterminal.infrastructure.web.websocket_adapter import FastAPIWebSocketAdapter

from .common import get_container

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/management")
async def websocket_management(websocket: WebSocket):
    """Control plane for tab operations and state synchronization."""
    await websocket.accept()

    container = get_container(websocket)
    management_service = container.management_service
    connection_registry = container.connection_registry
    user_id = UserId(websocket.headers.get("cf-access-authenticated-user-email", "local-user"))
    connection = FastAPIWebSocketAdapter(websocket)

    logger.info(
        "Management WebSocket connected client=%s user_id=%s",
        getattr(websocket.client, "host", None),
        user_id,
    )

    try:
        if container.password_hash is not None:
            authenticated = await authenticate_connection(
                connection,
                container.password_hash,
                max_attempts=container.max_auth_attempts,
            )
            if not authenticated:
                await websocket.close(code=4001, reason="Auth failed")
                return

        await connection_registry.register(user_id, connection)

        if not hasattr(websocket.app.state, "_first_connection_signaled"):
            websocket.app.state._first_connection_signaled = True
            print("@@CONNECTED@@", flush=True)

        await connection.send_message(management_service.build_state_sync(user_id))

        while connection.is_connected():
            try:
                message = await connection.receive()
                if isinstance(message, dict):
                    await management_service.handle_message(user_id, connection, message)
            except WebSocketDisconnect:
                break
            except Exception as error:
                logger.warning("Management message error: %s", error)
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Management WebSocket error user_id=%s", user_id)
    finally:
        await connection_registry.unregister(user_id, connection)
        logger.info("Management WebSocket disconnected user_id=%s", user_id)


@router.websocket("/ws")
async def websocket_terminal(
    websocket: WebSocket,
    skip_buffer: str | None = Query(None),
    tab_id: str | None = Query(None),
):
    """Data plane for terminal I/O on a previously created tab."""
    logger.info(
        "WebSocket connect attempt client=%s tab_id=%s",
        getattr(websocket.client, "host", None),
        tab_id,
    )

    container = get_container(websocket)
    session_service = container.session_service
    tab_service = container.tab_service
    terminal_service = container.terminal_service
    connection_registry = container.connection_registry
    user_id = UserId(websocket.headers.get("cf-access-authenticated-user-email", "local-user"))

    if not tab_id:
        logger.warning("WebSocket rejected - no tab_id provided user_id=%s", user_id)
        await websocket.close(code=4000, reason="tab_id required")
        return

    tab = tab_service.get_tab(tab_id)
    if not tab or str(tab.user_id) != str(user_id):
        logger.warning(
            "WebSocket rejected - tab not found or unauthorized user_id=%s tab_id=%s",
            user_id,
            tab_id,
        )
        await websocket.close(code=4004, reason="Tab not found")
        return

    session = await session_service.reconnect_session(tab.session_id, user_id)
    if not session:
        logger.warning(
            "WebSocket rejected - session ended user_id=%s tab_id=%s session_id=%s",
            user_id,
            tab_id,
            tab.session_id,
        )
        closed_tab = tab_service.close_tab(tab_id, user_id)
        if closed_tab:
            await websocket.accept()
            ended_connection = FastAPIWebSocketAdapter(websocket)
            await connection_registry.register(user_id, ended_connection)
            await connection_registry.broadcast(
                user_id,
                tab_service.build_tab_closed_message(tab_id, "session_ended"),
            )
            await connection_registry.unregister(user_id, ended_connection)
        await websocket.close(code=4005, reason="Session ended")
        return

    await websocket.accept()
    connection = FastAPIWebSocketAdapter(websocket)
    logger.info(
        "WebSocket accepted client=%s user_id=%s tab_id=%s session_id=%s",
        getattr(websocket.client, "host", None),
        user_id,
        tab_id,
        session.session_id,
    )

    if container.password_hash is not None:
        if not await validate_auth_message(connection, container.password_hash):
            logger.warning("Terminal WebSocket auth failed user_id=%s", user_id)
            await websocket.close(code=4001, reason="Auth failed")
            return

    tab_service.touch_tab(tab_id, user_id)

    try:
        await connection_registry.register(user_id, connection)
        await connection.send_message(
            {
                "type": "session_info",
                "session_id": session.session_id,
                "shell": session.shell_id,
                "tab_id": tab.tab_id,
                "cols": session.dimensions.cols,
                "rows": session.dimensions.rows,
            }
        )
        await terminal_service.handle_session(
            session,
            connection,
            skip_buffer=bool(skip_buffer),
        )
    except WebSocketDisconnect:
        logger.info("Client disconnected user_id=%s tab_id=%s", user_id, tab_id)
    except Exception:
        logger.exception("WebSocket error user_id=%s tab_id=%s", user_id, tab_id)
        with suppress(Exception):
            await connection.close(code=1011)
    finally:
        await connection_registry.unregister(user_id, connection)
        session_service.disconnect_session(session.id)
        logger.info(
            "WebSocket handler finished user_id=%s tab_id=%s session_id=%s",
            user_id,
            tab_id,
            session.session_id,
        )
