"""Application port for creating terminal PTYs."""

from typing import Protocol

from porterminal.domain import PTYPort, ShellCommand, TerminalDimensions


class PTYFactory(Protocol):
    """Create a spawned PTY for a shell and working directory."""

    def __call__(
        self,
        shell: ShellCommand,
        dimensions: TerminalDimensions,
        working_directory: str | None = None,
    ) -> PTYPort: ...
