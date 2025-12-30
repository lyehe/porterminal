"""Shell command specification value object."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShellCommand:
    """Shell command specification (value object).

    Note: Validation that the command exists on the filesystem
    is NOT done here - that's an infrastructure concern.
    """

    id: str
    name: str
    command: str
    args: tuple[str, ...]  # Immutable tuple instead of list

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Shell id cannot be empty")
        if not self.command:
            raise ValueError("Shell command cannot be empty")

    def to_command_list(self) -> list[str]:
        """Build command + args list for process spawning."""
        return [self.command, *self.args]

    @classmethod
    def from_dict(cls, data: dict) -> "ShellCommand":
        """Create from dictionary (e.g., from config)."""
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            command=data["command"],
            args=tuple(data.get("args", [])),
        )
