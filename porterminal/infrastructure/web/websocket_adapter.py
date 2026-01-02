"""FastAPI WebSocket adapter implementing ConnectionPort."""

import json
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from porterminal.application.ports import ConnectionPort


class FastAPIWebSocketAdapter(ConnectionPort):
    """Adapts FastAPI WebSocket to ConnectionPort protocol."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._closed = False

    async def send_output(self, data: bytes) -> None:
        """Send terminal output to client."""
        if not self._closed:
            try:
                await self._websocket.send_bytes(data)
            except Exception:
                self._closed = True

    async def send_message(self, message: dict[str, Any]) -> None:
        """Send JSON control message to client."""
        if not self._closed:
            try:
                await self._websocket.send_json(message)
            except Exception:
                self._closed = True

    async def receive(self) -> dict[str, Any] | bytes:
        """Receive message from client (binary or JSON).

        Returns:
            bytes for terminal input, dict for control messages.

        Raises:
            WebSocketDisconnect: If connection is closed.
        """
        try:
            message = await self._websocket.receive()
        except WebSocketDisconnect:
            self._closed = True
            raise

        if message.get("bytes"):
            return message["bytes"]
        elif message.get("text"):
            return json.loads(message["text"])

        # Handle disconnect message
        if message.get("type") == "websocket.disconnect":
            self._closed = True
            raise WebSocketDisconnect()

        raise ValueError(f"Unknown message type: {message.get('type')}")

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the connection."""
        if not self._closed:
            self._closed = True
            try:
                await self._websocket.close(code=code, reason=reason)
            except Exception:
                pass

    def is_connected(self) -> bool:
        """Check if connection is still open."""
        return not self._closed

    @property
    def websocket(self) -> WebSocket:
        """Get underlying WebSocket (for compatibility)."""
        return self._websocket
