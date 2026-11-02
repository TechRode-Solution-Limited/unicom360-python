"""Units left on every bundle (Decimal values, exactly as the gateway sent them).

UNICOM360_API_KEY=... python examples/balance_all.py
"""

from __future__ import annotations

from unicom360 import Unicom360


def main() -> None:
    client = Unicom360()
    result = client.balance.all()
    for bundle_type, units in sorted(result.balances.items()):
        print(f"{bundle_type}: {units}")


if __name__ == "__main__":
    main()
