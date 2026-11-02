"""Look up the status of WhatsApp messages by the message_id a send returned.

UNICOM360_API_KEY=... python examples/whatsapp_status.py
"""

from __future__ import annotations

from unicom360 import Unicom360


def main() -> None:
    client = Unicom360()
    ids = ["7c1f3a2e-5b64-4d2f-9a8e-0f1b2c3d4e5f", "00000000-0000-4000-8000-000000000000"]
    result = client.whatsapp.status(ids)
    for entry in result.results:
        if entry.status == "NOT_FOUND":
            print(entry.message_id, "not found")
        elif entry.error is not None:
            print(entry.message_id, entry.status, entry.error.code, entry.error.message)
        else:
            print(entry.message_id, entry.status, entry.delivered_at, entry.read_at)


if __name__ == "__main__":
    main()
