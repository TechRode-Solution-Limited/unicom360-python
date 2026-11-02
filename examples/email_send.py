"""Send an HTML email to two addresses.

UNICOM360_API_KEY=... python examples/email_send.py
"""

from __future__ import annotations

from unicom360 import Unicom360


def main() -> None:
    client = Unicom360()
    result = client.email.send(
        from_="noreply@yourdomain.com",
        to=["jane@example.com", "john@example.com"],
        subject="Your order is confirmed",
        email_body="<p>Thanks for your order. Order ZM4821 is confirmed.</p>",
        reply_to="support@yourdomain.com",
        callback_url="https://example.com/webhooks/unicom360/email",
    )
    for address in ("jane@example.com", "john@example.com"):
        found = result.by_address(address)
        print(address, found.status if found else "missing", found.message_id if found else "")


if __name__ == "__main__":
    main()
