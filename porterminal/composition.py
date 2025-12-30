"""Composition root - the ONLY place where dependencies are wired."""

from collections.abc import Callable
from pathlib import Path

from porterminal.application.services import SessionService, TerminalService
from porterminal.container import Container
from porterminal.domain import (
    EnvironmentRules,
    EnvironmentSanitizer,
    PTYPort,
    SessionLimitChecker,
    ShellCommand,
    TerminalDimensions,
)
from porterminal.infrastructure.config import ShellDetector, YAMLConfigLoader
from porterminal.infrastructure.repositories import InMemorySessionRepository


def create_pty_factory(
    cwd: str | None = None,
) -> Callable[[ShellCommand, TerminalDimensions, dict[str, str], str | None], PTYPort]:
    """Create a PTY factory function.

    This bridges the domain PTYPort interface with the existing
    infrastructure PTY implementation.
    """
    from porterminal.pty import SecurePTYManager, create_backend

    def factory(
        shell: ShellCommand,
        dimensions: TerminalDimensions,
        environment: dict[str, str],
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
        manager = SecurePTYManager(
            backend=backend,
            shell_config=legacy_shell,
            cols=dimensions.cols,
            rows=dimensions.rows,
            cwd=effective_cwd,
        )

        # Spawn with environment (manager handles sanitization internally,
        # but we pass our sanitized env to be safe)
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
    config_path: Path | str = "config.yaml",
    cwd: str | None = None,
) -> Container:
    """Create the dependency container with all wired dependencies.

    This is the composition root - the single place where all
    dependencies are created and wired together.

    Args:
        config_path: Path to config file.
        cwd: Working directory for PTY sessions.

    Returns:
        Fully wired dependency container.
    """
    # Load configuration
    loader = YAMLConfigLoader(config_path)
    config_data = loader.load()

    # Detect shells
    detector = ShellDetector()
    shells = detector.detect_shells()

    # Get config values with defaults
    server_data = config_data.get("server", {})
    terminal_data = config_data.get("terminal", {})

    server_host = server_data.get("host", "127.0.0.1")
    server_port = server_data.get("port", 8000)
    default_cols = terminal_data.get("cols", 120)
    default_rows = terminal_data.get("rows", 30)
    default_shell_id = terminal_data.get("default_shell") or detector.get_default_shell_id()
    buttons = config_data.get("buttons", [])

    # Use configured shells if provided, otherwise use detected
    configured_shells = terminal_data.get("shells", [])
    if configured_shells:
        shells = [ShellCommand.from_dict(s) for s in configured_shells]

    # Create repository
    session_repository = InMemorySessionRepository()

    # Create PTY factory
    pty_factory = create_pty_factory(cwd)

    # Create services
    session_service = SessionService(
        repository=session_repository,
        pty_factory=pty_factory,
        limit_checker=SessionLimitChecker(),
        environment_sanitizer=EnvironmentSanitizer(EnvironmentRules()),
        working_directory=cwd,
    )

    terminal_service = TerminalService()

    return Container(
        session_service=session_service,
        terminal_service=terminal_service,
        session_repository=session_repository,
        pty_factory=pty_factory,
        available_shells=shells,
        default_shell_id=default_shell_id,
        server_host=server_host,
        server_port=server_port,
        default_cols=default_cols,
        default_rows=default_rows,
        buttons=buttons,
        cwd=cwd,
    )
