"""Agent terminal service - drives PTY sessions on behalf of an MCP agent.

One MCP session maps 1:1 to a dedicated PTY session that shows up as an
"agent"-origin tab on the human's phone. The agent is wired in as just
another ``ConnectionPort`` client of the shared ``TerminalService`` (see
``AgentSessionConnection``), so the human co-views and can take over for free.

Exposes the four agent operations the MCP adapter calls:
``run_command``, ``read_screen``, ``send_keys``, ``send_signal``.
"""

import asyncio
import contextlib
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from porterminal.application.ports import AgentConnectionPort, ConnectionRegistryPort
from porterminal.domain import (
    PTYPort,
    RateLimitConfig,
    Session,
    ShellCommand,
    Tab,
    TerminalDimensions,
    UserId,
)

from .session_service import SessionService
from .tab_service import TabService
from .terminal_service import TerminalService

logger = logging.getLogger(__name__)

# Strip ANSI/VT escape sequences from raw PTY capture before scanning for the
# run_command marker (read_screen uses pyte's clean render instead).
_ANSI_RE = re.compile(
    rb"\x1b\[[0-9;?]*[ -/]*[@-~]"  # CSI ... final byte
    rb"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC ... BEL/ST
    rb"|\x1b[@-Z\\-_]"  # 2-byte escapes
)

# Agent input is trusted/explicitly authorized; the human-abuse limiter would
# silently drop bulk input, so agent sessions run effectively unlimited.
_AGENT_RATE = RateLimitConfig(rate=1_000_000_000.0, burst=1_000_000_000)

_MAX_TIMEOUT = 60.0  # cap below Cloudflare Quick Tunnel idle (~100s)
_DEFAULT_TIMEOUT = 30.0


def _clean(raw: bytes) -> str:
    """Strip ANSI and normalise newlines for marker scanning."""
    text = _ANSI_RE.sub(b"", raw).decode("utf-8", "replace")
    return text.replace("\r\n", "\n").replace("\r", "")


def _family(shell_id: str) -> str:
    sid = shell_id.lower()
    if "pwsh" in sid or "powershell" in sid or "devps" in sid:
        return "ps"
    if "cmd" in sid or "command" in sid or "devcmd" in sid:
        return "cmd"
    return "posix"


def _probe_command(shell_id: str, marker: str) -> str:
    """A shell line that prints ``<marker><exit-code>`` for the prior command.

    Constructed so the shell's *echo* of this line never contains the marker
    immediately followed by a digit (it contains the exit-code *expression*),
    so scanning for ``marker\\d+`` matches only the real output line.
    """
    fam = _family(shell_id)
    if fam == "ps":
        # `$?` is only boolean. Preserve a native process's exact exit code,
        # while still mapping PowerShell cmdlet failures to 1. Reset the native
        # code afterward so a later cmdlet failure cannot inherit stale state.
        return (
            f'$ptnSucceeded = $?; $ptnExitCode = $LASTEXITCODE; Write-Output "{marker}'
            "$(if ($ptnSucceeded) {0} elseif ($null -ne $ptnExitCode -and "
            '$ptnExitCode -ne 0) {$ptnExitCode} else {1})"; '
            "$global:LASTEXITCODE = 0"
        )
    if fam == "cmd":
        return f"echo {marker}%errorlevel%"
    return f"printf '{marker}%d\\n' \"$?\""


@dataclass
class _AgentSession:
    session: Session[PTYPort]
    tab: Tab
    conn: AgentConnectionPort
    task: asyncio.Task
    shell_id: str
    lock: asyncio.Lock
    reap_on_disconnect: bool = True
    last_used: float = 0.0


class AgentSessionNotFoundError(LookupError):
    """Raised when a non-creating operation references no live agent session."""


class AgentTerminalService:
    """Manages agent-driven PTY sessions behind the MCP endpoint."""

    def __init__(
        self,
        session_service: SessionService,
        tab_service: TabService,
        terminal_service: TerminalService,
        connection_registry: ConnectionRegistryPort,
        connection_factory: Callable[[int, int], AgentConnectionPort],
        shell_provider: Callable[[str | None], ShellCommand | None],
        default_dimensions: TerminalDimensions,
        owner_user_id: UserId,
        reap_interval: float = 20.0,
        max_idle: float = 900.0,
    ) -> None:
        self._sessions = session_service
        self._tabs = tab_service
        self._terminal = terminal_service
        self._registry = connection_registry
        self._make_conn = connection_factory
        self._get_shell = shell_provider
        self._dims = default_dimensions
        self._owner = owner_user_id
        self._by_mcp: dict[str, _AgentSession] = {}
        self._create_lock = asyncio.Lock()
        self._reap_interval = reap_interval
        self._max_idle = max_idle
        self._live_probe: Callable[[], set[str]] | None = None
        self._reaper_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def ensure_session(
        self, mcp_session_id: str, *, reap_on_disconnect: bool = True
    ) -> _AgentSession:
        """Get (or lazily create) the agent's PTY session + tab."""
        now = asyncio.get_running_loop().time()
        existing = self._by_mcp.get(mcp_session_id)
        if existing is not None:
            existing.last_used = now
            return existing

        async with self._create_lock:
            existing = self._by_mcp.get(mcp_session_id)
            if existing is not None:
                existing.last_used = now
                return existing

            shell = self._get_shell(None)
            if shell is None:
                raise RuntimeError("No shell available")

            session = await self._sessions.create_session(
                user_id=self._owner, shell=shell, dimensions=self._dims
            )
            session.add_client()  # keep alive for the agent's lifetime

            tab = self._tabs.create_tab(
                user_id=self._owner,
                session_id=session.id,
                shell_id=shell.id,
                name=f"Agent {shell.id}"[:50],
                origin="agent",
            )
            # Surface the new robot tab on the human's phone.
            await self._registry.broadcast(
                self._owner, self._tabs.build_tab_state_update("add", tab)
            )

            conn = self._make_conn(self._dims.cols, self._dims.rows)
            task = asyncio.create_task(
                self._terminal.handle_session(
                    session, conn, skip_buffer=False, rate_limit_config=_AGENT_RATE
                )
            )

            rec = _AgentSession(
                session=session,
                tab=tab,
                conn=conn,
                task=task,
                shell_id=shell.id,
                lock=asyncio.Lock(),
                reap_on_disconnect=reap_on_disconnect,
                last_used=now,
            )
            self._by_mcp[mcp_session_id] = rec

            logger.info(
                "Agent session created mcp=%s session_id=%s shell=%s",
                mcp_session_id,
                session.id,
                shell.id,
            )

        # Let the shell finish printing its initial prompt before first use.
        await self._settle(rec.conn, idle=0.3, max_wait=3.0)
        return rec

    async def _resolve_session(
        self,
        mcp_session_id: str,
        *,
        create_if_missing: bool,
        reap_on_disconnect: bool,
    ) -> _AgentSession:
        if create_if_missing:
            return await self.ensure_session(
                mcp_session_id,
                reap_on_disconnect=reap_on_disconnect,
            )

        rec = self._by_mcp.get(mcp_session_id)
        if rec is None:
            raise AgentSessionNotFoundError(mcp_session_id)
        rec.last_used = asyncio.get_running_loop().time()
        return rec

    async def close_session(self, mcp_session_id: str) -> bool:
        rec = self._by_mcp.pop(mcp_session_id, None)
        if rec is None:
            return False
        await rec.conn.close()
        rec.task.cancel()
        try:
            await rec.task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug(
                "Agent session task error during close mcp=%s", mcp_session_id, exc_info=True
            )
        await self._sessions.destroy_session(rec.session.id)
        logger.info("Agent session closed mcp=%s", mcp_session_id)
        return True

    async def shutdown(self) -> None:
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper_task
            self._reaper_task = None
        for mcp_id in list(self._by_mcp):
            await self.close_session(mcp_id)

    # ------------------------------------------------------------------
    # Reaper: clean up agent sessions whose MCP client has disconnected
    # ------------------------------------------------------------------

    def bind_live_probe(self, probe: Callable[[], set[str]]) -> None:
        """Provide a callable returning the MCP session ids still considered
        live by the transport. The reaper closes any tracked session that has
        left that set (graceful DELETE or the SDK's own idle termination)."""
        self._live_probe = probe

    async def start(self) -> None:
        """Start the background reaper (call once, after the loop is running)."""
        if self._reaper_task is None:
            self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def _reaper_loop(self) -> None:
        while True:
            await asyncio.sleep(self._reap_interval)
            try:
                await self._reap_once()
            except Exception:
                logger.exception("Agent reaper error")

    @staticmethod
    def _pty_dead(rec: _AgentSession) -> bool:
        try:
            return not rec.session.pty_handle.is_alive()
        except Exception:
            return False

    async def _reap_once(self) -> None:
        live: set[str] | None = None
        if self._live_probe is not None:
            try:
                live = set(self._live_probe())
            except Exception:
                live = None

        now = asyncio.get_running_loop().time()
        # Reap a session when: its MCP client has gone (absent from `live` in
        # stateful mode = disconnected); its shell has exited (dead PTY, e.g.
        # the agent ran `exit`); or, as a backstop if the probe is unavailable,
        # it has been idle too long.
        stale = [
            mcp_id
            for mcp_id, rec in list(self._by_mcp.items())
            if (live is not None and rec.reap_on_disconnect and mcp_id not in live)
            or self._pty_dead(rec)
            or (now - rec.last_used) > self._max_idle
        ]
        for mcp_id in stale:
            logger.info("Reaping agent session mcp=%s (disconnected or shell exited)", mcp_id)
            await self.close_session(mcp_id)

    # ------------------------------------------------------------------
    # Agent operations (called by MCP tools)
    # ------------------------------------------------------------------

    async def run_command(
        self,
        mcp_session_id: str,
        command: str,
        timeout: float = _DEFAULT_TIMEOUT,
        *,
        reap_on_disconnect: bool = True,
        create_if_missing: bool = True,
    ) -> dict:
        rec = await self._resolve_session(
            mcp_session_id,
            create_if_missing=create_if_missing,
            reap_on_disconnect=reap_on_disconnect,
        )
        timeout = min(max(float(timeout), 1.0), _MAX_TIMEOUT)

        async with rec.lock:
            conn = rec.conn
            conn.take_error()  # clear stale errors
            marker = "PTNX" + uuid.uuid4().hex
            probe = _probe_command(rec.shell_id, marker)
            snapshot = conn.total_received

            await conn.push_input((command + "\r").encode("utf-8"))
            await conn.push_input((probe + "\r").encode("utf-8"))

            pattern = re.compile(re.escape(marker) + r"(-?\d+)")
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout

            while True:
                text = _clean(conn.capture_since(snapshot))
                m = pattern.search(text)
                if m:
                    exit_code = int(m.group(1))
                    output = self._extract_output(text[: m.start()], command, marker)
                    return {
                        "status": "completed",
                        "exit_code": exit_code,
                        "output": output,
                    }
                err = conn.take_error()
                if err:
                    return {"status": "error", "exit_code": None, "output": err}
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return {
                        "status": "waiting",
                        "exit_code": None,
                        "output": self._screen_text(conn),
                        "note": (
                            "Command did not finish (likely interactive). Use "
                            "read_screen to see the prompt and send_keys to respond."
                        ),
                    }
                await conn.wait_for_output(remaining)

    async def read_screen(
        self,
        mcp_session_id: str,
        *,
        reap_on_disconnect: bool = True,
        create_if_missing: bool = True,
    ) -> dict:
        rec = await self._resolve_session(
            mcp_session_id,
            create_if_missing=create_if_missing,
            reap_on_disconnect=reap_on_disconnect,
        )
        # Let any in-flight output finish rendering so we never snapshot
        # mid-draw or return a blank screen right after a send_keys.
        await self._settle(rec.conn, idle=0.15, max_wait=0.6)
        row, col = rec.conn.cursor()
        return {
            "screen": self._screen_text(rec.conn),
            "cursor": {"row": row, "col": col},
        }

    async def send_keys(
        self,
        mcp_session_id: str,
        text: str,
        *,
        reap_on_disconnect: bool = True,
        create_if_missing: bool = True,
    ) -> dict:
        rec = await self._resolve_session(
            mcp_session_id,
            create_if_missing=create_if_missing,
            reap_on_disconnect=reap_on_disconnect,
        )
        await rec.conn.push_input(text.encode("utf-8"))
        return {"ok": True}

    async def send_signal(
        self,
        mcp_session_id: str,
        signal: str,
        *,
        reap_on_disconnect: bool = True,
        create_if_missing: bool = True,
    ) -> dict:
        rec = await self._resolve_session(
            mcp_session_id,
            create_if_missing=create_if_missing,
            reap_on_disconnect=reap_on_disconnect,
        )
        byte = {"int": b"\x03", "eof": b"\x04"}.get(signal.lower())
        if byte is None:
            return {"ok": False, "error": f"Unknown signal: {signal}"}
        await rec.conn.push_input(byte)
        return {"ok": True}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _screen_text(conn: AgentConnectionPort) -> str:
        return "\n".join(line.rstrip() for line in conn.screen_lines()).strip("\n")

    @staticmethod
    def _extract_output(segment: str, command: str, marker: str) -> str:
        """Extract command output from the captured region before the marker.

        The region holds: the echoed command, its output, then the echoed
        marker-print line (which contains the random `marker`). We stop at that
        echoed marker line and drop only the *first* command-echo line, so
        output lines that happen to repeat the command text are preserved.
        """
        cmd = command.strip()
        keep: list[str] = []
        dropped_echo = False
        for line in segment.splitlines():
            if marker in line:
                break  # reached the echoed marker-print command; output ended
            stripped = line.strip()
            if not stripped:
                continue
            if not dropped_echo and cmd and cmd in line:
                dropped_echo = True  # drop the single echoed command line
                continue
            keep.append(line.rstrip())
        return "\n".join(keep).strip()

    @staticmethod
    async def _settle(conn: AgentConnectionPort, idle: float, max_wait: float) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_wait
        while loop.time() < deadline:
            window = min(idle, max(0.0, deadline - loop.time()))
            got = await conn.wait_for_output(window)
            if not got:
                return
