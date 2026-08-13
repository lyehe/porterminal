"""Tiny MCP client so a human/agent can drive porterminal's /mcp live.

Reads a JSON list of steps from stdin and runs them in ONE MCP session
(one persistent shell), printing each tool result. Example step list:

    [{"tool": "run_command", "args": {"command": "whoami"}},
     {"tool": "read_screen", "args": {}}]

Usage:
    echo '<json>' | uv run python scripts/agent_drive.py \
        https://<tunnel>.trycloudflare.com/<access-code>/mcp
"""

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Sequence
from urllib.parse import urlsplit

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from porterminal.access_path import validate_access_code

# A bare PowerShell prompt at the end of the screen = the command finished.
_PROMPT_RE = re.compile(r"PS .*?>\s*$")


def validate_mcp_url(value: str) -> str:
    """Require a complete HTTP(S) MCP URL containing a valid access code."""
    if not value or value != value.strip() or any(ord(character) < 32 for character in value):
        raise ValueError("MCP URL must be a complete protected HTTP(S) URL")
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError as error:
        raise ValueError("MCP URL must be a complete protected HTTP(S) URL") from error

    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in parsed.path
    ):
        raise ValueError("MCP URL must be a complete protected HTTP(S) URL")

    segments = parsed.path.split("/")
    if (
        len(segments) < 3
        or segments[0] != ""
        or any(not segment for segment in segments[1:])
        or segments[-1] != "mcp"
    ):
        raise ValueError("MCP URL must end with /<access-code>/mcp")
    try:
        validate_access_code(segments[-2])
    except ValueError as error:
        raise ValueError("MCP URL must end with /<access-code>/mcp") from error
    return value


def _mcp_url_argument(value: str) -> str:
    try:
        return validate_mcp_url(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "url",
        type=_mcp_url_argument,
        metavar="PROTECTED_MCP_URL",
        help="complete URL printed by ptn with /mcp appended",
    )
    return parser.parse_args(argv)


def payload(result) -> dict:
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        return sc.get("result", sc)
    for c in getattr(result, "content", []) or []:
        text = getattr(c, "text", None)
        if text:
            try:
                return json.loads(text)
            except (ValueError, TypeError):
                return {"output": text}
    return {}


async def drive(url: str) -> None:
    steps = json.loads(sys.stdin.read())
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            server_info = getattr(init, "serverInfo", None) or getattr(init, "server_info", None)
            server_name = getattr(server_info, "name", "porterminal")
            print(f"# connected: {server_name} (session shell is persistent)\n")
            for i, step in enumerate(steps, 1):
                tool = step["tool"]
                args = step.get("args", {})
                if tool == "sleep":  # client-side pause (let the PTY catch up)
                    await asyncio.sleep(float(args.get("seconds", 0.6)))
                    continue
                if tool == "run_wait":  # long command: type it, poll until prompt returns
                    cmd = args["command"]
                    max_wait = float(args.get("max_wait", 300))
                    interval = float(args.get("interval", 3))
                    await session.call_tool("send_keys", {"text": cmd + "\r"})
                    elapsed, saw_busy, screen = 0.0, False, ""
                    while elapsed < max_wait:
                        await asyncio.sleep(interval)
                        elapsed += interval
                        screen = payload(await session.call_tool("read_screen", {})).get(
                            "screen", ""
                        )
                        last = next((ln for ln in reversed(screen.splitlines()) if ln.strip()), "")
                        if _PROMPT_RE.search(last):
                            if saw_busy:
                                break
                        else:
                            saw_busy = True
                    print(f"===== step {i}: run_wait({cmd!r})  [~{elapsed:.0f}s] =====")
                    print(screen)
                    print()
                    continue
                data = payload(await session.call_tool(tool, args))
                print(f"===== step {i}: {tool}({json.dumps(args, ensure_ascii=False)}) =====")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                print()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    asyncio.run(drive(args.url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
