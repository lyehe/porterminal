"""Tab ID value object."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TabId:
    """Strongly-typed tab identifier.

    Generated as UUID string, same pattern as SessionId.
    Immutable and hashable for use as dict keys.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not isinstance(self.value, str):
            raise ValueError("TabId cannot be empty")

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)
