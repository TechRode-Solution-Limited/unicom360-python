"""Receive Unicom360 WhatsApp webhooks with FastAPI.

UNICOM360_WEBHOOK_SECRET=... uvicorn examples.webhook_fastapi:app
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request, Response

from unicom360 import SignatureVerificationError, webhooks

app = FastAPI()
SECRET = os.environ.get("UNICOM360_WEBHOOK_SECRET", "")


@app.post("/webhooks/unicom360/whatsapp")
async def whatsapp_webhook(request: Request) -> Response:
    body = await request.body()  # the raw bytes, before any JSON parsing
    try:
        event = webhooks.construct_event(body, request.headers, SECRET)
    except SignatureVerificationError as error:
        return Response(error.reason, status_code=401)

    if isinstance(event, webhooks.MessageReceivedEvent):
        print("from", event.data.from_, "text", event.data.text)
    elif isinstance(event, webhooks.MessageStatusEvent):
        print("status", event.data.message_id, event.data.status)
    return Response(status_code=200)
