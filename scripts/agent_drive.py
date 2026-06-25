"""Tiny MCP client so a human/agent can drive porterminal's /mcp live.

Reads a JSON list of steps from stdin and runs them in ONE MCP session
(one persistent shell), printing each tool result. Example step list:

    [{"tool": "run_command", "args": {"command": "whoami"}},
     {"tool": "read_screen", "args": {}}]

Usage:  echo '<json>' | uv run python scripts/agent_drive.py [url]
"""

import asyncio
import json
import re
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# A bare PowerShell prompt at the end of the screen = the command finished.
_PROMPT_RE = re.compile(r"PS .*?>\s*$")

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8077/mcp"


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


async def main() -> None:
    steps = json.loads(sys.stdin.read())
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"# connected: {init.serverInfo.name} (session shell is persistent)\n")
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
                        screen = payload(await session.call_tool("read_screen", {})).get("screen", "")
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


asyncio.run(main())
