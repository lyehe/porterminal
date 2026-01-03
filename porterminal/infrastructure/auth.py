"""Authentication utilities for WebSocket connections."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import TYPE_CHECKING

import bcrypt

if TYPE_CHECKING:
    from porterminal.application.ports import ConnectionPort

logger = logging.getLogger(__name__)


def _shutdown_server() -> None:
    """Trigger server shutdown due to auth failure."""
    import time

    # Print plain text - parent's drain_process_output handles formatting
    print("", flush=True)
    print("SECURITY WARNING", flush=True)
    print("Max authentication attempts exceeded.", flush=True)
    print("Your URL may have been leaked. Investigate before restarting.", flush=True)
    print("", flush=True)

    logger.warning(
        "SECURITY: Max authentication attempts exceeded. "
        "Shutting down server to prevent brute force attack."
    )

    # Delay to ensure message is visible before shutdown
    time.sleep(1)
    os.kill(os.getpid(), signal.SIGTERM)


async def authenticate_connection(
    connection: ConnectionPort,
    password_hash: bytes,
    max_attempts: int = 5,
    timeout_seconds: int = 30,
) -> bool:
    """Authenticate a WebSocket connection with password.

    Sends auth_required, waits for auth message, validates password.
    Returns True if authenticated, False otherwise.

    Args:
        connection: WebSocket connection adapter
        password_hash: bcrypt hash of the expected password
        max_attempts: Maximum number of password attempts
        timeout_seconds: Timeout for receiving auth message

    Returns:
        True if successfully authenticated, False otherwise
    """
    await connection.send_message({"type": "auth_required"})

    attempts = 0
    while attempts < max_attempts:
        try:
            message = await asyncio.wait_for(connection.receive(), timeout=timeout_seconds)
        except TimeoutError:
            await connection.send_message(
                {
                    "type": "auth_failed",
                    "attempts_remaining": 0,
                    "error": "Authentication timeout",
                }
            )
            return False

        if not isinstance(message, dict) or message.get("type") != "auth":
            await connection.send_message(
                {
                    "type": "error",
                    "error": "Authentication required",
                }
            )
            continue

        password = message.get("password", "")
        if bcrypt.checkpw(password.encode(), password_hash):
            await connection.send_message({"type": "auth_success"})
            return True

        attempts += 1
        remaining = max_attempts - attempts
        await connection.send_message(
            {
                "type": "auth_failed",
                "attempts_remaining": remaining,
                "error": "Invalid password" if remaining > 0 else "Too many failed attempts",
            }
        )

    # Max attempts exhausted - shutdown to prevent brute force
    _shutdown_server()
    return False


async def validate_auth_message(
    connection: ConnectionPort,
    password_hash: bytes,
    timeout_seconds: int = 10,
) -> bool:
    """Validate a single auth message from a connection.

    For terminal WebSocket where we expect auth as first message.

    Args:
        connection: WebSocket connection adapter
        password_hash: bcrypt hash of the expected password
        timeout_seconds: Timeout for receiving auth message

    Returns:
        True if valid, False otherwise
    """
    try:
        message = await asyncio.wait_for(connection.receive(), timeout=timeout_seconds)
    except TimeoutError:
        return False

    if not isinstance(message, dict) or message.get("type") != "auth":
        return False

    password = message.get("password", "")
    return bcrypt.checkpw(password.encode(), password_hash)
