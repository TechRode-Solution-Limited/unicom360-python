"""Send an SMS to two numbers and find each recipient's result.

    UNICOM360_API_KEY=... python examples/sms_send.py

This sends a real, billed message: there is no sandbox.
"""

from __future__ import annotations

from unicom360 import APIError, InsufficientBundleError, Unicom360, gsm


def main() -> None:
    client = Unicom360()  # reads UNICOM360_API_KEY
    text = "Your verification code is 482193. It expires in 5 minutes."

    # Optional: check the text the way the gateway will, before paying for it.
    problems = gsm.validate_sms(text)
    if problems:
        raise SystemExit(f"The gateway would refuse this text: {problems}")
    print(f"{gsm.units(text)} unit(s) per recipient")

    try:
        result = client.sms.send(
            from_="Unicom360",
            to=["260971234567", "260961234567"],
            message=text,
            user_reference_id="otp-482193",  # makes the send safe to retry
            callback_url="https://example.com/webhooks/unicom360/sms",
        )
    except InsufficientBundleError as error:
        raise SystemExit(f"Top up your SMS bundle (api_reference {error.api_reference})") from error
    except APIError as error:
        raise SystemExit(f"Refused: {error.code} ({error.message})") from error

    # Results are not in request order past the tenth recipient: look them up by number.
    for number in ("260971234567", "260961234567"):
        found = result.by_number(number)
        print(number, found.status if found else "missing", found.message_id if found else "")
    print(f"{len(result.accepted())} accepted, {len(result.invalid())} invalid")


if __name__ == "__main__":
    main()
