"""Reply inside the 24-hour customer service window, with text, buttons and a reaction.

UNICOM360_API_KEY=... python examples/whatsapp_send_session.py
"""

from __future__ import annotations

from unicom360 import SessionWindowClosedError, Unicom360, session
from unicom360.session import ListRow, ListSection, ReplyButton

# The wamid of the customer's message, as a message.received webhook delivered it.
INBOUND = "wamid.HBgMMjYwOTcxMjM0NTY3FQIAEhggQTVCMEM3Qjc5OUZCOEU5NEM3REMxMjI5NzJBODJEQTVEAA=="


def main() -> None:
    client = Unicom360()
    customer = "260971234567"
    try:
        sent = client.whatsapp.send_session(
            session.text(
                customer,
                "Hi Ada, your order ZM-4821 is ready for collection at the Cairo Road branch.",
                from_="260960123456",
                reply_to=INBOUND,
                user_reference_id="s-1",
            )
        )
    except SessionWindowClosedError as error:
        raise SystemExit("The window is closed: send a template instead.") from error
    print("sent", sent.message_id, sent.status)

    client.whatsapp.send_session(
        session.buttons(
            customer,
            "Collect today or deliver?",
            [ReplyButton("collect", "Collect"), ReplyButton("deliver", "Deliver")],
            footer="Reply within 24 hours",
        )
    )
    client.whatsapp.send_session(
        session.list(
            customer,
            "Choose a delivery slot",
            "Pick a slot",
            [
                ListSection(
                    title="Today",
                    rows=[
                        ListRow("today-am", "Morning", "08:00 to 12:00"),
                        ListRow("today-pm", "Afternoon"),
                    ],
                )
            ],
        )
    )
    client.whatsapp.send_session(
        session.location(customer, -15.4167, 28.2833, "Cairo Road branch", "Cairo Road, Lusaka")
    )
    client.whatsapp.send_session(session.reaction(customer, INBOUND, "\U0001f44d"))


if __name__ == "__main__":
    main()
