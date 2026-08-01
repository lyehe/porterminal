"""Composition root - the ONLY place where dependencies are wired."""

import os
from pathlib import Path

from porterminal.application.ports import PTYFactory
from porterminal.application.services import (
    AgentTerminalService,
    ManagementService,
    SessionService,
    TabService,
    TerminalService,
)
from porterminal.config import ConfigStore
from porterminal.container import Container
from porterminal.domain import (
    PTYPort,
    SessionLimitChecker,
    ShellCommand,
    TabLimitChecker,
    TerminalDimensions,
    UserId,
)
from porterminal.infrastructure.config import ConfigService
from porterminal.infrastructure.registry import UserConnectionRegistry
from porterminal.infrastructure.repositories import InMemorySessionRepository, InMemoryTabRepository
from porterminal.infrastructure.web import AgentSessionConnection


def create_pty_factory(
    cwd: str | None = None,
) -> PTYFactory:
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


class PTYManagerAdapter(PTYPort):
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
    compose_mode_override: bool | None = None,
) -> Container:
    """Create the dependency container with all wired dependencies.

    This is the composition root - the single place where all
    dependencies are created and wired together.

    Args:
        config_path: Path to config file, or None to search standard locations.
        cwd: Working directory for PTY sessions.
        password_hash: Bcrypt hash of password for authentication (None = no auth).
        compose_mode_override: CLI override for compose mode (None = use config).

    Returns:
        Fully wired dependency container.
    """
    config_store = ConfigStore(config_path=config_path)
    config = config_store.load()

    shells = [ShellCommand.from_dict(shell.model_dump()) for shell in config.terminal.shells]
    server_host = config.server.host
    server_port = config.server.port
    default_cols = config.terminal.cols
    default_rows = config.terminal.rows
    default_shell_id = config.terminal.default_shell
    buttons = [button.model_dump() for button in config.buttons]
    max_auth_attempts = config.security.max_auth_attempts

    # UI defaults: CLI override > config file > default (False)
    compose_mode_default = (
        compose_mode_override if compose_mode_override is not None else config.ui.compose_mode
    )

    # Create repositories
    session_repository = InMemorySessionRepository()
    tab_repository = InMemoryTabRepository()

    # Create connection registry for broadcasting
    connection_registry = UserConnectionRegistry()

    # Create config service for runtime settings
    config_service = ConfigService(config_store)

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

    default_dimensions = TerminalDimensions(default_cols, default_rows)

    management_service = ManagementService(
        session_service=session_service,
        tab_service=tab_service,
        connection_registry=connection_registry,
        shell_provider=get_shell,
        default_dimensions=default_dimensions,
    )

    # Agent (MCP) terminal access. Agent sessions are created under the same
    # owner identity the phone uses ("local-user" in the default no-auth case)
    # so they appear as robot-badged tabs on the user's phone.
    agent_terminal_service = AgentTerminalService(
        session_service=session_service,
        tab_service=tab_service,
        terminal_service=terminal_service,
        connection_registry=connection_registry,
        connection_factory=lambda cols, rows: AgentSessionConnection(cols, rows),
        shell_provider=get_shell,
        default_dimensions=default_dimensions,
        owner_user_id=UserId("local-user"),
        reap_interval=float(os.environ.get("PORTERMINAL_AGENT_REAP_INTERVAL", "20")),
    )

    return Container(
        session_service=session_service,
        tab_service=tab_service,
        terminal_service=terminal_service,
        management_service=management_service,
        agent_terminal_service=agent_terminal_service,
        session_repository=session_repository,
        tab_repository=tab_repository,
        connection_registry=connection_registry,
        config_service=config_service,
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
        compose_mode_default=compose_mode_default,
    )
