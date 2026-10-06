"""Regression tests for command output captured from an agent's PTY."""

import asyncio

import pytest

from porterminal.application.services.agent_terminal_service import AgentTerminalService
from porterminal.infrastructure.web.agent_connection import AgentSessionConnection


async def test_agent_terminal_answers_cursor_position_queries():
    connection = AgentSessionConnection(80, 24)
    await connection.send_output(b"hello\x1b[6n")

    assert await asyncio.wait_for(connection.receive(), 1) == b"\x1b[1;6R"
    assert connection.capture_since(0) == b"hello\x1b[6n"


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
