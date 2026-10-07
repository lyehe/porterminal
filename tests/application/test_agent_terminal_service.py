"""Regression tests for command output captured from an agent's PTY."""

import asyncio
import re

import pytest

from porterminal.application.services import agent_terminal_service as agent_module
from porterminal.application.services.agent_terminal_service import AgentTerminalService
from porterminal.application.services.session_service import SessionService
from porterminal.application.services.tab_service import TabService
from porterminal.application.services.terminal_service import TerminalService
from porterminal.domain import TokenBucketRateLimiter
from porterminal.infrastructure.web.agent_connection import AgentSessionConnection


async def test_agent_terminal_answers_cursor_position_queries():
    connection = AgentSessionConnection(80, 24)
    await connection.send_output(b"hello\x1b[6n")

    assert await asyncio.wait_for(connection.receive(), 1) == b"\x1b[1;6R"
    assert connection.capture_since(0) == b"hello\x1b[6n"


async def test_device_attribute_reply_reaches_the_shell(
    sample_session, fake_pty, rate_limit_config, fake_clock
):
    connection = AgentSessionConnection(80, 24)
    await connection.send_output(b"\x1b[0c")
    reply = await asyncio.wait_for(connection.receive(), 1)
    assert reply == b"\x1b[?6c"

    await TerminalService()._handle_binary_input(
        sample_session,
        reply,
        TokenBucketRateLimiter(rate_limit_config, fake_clock),
        connection,
    )

    assert fake_pty.get_input() == [reply]


@pytest.mark.parametrize(
    "probe_echo",
    [
        "printf '{marker}%d\\n' \"$?\"",
        "echo {marker}%errorlevel%",
        'Write-Output "{marker}$LASTEXITCODE"',
    ],
    ids=["posix", "cmd", "powershell"],
)
@pytest.mark.parametrize("output_before_probe", [True, False], ids=["normal", "early-echo"])
def test_command_output_survives_probe_echo_order(probe_echo, output_before_probe):
    marker = "PTNXregression"
    command = "echo AGENT_OK"
    probe = probe_echo.format(marker=marker)
    lines = [f"prompt> {command}"]
    if output_before_probe:
        lines.extend(["AGENT_OK", f"prompt> {probe}"])
    else:
        # A terminal can echo both queued lines before the shell runs either.
        lines.extend([f"prompt> {probe}", "AGENT_OK"])

    output = AgentTerminalService._extract_output("\n".join(lines), command, marker)

    assert output == "AGENT_OK"


def test_command_output_repeating_the_command_is_preserved_after_probe_echo():
    marker = "PTNXregression"
    command = "cat log.txt"
    segment = (
        f"prompt> {command}\nprompt> printf '{marker}%d\\n' \"$?\"\ncat log.txt\nanother line\n"
    )

    output = AgentTerminalService._extract_output(segment, command, marker)

    assert output == "cat log.txt\nanother line"


@pytest.fixture
async def startup_service(
    session_repository,
    tab_repository,
    fake_pty_factory,
    connection_registry,
    bash_shell,
    default_dimensions,
    user_id,
):
    terminal = TerminalService()
    sessions = SessionService(
        session_repository,
        fake_pty_factory,
        on_session_created=terminal.start_session,
        on_session_closing=terminal.stop_session,
    )

    class StartupConnection(AgentSessionConnection):
        def __init__(self):
            super().__init__(default_dimensions.cols, default_dimensions.rows)
            self.probe_seen = asyncio.Event()
            self.marker = b""

        async def push_input(self, data: bytes) -> None:
            if data.startswith(b"printf "):
                self.marker = b"".join(re.findall(rb"'([^']*)'", data)[1:])
                # Echoing the probe is not evidence that the shell executed it.
                await self.send_output(data + b"\n")
                self.probe_seen.set()
            await super().push_input(data)

    connection = StartupConnection()
    service = AgentTerminalService(
        sessions,
        TabService(tab_repository),
        terminal,
        connection_registry,
        lambda cols, rows: connection,
        lambda shell_id: bash_shell,
        default_dimensions,
        user_id,
    )
    yield service, connection
    await service.shutdown()
    await sessions.stop()


async def wait_for_session_creation(service):
    async with asyncio.timeout(1):
        while "startup" not in service._by_mcp:
            await asyncio.sleep(0)


async def test_delayed_startup_and_concurrent_first_calls_wait_for_the_same_handshake(
    startup_service, fake_pty
):
    service, connection = startup_service
    first = asyncio.create_task(service.ensure_session("startup"))
    await wait_for_session_creation(service)
    second = asyncio.create_task(service.ensure_session("startup"))
    input_call = asyncio.create_task(
        service.send_keys("startup", "user input", create_if_missing=False)
    )
    try:
        # The previous quiet-window check returned at 0.3s, before this prompt.
        await asyncio.sleep(0.35)
        assert not first.done()
        assert not second.done()
        assert not input_call.done()
        assert fake_pty.get_input() == []

        fake_pty.add_output(b"delayed prompt> ")
        await asyncio.wait_for(connection.probe_seen.wait(), 2)
        assert not first.done()
        assert not second.done()
        assert not input_call.done()
        fake_pty.add_output(connection.marker + b"\r\nready> ")

        async with asyncio.timeout(2):
            first_rec, second_rec, result = await asyncio.gather(first, second, input_call)
        assert first_rec is second_rec
        assert result == {"ok": True}
        assert service._sessions.session_count() == 1
        async with asyncio.timeout(1):
            while b"user input" not in fake_pty.get_input():
                await asyncio.sleep(0)
    finally:
        for task in (first, second, input_call):
            task.cancel()
        await asyncio.gather(first, second, input_call, return_exceptions=True)


async def test_cancelling_one_caller_does_not_cancel_shared_startup(startup_service, fake_pty):
    service, connection = startup_service
    first = asyncio.create_task(service.ensure_session("startup"))
    await wait_for_session_creation(service)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    second = asyncio.create_task(service.ensure_session("startup"))
    try:
        fake_pty.add_output(b"prompt> ")
        await asyncio.wait_for(connection.probe_seen.wait(), 2)
        assert connection.is_connected()
        fake_pty.add_output(connection.marker + b"\r\n")
        rec = await asyncio.wait_for(second, 2)
        assert rec.ready_task.done()
        assert not rec.ready_task.cancelled()
    finally:
        second.cancel()
        await asyncio.gather(second, return_exceptions=True)


async def test_startup_timeout_closes_and_removes_the_failed_session(
    startup_service, fake_pty, monkeypatch
):
    monkeypatch.setattr(agent_module, "_STARTUP_TIMEOUT", 0.06)
    service, connection = startup_service
    fake_pty.add_output(b"prompt> ")
    with pytest.raises(TimeoutError, match="startup timeout"):
        await service.ensure_session("startup")
    assert not connection.is_connected()
    assert service._by_mcp == {}
    assert service._sessions.session_count() == 0
    assert service._terminal._session_read_tasks == {}
    assert service._terminal._flow_state == {}


async def test_silent_prompt_can_become_ready_through_the_handshake(
    startup_service, fake_pty, monkeypatch
):
    monkeypatch.setattr(agent_module, "_STARTUP_TIMEOUT", 1.5)
    service, connection = startup_service
    task = asyncio.create_task(service.ensure_session("startup"))
    try:
        await asyncio.wait_for(connection.probe_seen.wait(), 1)
        assert not task.done()
        fake_pty.add_output(connection.marker + b"\r\n")
        assert await asyncio.wait_for(task, 1)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("shell", ["bash", "fish", "nu", "powershell", "pwsh", "cmd"])
def test_readiness_marker_cannot_be_matched_in_echoed_input(shell):
    marker = "PTNRabc123def456"
    command = agent_module._ready_command(shell, marker)
    assert marker not in agent_module._clean(command.encode())
