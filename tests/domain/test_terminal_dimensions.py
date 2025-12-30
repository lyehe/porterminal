"""Tests for TerminalDimensions value object."""

import pytest

from porterminal.domain import MAX_COLS, MAX_ROWS, MIN_COLS, MIN_ROWS, TerminalDimensions


class TestTerminalDimensions:
    """Tests for TerminalDimensions."""

    def test_valid_dimensions(self):
        """Test creating valid dimensions."""
        dims = TerminalDimensions(cols=80, rows=24)
        assert dims.cols == 80
        assert dims.rows == 24

    def test_default_dimensions(self):
        """Test default dimensions."""
        dims = TerminalDimensions.default()
        assert dims.cols == 120
        assert dims.rows == 30

    def test_min_cols(self):
        """Test minimum columns."""
        dims = TerminalDimensions(cols=MIN_COLS, rows=24)
        assert dims.cols == MIN_COLS

    def test_max_cols(self):
        """Test maximum columns."""
        dims = TerminalDimensions(cols=MAX_COLS, rows=24)
        assert dims.cols == MAX_COLS

    def test_min_rows(self):
        """Test minimum rows."""
        dims = TerminalDimensions(cols=80, rows=MIN_ROWS)
        assert dims.rows == MIN_ROWS

    def test_max_rows(self):
        """Test maximum rows."""
        dims = TerminalDimensions(cols=80, rows=MAX_ROWS)
        assert dims.rows == MAX_ROWS

    def test_cols_below_min_raises(self):
        """Test that cols below minimum raises ValueError."""
        with pytest.raises(ValueError, match="cols must be"):
            TerminalDimensions(cols=MIN_COLS - 1, rows=24)

    def test_cols_above_max_raises(self):
        """Test that cols above maximum raises ValueError."""
        with pytest.raises(ValueError, match="cols must be"):
            TerminalDimensions(cols=MAX_COLS + 1, rows=24)

    def test_rows_below_min_raises(self):
        """Test that rows below minimum raises ValueError."""
        with pytest.raises(ValueError, match="rows must be"):
            TerminalDimensions(cols=80, rows=MIN_ROWS - 1)

    def test_rows_above_max_raises(self):
        """Test that rows above maximum raises ValueError."""
        with pytest.raises(ValueError, match="rows must be"):
            TerminalDimensions(cols=80, rows=MAX_ROWS + 1)

    def test_clamped_within_bounds(self):
        """Test clamped with values within bounds."""
        dims = TerminalDimensions.clamped(80, 24)
        assert dims.cols == 80
        assert dims.rows == 24

    def test_clamped_below_min(self):
        """Test clamped with values below minimum."""
        dims = TerminalDimensions.clamped(10, 5)
        assert dims.cols == MIN_COLS
        assert dims.rows == MIN_ROWS

    def test_clamped_above_max(self):
        """Test clamped with values above maximum."""
        dims = TerminalDimensions.clamped(1000, 500)
        assert dims.cols == MAX_COLS
        assert dims.rows == MAX_ROWS

    def test_resize_returns_new_instance(self):
        """Test that resize returns a new instance."""
        dims1 = TerminalDimensions(cols=80, rows=24)
        dims2 = dims1.resize(100, 30)

        assert dims1.cols == 80
        assert dims1.rows == 24
        assert dims2.cols == 100
        assert dims2.rows == 30
        assert dims1 is not dims2

    def test_immutable(self):
        """Test that dimensions are immutable."""
        dims = TerminalDimensions(cols=80, rows=24)
        with pytest.raises(AttributeError):
            dims.cols = 100

    def test_equality(self):
        """Test equality comparison."""
        dims1 = TerminalDimensions(cols=80, rows=24)
        dims2 = TerminalDimensions(cols=80, rows=24)
        dims3 = TerminalDimensions(cols=100, rows=24)

        assert dims1 == dims2
        assert dims1 != dims3

    def test_hashable(self):
        """Test that dimensions are hashable."""
        dims = TerminalDimensions(cols=80, rows=24)
        # Should be usable in sets/dicts
        dim_set = {dims}
        assert dims in dim_set
