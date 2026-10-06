"""Small invoice demo with an intentional discount bug for an agent to fix."""


def total_after_discount(price: float, percent: float) -> float:
    """Return the total after applying a percentage discount."""
    return round(price * (1 + percent / 100), 2)
