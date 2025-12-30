"""Terminal dimensions value object with validation."""

from dataclasses import dataclass

# Business rule constants
MIN_COLS = 40
MAX_COLS = 500
MIN_ROWS = 10
MAX_ROWS = 200


@dataclass(frozen=True, slots=True)
class TerminalDimensions:
    """Immutable terminal dimensions with validation.

    Invariants:
    - cols in [40, 500]
    - rows in [10, 200]
    """

    cols: int
    rows: int

    def __post_init__(self) -> None:
        if not (MIN_COLS <= self.cols <= MAX_COLS):
            raise ValueError(f"cols must be {MIN_COLS}-{MAX_COLS}, got {self.cols}")
        if not (MIN_ROWS <= self.rows <= MAX_ROWS):
            raise ValueError(f"rows must be {MIN_ROWS}-{MAX_ROWS}, got {self.rows}")

    @classmethod
    def clamped(cls, cols: int, rows: int) -> "TerminalDimensions":
        """Create dimensions with clamping instead of raising."""
        return cls(
            cols=max(MIN_COLS, min(cols, MAX_COLS)),
            rows=max(MIN_ROWS, min(rows, MAX_ROWS)),
        )

    @classmethod
    def default(cls) -> "TerminalDimensions":
        """Create default dimensions (120x30)."""
        return cls(cols=120, rows=30)

    def resize(self, cols: int, rows: int) -> "TerminalDimensions":
        """Return new dimensions with clamping (immutable)."""
        return TerminalDimensions.clamped(cols, rows)
