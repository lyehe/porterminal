"""Configuration port - interface for configuration access."""

from typing import Any, Protocol


class ConfigPort(Protocol):
    """Protocol for configuration access.

    Infrastructure layer implements this with actual config loading.
    """

    def get_server_host(self) -> str:
        """Get server bind host."""
        ...

    def get_server_port(self) -> int:
        """Get server port."""
        ...

    def get_default_cols(self) -> int:
        """Get default terminal columns."""
        ...

    def get_default_rows(self) -> int:
        """Get default terminal rows."""
        ...

    def get_default_shell_id(self) -> str:
        """Get default shell ID."""
        ...

    def get_shell_by_id(self, shell_id: str) -> dict[str, Any] | None:
        """Get shell configuration by ID."""
        ...

    def get_available_shells(self) -> list[dict[str, Any]]:
        """Get list of available shells."""
        ...

    def get_buttons(self) -> list[dict[str, Any]]:
        """Get custom button configurations."""
        ...
