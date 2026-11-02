"""Send an approved WhatsApp template, each recipient with its own parameters.

UNICOM360_API_KEY=... python examples/whatsapp_send_template.py
"""

from __future__ import annotations

from unicom360 import (
    NoValidRecipientsError,
    TemplateBody,
    TemplateButton,
    TemplateHeader,
    TemplateRecipient,
    Unicom360,
)


def main() -> None:
    client = Unicom360()
    try:
        result = client.whatsapp.send_template(
            template="order_ready",
            from_="260960123456",
            language="en_US",
            callback_url="https://example.com/webhooks/unicom360/whatsapp",
            recipients=[
                TemplateRecipient(
                    to="260971234567",
                    user_reference_id="inv-42",
                    header=TemplateHeader.image("https://example.com/receipts/ZM-4821.png"),
                    body=TemplateBody.of(["Ada", "ZM-4821"]),
                    buttons=[TemplateButton.url(0, "ZM-4821")],
                ),
                TemplateRecipient(
                    to="260961234567",
                    user_reference_id="inv-43",
                    body=TemplateBody.of(["Joseph", "ZM-4822"]),
                ),
            ],
        )
    except NoValidRecipientsError as error:
        for rejected in error.results:
            print("rejected", rejected.to, rejected.reason)
        raise SystemExit(1) from error

    print(f"{result.accepted_count} accepted, {result.rejected_count} rejected")
    for rejected in result.rejected():
        print("rejected", rejected.to, rejected.reason)


if __name__ == "__main__":
    main()
