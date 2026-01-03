"""Shared test fixtures and configuration."""

from datetime import UTC, datetime

import pytest

from porterminal.domain import (
    EnvironmentRules,
    OutputBuffer,
    RateLimitConfig,
    Session,
    SessionId,
    ShellCommand,
    Tab,
    TabId,
    TabLimitChecker,
    TerminalDimensions,
    UserId,
)

# ============= Domain Fixtures =============


@pytest.fixture
def default_dimensions():
    """Default terminal dimensions."""
    return TerminalDimensions.default()


@pytest.fixture
def small_dimensions():
    """Small terminal dimensions."""
    return TerminalDimensions(cols=80, rows=24)


@pytest.fixture
def session_id():
    """Sample session ID."""
    return SessionId("test-session-123")


@pytest.fixture
def user_id():
    """Sample user ID."""
    return UserId("test-user")


@pytest.fixture
def local_user_id():
    """Local user ID."""
    return UserId.local_user()


@pytest.fixture
def bash_shell():
    """Bash shell command."""
    return ShellCommand(
        id="bash",
        name="Bash",
        command="/bin/bash",
        args=("--login",),
    )


@pytest.fixture
def powershell_shell():
    """PowerShell shell command."""
    return ShellCommand(
        id="powershell",
        name="PowerShell",
        command="powershell.exe",
        args=("-NoLogo",),
    )


@pytest.fixture
def rate_limit_config():
    """Default rate limit config."""
    return RateLimitConfig()


@pytest.fixture
def strict_rate_limit_config():
    """Strict rate limit config for testing."""
    return RateLimitConfig(rate=10.0, burst=20)


@pytest.fixture
def environment_rules():
    """Default environment rules."""
    return EnvironmentRules()


@pytest.fixture
def output_buffer():
    """Empty output buffer."""
    return OutputBuffer()


# ============= Mock Fixtures =============


class FakeClock:
    """Fake clock for testing rate limiter."""

    def __init__(self, start_time: float = 0.0):
        self._time = start_time

    def now(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += seconds


@pytest.fixture
def fake_clock():
    """Fake clock starting at 0."""
    return FakeClock()


class FakePTY:
    """Fake PTY for testing."""

    def __init__(self, dimensions: TerminalDimensions):
        self._dimensions = dimensions
        self._alive = True
        self._output_queue: list[bytes] = []
        self._input_received: list[bytes] = []
        self._spawned = False

    def spawn(self) -> None:
        self._spawned = True

    def read(self, size: int = 4096) -> bytes:
        if self._output_queue:
            return self._output_queue.pop(0)
        return b""

    def write(self, data: bytes) -> None:
        self._input_received.append(data)

    def resize(self, dimensions: TerminalDimensions) -> None:
        self._dimensions = dimensions

    def is_alive(self) -> bool:
        return self._alive

    def close(self) -> None:
        self._alive = False

    @property
    def dimensions(self) -> TerminalDimensions:
        return self._dimensions

    # Test helpers
    def add_output(self, data: bytes) -> None:
        """Add data to be returned by read()."""
        self._output_queue.append(data)

    def kill(self) -> None:
        """Simulate PTY death."""
        self._alive = False

    def get_input(self) -> list[bytes]:
        """Get all input received."""
        return self._input_received


@pytest.fixture
def fake_pty(default_dimensions):
    """Fake PTY for testing."""
    return FakePTY(default_dimensions)


def create_fake_pty_factory(fake_pty_instance: FakePTY):
    """Create a PTY factory that returns the given fake PTY."""

    def factory(shell, dimensions, env, cwd=None):
        fake_pty_instance._dimensions = dimensions
        fake_pty_instance.spawn()
        return fake_pty_instance

    return factory


@pytest.fixture
def fake_pty_factory(fake_pty):
    """Factory that creates fake PTYs."""
    return create_fake_pty_factory(fake_pty)


# ============= Session Fixtures =============


@pytest.fixture
def sample_session(session_id, user_id, default_dimensions, fake_pty):
    """Sample session for testing."""
    now = datetime.now(UTC)
    session = Session(
        id=session_id,
        user_id=user_id,
        shell_id="bash",
        dimensions=default_dimensions,
        created_at=now,
        last_activity=now,
        pty_handle=fake_pty,
        connected_clients=1,  # Start with one connected client
    )
    return session


# ============= Repository Fixtures =============


@pytest.fixture
def session_repository():
    """Empty in-memory session repository."""
    from porterminal.infrastructure.repositories import InMemorySessionRepository

    return InMemorySessionRepository()


# ============= Tab Fixtures =============


@pytest.fixture
def tab_id():
    """Sample tab ID."""
    return TabId("test-tab-123")


@pytest.fixture
def sample_tab(tab_id, user_id, session_id):
    """Sample tab for testing."""
    now = datetime.now(UTC)
    return Tab(
        id=tab_id,
        user_id=user_id,
        session_id=session_id,
        shell_id="bash",
        name="Test Tab",
        created_at=now,
        last_accessed=now,
    )


@pytest.fixture
def tab_repository():
    """Empty in-memory tab repository."""
    from porterminal.infrastructure.repositories import InMemoryTabRepository

    return InMemoryTabRepository()


@pytest.fixture
def tab_limit_checker():
    """Default tab limit checker."""
    return TabLimitChecker()


# ============= Mock Connection Fixtures =============


class MockConnection:
    """Mock implementation of ConnectionPort protocol."""

    def __init__(self):
        self.sent_messages: list[dict] = []
        self._is_connected = True

    async def send_message(self, message: dict) -> None:
        self.sent_messages.append(message)

    async def send_output(self, data: bytes) -> None:
        pass

    async def receive(self) -> dict | bytes:
        return b""

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self._is_connected = False

    def is_connected(self) -> bool:
        return self._is_connected


@pytest.fixture
def mock_connection():
    """Mock connection for testing."""
    return MockConnection()


@pytest.fixture
def connection_registry():
    """Empty user connection registry."""
    from porterminal.infrastructure.registry import UserConnectionRegistry

    return UserConnectionRegistry()


# ============= Async Fixtures =============


@pytest.fixture
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()
