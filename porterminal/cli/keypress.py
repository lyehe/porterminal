"""Cross-platform single-keypress listener for interactive hotkeys.

Runs a background daemon thread that reads one key at a time (no Enter needed)
from the controlling terminal and dispatches it to handler callbacks. Designed
to run alongside the blocking server loop in ``porterminal.main``.

The CLI process is synchronous (uvicorn runs in a separate subprocess), so a
daemon thread - matching the existing ``drain_process_output`` threads - is the
right tool; there is no asyncio loop to integrate with.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from threading import Event, Thread

Handlers = dict[str, Callable[[], None]]


def start_key_listener(shutdown_event: Event, handlers: Handlers) -> Thread | None:
    """Start a daemon thread dispatching single keypresses to ``handlers``.

    Keys are matched case-insensitively, so ``{"c": ...}`` also fires on "C".
    The thread stops when ``shutdown_event`` is set; the caller should set it and
    ``join()`` the returned thread on shutdown so the terminal is restored before
    any further output. It is a no-op (returns None) when stdin is not an
    interactive terminal (piped, redirected, or detached/background).

    Args:
        shutdown_event: Setting this stops the listener loop.
        handlers: Map of lowercase key char -> zero-arg callback.

    Returns:
        The listener thread, or None if stdin is not a TTY.
    """
    if not sys.stdin.isatty():
        return None

    target = _listen_windows if sys.platform == "win32" else _listen_unix
    thread = Thread(target=target, args=(shutdown_event, handlers), daemon=True)
    thread.start()
    return thread


def _dispatch(ch: str, handlers: Handlers) -> None:
    handler = handlers.get(ch.lower())
    if handler is None:
        return
    try:
        handler()
    except Exception:
        # A misbehaving handler must never kill the listener thread.
        pass


def _listen_windows(shutdown_event: Event, handlers: Handlers) -> None:
    import msvcrt
    import time

    while not shutdown_event.is_set():
        if msvcrt.kbhit():
            try:
                ch = msvcrt.getwch()
            except (OSError, ValueError):
                continue
            _dispatch(ch, handlers)
        else:
            time.sleep(0.05)


def _listen_unix(shutdown_event: Event, handlers: Handlers) -> None:
    import atexit
    import os
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    try:
        old_settings = termios.tcgetattr(fd)
    except termios.error:
        return  # Not a real terminal; nothing to restore or read.

    def restore() -> None:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except (termios.error, OSError):
            pass

    # Backstop: daemon threads are killed abruptly at interpreter exit and may
    # skip the finally below, which would leave the terminal in cbreak mode.
    atexit.register(restore)

    try:
        # cbreak (not raw): single-key reads with no echo, while Ctrl+C still
        # raises SIGINT and output newline translation stays intact for redraws.
        tty.setcbreak(fd)
        while not shutdown_event.is_set():
            ready, _, _ = select.select([fd], [], [], 0.2)
            if ready:
                # Read the raw fd, not the buffered sys.stdin TextIOWrapper, so a
                # byte can't sit in Python's buffer unseen by the next select().
                ch = os.read(fd, 1).decode(errors="ignore")
                if ch:
                    _dispatch(ch, handlers)
    finally:
        restore()
