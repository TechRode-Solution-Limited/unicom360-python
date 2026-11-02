"""Units left on one bundle.

UNICOM360_API_KEY=... python examples/balance_get.py
"""

from __future__ import annotations

from unicom360 import BundleType, Unicom360


def main() -> None:
    client = Unicom360()
    sms = client.balance.get()  # the SMS bundle
    whatsapp = client.balance.get(BundleType.WHATSAPP)
    print(f"SMS: {sms.balance} units, WhatsApp: {whatsapp.balance} units ({sms.client_name})")


if __name__ == "__main__":
    main()
