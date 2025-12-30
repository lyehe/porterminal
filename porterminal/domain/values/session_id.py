"""Session ID value object."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionId:
    """Strongly-typed session identifier."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not isinstance(self.value, str):
            raise ValueError("SessionId cannot be empty")

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)
