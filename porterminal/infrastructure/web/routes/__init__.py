"""HTTP and WebSocket route groups."""

from .agent import router as agent_router
from .discovery import STATIC_DIR
from .discovery import router as discovery_router
from .settings import router as settings_router
from .websockets import router as websocket_router

__all__ = [
    "STATIC_DIR",
    "agent_router",
    "discovery_router",
    "settings_router",
    "websocket_router",
]
