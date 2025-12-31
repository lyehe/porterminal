"""Dependency container - holds all wired dependencies."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from porterminal.application.services import (
    ManagementService,
    SessionService,
    TabService,
    TerminalService,
)
from porterminal.domain import PTYPort, ShellCommand, TerminalDimensions
from porterminal.domain.ports import SessionRepository, TabRepository

if TYPE_CHECKING:
    from porterminal.infrastructure.registry import UserConnectionRegistry


@dataclass(frozen=True)
class Container:
    """Immutable dependency container.

    All dependencies are wired at startup and cannot be modified.
    This ensures thread-safety and predictable behavior.
    """

    # Services
    session_service: SessionService
    tab_service: TabService
    terminal_service: TerminalService
    management_service: ManagementService

    # Repositories
    session_repository: SessionRepository
    tab_repository: TabRepository

    # Registry for broadcasting
    connection_registry: "UserConnectionRegistry"

    # Factories
    pty_factory: Callable[[ShellCommand, TerminalDimensions, dict[str, str], str | None], PTYPort]

    # Configuration
    available_shells: list[ShellCommand]
    default_shell_id: str
    server_host: str
    server_port: int
    default_cols: int
    default_rows: int
    buttons: list[dict]

    # Working directory
    cwd: str | None = None

    def get_shell(self, shell_id: str | None = None) -> ShellCommand | None:
        """Get shell by ID or default."""
        target_id = shell_id or self.default_shell_id

        for shell in self.available_shells:
            if shell.id == target_id:
                return shell

        # Return first available if target not found
        return self.available_shells[0] if self.available_shells else None
