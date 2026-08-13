"""Per-launch capability path for every remotely exposed endpoint."""

from __future__ import annotations

import re
import secrets
from urllib.parse import quote_from_bytes

from starlette.responses import RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

ACCESS_CODE_ENV = "PORTERMINAL_ACCESS_CODE"
_ACCESS_CODE_BYTES = 16  # 128 bits; token_urlsafe renders this as 22 URL-safe characters.
_ACCESS_CODE_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}")


def generate_access_code() -> str:
    """Return a new cryptographically random, URL-safe access code."""
    return secrets.token_urlsafe(_ACCESS_CODE_BYTES)


def validate_access_code(value: str) -> str:
    """Validate an access code before using it as a path segment."""
    if not _ACCESS_CODE_PATTERN.fullmatch(value):
        raise ValueError("Access code must be 16-128 URL-safe characters")
    return value


def access_path(access_code: str) -> str:
    """Return the normalized absolute path for an access code."""
    return f"/{validate_access_code(access_code)}"


def build_access_url(base_url: str, access_code: str) -> str:
    """Append the per-launch access path to a server or tunnel URL."""
    return f"{base_url.rstrip('/')}{access_path(access_code)}/"


def route_path(scope: Scope) -> str:
    """Return the request path relative to its current ASGI root path."""
    path = scope.get("path", "")
    root_path = scope.get("root_path", "").rstrip("/")
    if root_path and path.startswith(root_path):
        boundary = len(root_path)
        if len(path) == boundary:
            return "/"
        if path[boundary] == "/":
            return path[boundary:]
    return path or "/"


class AccessPathMiddleware:
    """Expose the wrapped ASGI app only below one unguessable path segment."""

    def __init__(self, app: ASGIApp, access_code: str) -> None:
        self.app = app
        self.access_code = validate_access_code(access_code)
        self.prefix = access_path(self.access_code)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        relative_path = route_path(scope)
        candidate = relative_path.removeprefix("/").partition("/")[0]
        candidate_bytes = candidate.encode("utf-8", errors="surrogatepass")
        expected_bytes = self.access_code.encode("ascii")
        if not secrets.compare_digest(candidate_bytes, expected_bytes):
            await self._reject(scope, receive, send)
            return

        if scope["type"] == "http" and relative_path == self.prefix:
            current_root = scope.get("root_path", "").rstrip("/")
            location = f"{current_root}{self.prefix}/"
            query = scope.get("query_string", b"")
            if query:
                # Quote from the original ASGI bytes so non-ASCII octets are
                # not decoded as Latin-1 and then re-encoded as UTF-8. Keep
                # valid query delimiters and existing percent escapes intact;
                # RedirectResponse performs the final whole-URL safety pass.
                encoded_query = quote_from_bytes(
                    query,
                    safe="/?:@[]!$&'()*+,;=%",
                )
                location = f"{location}?{encoded_query}"
            response = RedirectResponse(location, status_code=307)
            await response(scope, receive, send)
            return

        protected_scope = dict(scope)
        current_root = scope.get("root_path", "").rstrip("/")
        protected_scope["root_path"] = f"{current_root}{self.prefix}"
        await self.app(protected_scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        response = Response(
            status_code=404,
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
            },
        )
        await response(scope, receive, send)
