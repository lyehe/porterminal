"""Real PTY coverage for agent startup and completion across supported shells."""

import json
import os
import shutil

import pytest

from porterminal.composition import create_container


@pytest.mark.parametrize(
    "shell_id,args",
    [
        ("bash", ["--noprofile", "--norc"]),
        ("fish", ["--no-config"]),
        ("nu", ["--no-config-file", "--no-history"]),
        ("cmd", ["/Q"]),
        ("pwsh", ["-NoLogo", "-NoProfile"]),
    ],
)
async def test_agent_completion_and_exit_codes_in_real_shell(tmp_path, shell_id, args):
    if (shell_id in {"cmd", "pwsh"}) != (os.name == "nt"):
        pytest.skip("Shell belongs to a different operating system")
    executable = os.environ.get("PORTERMINAL_TEST_NU") if shell_id == "nu" else None
    executable = executable or shutil.which(shell_id)
    if not executable:
        pytest.skip(f"{shell_id} is not installed")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        json.dumps(
            {
                "terminal": {
                    "default_shell": shell_id,
                    "shells": [
                        {"id": shell_id, "name": shell_id, "command": executable, "args": args}
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    container = create_container(config_path=config_path, cwd=str(tmp_path))
    agent = container.agent_terminal_service
    try:
        result = await agent.run_command("shell-regression", "echo SHELL_OK", timeout=10)
        assert result["status"] == "completed", result
        assert result["exit_code"] == 0, result
        assert "SHELL_OK" in result["output"], (
            result,
            agent._by_mcp["shell-regression"].conn.capture_since(0),
        )

        result = await agent.run_command(
            "shell-regression", 'python -c "import sys; sys.exit(7)"', timeout=10
        )
        assert result["status"] == "completed", result
        assert result["exit_code"] == 7, result

        result = await agent.run_command(
            "shell-regression", "cd __ptn_missing_directory__", timeout=10
        )
        assert result["status"] == "completed", result
        assert result["exit_code"] != 0, result

        result = await agent.run_command(
            "shell-regression", "python -c \"print('SHELL_AFTER')\"", timeout=10
        )
        assert result["status"] == "completed", result
        assert result["exit_code"] == 0, result
        assert "SHELL_AFTER" in result["output"], result
    finally:
        await agent.shutdown()
        await container.session_service.stop()
