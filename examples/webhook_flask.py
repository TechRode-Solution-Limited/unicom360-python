"""Receive Unicom360 webhooks and delivery reports with Flask.

UNICOM360_WEBHOOK_SECRET=... flask --app examples/webhook_flask.py run
"""

from __future__ import annotations

import os

from flask import Flask, request

from unicom360 import SignatureVerificationError, webhooks

app = Flask(__name__)
SECRET = os.environ.get("UNICOM360_WEBHOOK_SECRET", "")
seen_deliveries: set[str] = set()  # use your database in production


@app.post("/webhooks/unicom360/whatsapp")
def whatsapp_webhook() -> tuple[str, int]:
    try:
        # get_data() is the raw body; never re-serialise request.json.
        event = webhooks.construct_event(request.get_data(), request.headers, SECRET)
    except SignatureVerificationError as error:
        return error.reason, 401

    # Deliveries are retried until you answer 2xx: drop repeats.
    if event.delivery_id is not None:
        if event.delivery_id in seen_deliveries:
            return "", 200
        seen_deliveries.add(event.delivery_id)

    if isinstance(event, webhooks.MessageStatusEvent):
        print("status", event.data.message_id, event.data.status)
    elif isinstance(event, webhooks.MessageReceivedEvent):
        print("from", event.data.from_, "text", event.data.text, "type", event.data.type)
    elif isinstance(event, webhooks.TestEvent):
        print("test:", event.data.message)
    else:
        print("unhandled event", event.event)
    return "", 200


@app.post("/webhooks/unicom360/sms")
def sms_report() -> tuple[str, int]:
    # SMS and email reports are unsigned and never retried: treat them as hints.
    report = webhooks.parse_sms_callback(request.get_data())
    print("sms", report.message_id, report.status, report.mobile_number)
    return "", 200


@app.post("/webhooks/unicom360/email")
def email_report() -> tuple[str, int]:
    report = webhooks.parse_email_callback(request.get_data())
    print("email", report.message_id, report.status, report.message)
    return "", 200
