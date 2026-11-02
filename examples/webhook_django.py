"""Receive Unicom360 WhatsApp webhooks with Django.

Route the CSRF-exempt view in your urls.py::

    path("webhooks/unicom360/whatsapp", webhook_django.whatsapp_view)
"""

from __future__ import annotations

import os

from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from unicom360 import SignatureVerificationError, webhooks

SECRET = os.environ.get("UNICOM360_WEBHOOK_SECRET", "")


def whatsapp_webhook(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        # request.body is the raw body bytes.
        event = webhooks.construct_event(request.body, request.headers, SECRET)
    except SignatureVerificationError as error:
        return HttpResponse(error.reason, status=401)

    if isinstance(event, webhooks.MessageReceivedEvent):
        print("from", event.data.from_, "text", event.data.text)
    elif isinstance(event, webhooks.MessageStatusEvent):
        print("status", event.data.message_id, event.data.status)
    return HttpResponse(status=200)


# Unicom360 cannot send a CSRF token; the signature is what authenticates the delivery.
whatsapp_view = csrf_exempt(whatsapp_webhook)
