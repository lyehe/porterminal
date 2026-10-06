"""Real PTY coverage for agent completion across supported Unix shells."""

import json
import os
import shutil

import pytest

from porterminal.composition import create_container

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Unix PTYs run on Linux and macOS")


@pytest.mark.parametrize(
    "shell_id,args",
    [
        ("bash", ["--noprofile", "--norc"]),
        ("fish", ["--no-config"]),
        ("nu", ["--no-config-file", "--no-history"]),
    ],
)
async def test_agent_completion_and_exit_codes_in_real_shell(tmp_path, shell_id, args):
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
        assert "SHELL_OK" in result["output"], result

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

        result = await agent.run_command("shell-regression", "echo SHELL_AFTER", timeout=10)
        assert result["status"] == "completed", result
        assert result["exit_code"] == 0, result
        assert "SHELL_AFTER" in result["output"], result
    finally:
        await agent.shutdown()
        await container.session_service.stop()
