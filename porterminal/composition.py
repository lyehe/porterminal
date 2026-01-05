"""Composition root - the ONLY place where dependencies are wired."""

from collections.abc import Callable
from pathlib import Path

import yaml

from porterminal.application.services import (
    ManagementService,
    SessionService,
    TabService,
    TerminalService,
)
from porterminal.config import find_config_file
from porterminal.container import Container
from porterminal.domain import (
    PTYPort,
    SessionLimitChecker,
    ShellCommand,
    TabLimitChecker,
    TerminalDimensions,
)
from porterminal.infrastructure.config import ShellDetector
from porterminal.infrastructure.registry import UserConnectionRegistry
from porterminal.infrastructure.repositories import InMemorySessionRepository, InMemoryTabRepository


def create_pty_factory(
    cwd: str | None = None,
) -> Callable[[ShellCommand, TerminalDimensions, str | None], PTYPort]:
    """Create a PTY factory function.

    This bridges the domain PTYPort interface with the existing
    infrastructure PTY implementation.
    """
    from porterminal.pty import SecurePTYManager, create_backend

    def factory(
        shell: ShellCommand,
        dimensions: TerminalDimensions,
        working_directory: str | None = None,
    ) -> PTYPort:
        # Use provided cwd or factory default
        effective_cwd = working_directory or cwd

        # Create backend
        backend = create_backend()

        # Create shell config compatible with existing infrastructure
        from porterminal.config import ShellConfig as LegacyShellConfig

        legacy_shell = LegacyShellConfig(
            name=shell.name,
            id=shell.id,
            command=shell.command,
            args=list(shell.args),
        )

        # Create manager (which implements PTY operations)
        # Environment sanitization is handled internally by SecurePTYManager
        manager = SecurePTYManager(
            backend=backend,
            shell_config=legacy_shell,
            cols=dimensions.cols,
            rows=dimensions.rows,
            cwd=effective_cwd,
        )

        manager.spawn()

        return PTYManagerAdapter(manager, dimensions)

    return factory


class PTYManagerAdapter:
    """Adapts SecurePTYManager to PTYPort interface."""

    def __init__(self, manager, dimensions: TerminalDimensions) -> None:
        self._manager = manager
        self._dimensions = dimensions

    def spawn(self) -> None:
        """Already spawned in factory."""
        pass

    def read(self, size: int = 4096) -> bytes:
        return self._manager.read(size)

    def write(self, data: bytes) -> None:
        self._manager.write(data)

    def resize(self, dimensions: TerminalDimensions) -> None:
        self._manager.resize(dimensions.cols, dimensions.rows)
        self._dimensions = dimensions

    def is_alive(self) -> bool:
        return self._manager.is_alive()

    def close(self) -> None:
        self._manager.close()

    @property
    def dimensions(self) -> TerminalDimensions:
        return self._dimensions


def create_container(
    config_path: Path | str | None = None,
    cwd: str | None = None,
    password_hash: bytes | None = None,
) -> Container:
    """Create the dependency container with all wired dependencies.

    This is the composition root - the single place where all
    dependencies are created and wired together.

    Args:
        config_path: Path to config file, or None to search standard locations.
        cwd: Working directory for PTY sessions.
        password_hash: Bcrypt hash of password for authentication (None = no auth).

    Returns:
        Fully wired dependency container.
    """
    # Load configuration
    if config_path is None:
        config_path = find_config_file()

    config_data: dict = {}
    if config_path is not None and Path(config_path).exists():
        with open(config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

    # Detect shells
    detector = ShellDetector()
    shells = detector.detect_shells()

    # Get config values with defaults
    server_data = config_data.get("server", {})
    terminal_data = config_data.get("terminal", {})
    security_data = config_data.get("security", {})

    server_host = server_data.get("host", "127.0.0.1")
    server_port = server_data.get("port", 8000)
    default_cols = terminal_data.get("cols", 120)
    default_rows = terminal_data.get("rows", 30)
    default_shell_id = terminal_data.get("default_shell") or detector.get_default_shell_id()
    buttons = config_data.get("buttons", [])
    max_auth_attempts = security_data.get("max_auth_attempts", 5)

    # Use configured shells if provided, otherwise use detected
    configured_shells = terminal_data.get("shells", [])
    if configured_shells:
        shells = [ShellCommand.from_dict(s) for s in configured_shells]

    # Create repositories
    session_repository = InMemorySessionRepository()
    tab_repository = InMemoryTabRepository()

    # Create connection registry for broadcasting
    connection_registry = UserConnectionRegistry()

    # Create PTY factory
    pty_factory = create_pty_factory(cwd)

    # Create services
    session_service = SessionService(
        repository=session_repository,
        pty_factory=pty_factory,
        limit_checker=SessionLimitChecker(),
        working_directory=cwd,
    )

    tab_service = TabService(
        repository=tab_repository,
        limit_checker=TabLimitChecker(),
    )

    terminal_service = TerminalService()

    # Create a shell provider closure for ManagementService
    def get_shell(shell_id: str | None) -> ShellCommand | None:
        target_id = shell_id or default_shell_id
        for shell in shells:
            if shell.id == target_id:
                return shell
        return shells[0] if shells else None

    management_service = ManagementService(
        session_service=session_service,
        tab_service=tab_service,
        connection_registry=connection_registry,
        shell_provider=get_shell,
        default_dimensions=TerminalDimensions(default_cols, default_rows),
    )

    return Container(
        session_service=session_service,
        tab_service=tab_service,
        terminal_service=terminal_service,
        management_service=management_service,
        session_repository=session_repository,
        tab_repository=tab_repository,
        connection_registry=connection_registry,
        pty_factory=pty_factory,
        available_shells=shells,
        default_shell_id=default_shell_id,
        server_host=server_host,
        server_port=server_port,
        default_cols=default_cols,
        default_rows=default_rows,
        buttons=buttons,
        cwd=cwd,
        password_hash=password_hash,
        max_auth_attempts=max_auth_attempts,
    )
