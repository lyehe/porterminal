"""Shared route dependencies."""

from typing import cast

from starlette.requests import HTTPConnection

from porterminal.container import Container


def get_container(connection: HTTPConnection) -> Container:
    """Return the application container attached during composition/startup."""
    return cast(Container, connection.app.state.container)
