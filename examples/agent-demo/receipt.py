"""A terminal prompt for the human to answer while the agent watches."""

from invoice import total_after_discount

label = input("Receipt label: ").strip() or "demo"
print(f"Receipt {label}: ${total_after_discount(100, 20):.2f}")
