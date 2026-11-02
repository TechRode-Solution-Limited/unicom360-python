# Unicom360 Python SDK

The official Python client for the [Unicom360](https://unicom360.com) API: SMS, email and
WhatsApp over one JSON API.

* Python 3.9 or later, **no dependencies** (the standard library only).
* Typed (`py.typed`), checked with `mypy --strict`.
* Targets **Unicom360 API contract v0.1.0** (`openapi.yaml` 0.1.0 in
  [unicom360-openapi](https://github.com/TechRode-Solution-Limited/unicom360-openapi)), and runs
  that contract's full conformance suite in CI.
* API reference: <https://unicom360.com/docs>.

There is no sandbox: every accepted send is real and billed.

## Contents

* [Install](#install)
* [Quick start](#quick-start)
* [Every operation](#every-operation)
* [Results](#results)
* [Errors](#errors)
* [Retries](#retries)
* [auto_reference_ids](#auto_reference_ids)
* [Webhooks](#webhooks)
* [SMS and email delivery reports](#sms-and-email-delivery-reports)
* [GSM-7 helpers](#gsm-7-helpers)
* [Configuration](#configuration)
* [Logging](#logging)
* [Known differences from the published docs](#known-differences-from-the-published-docs)
* [Versioning](#versioning)

## Install

```sh
pip install unicom360
```

## Quick start

```python
from unicom360 import Unicom360

client = Unicom360()  # reads UNICOM360_API_KEY; or Unicom360(api_key="...")

result = client.sms.send(
    from_="Unicom360",
    to=["260971234567", "260961234567"],
    message="Your verification code is 482193. It expires in 5 minutes.",
)
for recipient in result.results:
    print(recipient.mobile_number, recipient.status, recipient.message_id)
```

`from` is a Python keyword, so the sender is `from_` everywhere (arguments and model fields).
Every other name is the API's own.

## Every operation

| Operation | Method | Returns |
|---|---|---|
| Send an SMS | `client.sms.send(...)` | `SmsSendResult` |
| Send an email | `client.email.send(...)` | `EmailSendResult` |
| Send a WhatsApp template | `client.whatsapp.send_template(...)` | `TemplateSendResult` |
| Send a WhatsApp session message | `client.whatsapp.send_session(message)` | `SessionSendResult` |
| WhatsApp message status | `client.whatsapp.status(message_ids)` | `StatusResult` |
| WhatsApp templates | `client.whatsapp.templates()` | `TemplateList` |
| One balance | `client.balance.get(bundle_type=None)` | `Balance` |
| Every balance | `client.balance.all()` | `Balances` |
| Health | `client.health()` | `Health` |

Every operation also takes `timeout=` (seconds per attempt) and `max_retries=`, which override
the client's settings for that call.

### SMS

```python
result = client.sms.send(
    from_="Unicom360",  # a registered sender ID
    to="260971234567",  # one number, or a list
    message="Your order ZM4821 is ready.",  # GSM-7, at most 1,200 characters
    user_reference_id="order-10421",  # optional: makes the send safe to retry
    callback_url="https://example.com/webhooks/unicom360/sms",  # optional
    source="crm",  # optional label for your reporting
)
print(result.api_reference, [r.status for r in result.results])
```

### Email

```python
result = client.email.send(
    from_="noreply@yourdomain.com",
    to=["jane@example.com", "john@example.com"],
    subject="Your order is confirmed",
    email_body="<p>Thanks for your order. Order ZM4821 is confirmed.</p>",
    reply_to="support@yourdomain.com",  # optional
    callback_url="https://example.com/webhooks/unicom360/email",  # optional
)
jane = result.by_address("jane@example.com")
```

### WhatsApp template

```python
from unicom360 import TemplateBody, TemplateButton, TemplateHeader, TemplateRecipient

result = client.whatsapp.send_template(
    template="order_ready",
    from_="260960123456",  # optional: your WhatsApp number
    language="en_US",  # optional
    recipients=[
        TemplateRecipient(
            to="260971234567",
            user_reference_id="inv-42",
            header=TemplateHeader.image("https://example.com/receipts/ZM-4821.png"),
            body=TemplateBody.of(["Ada", "ZM-4821"]),  # or TemplateBody.named({...})
            buttons=[TemplateButton.url(0, "ZM-4821")],  # or TemplateButton.quick_reply(...)
        ),
        TemplateRecipient(to="260961234567", body=["Joseph", "ZM-4822"]),
    ],
)
print(result.accepted_count, result.rejected_count)
for rejected in result.rejected():
    print(rejected.to, rejected.reason)
```

Headers: `TemplateHeader.text(value)` (or a plain string), `.image(url)`, `.video(url)`,
`.document(url, filename=None)`. An `AUTHENTICATION` template takes the code as
`TemplateRecipient(to=..., otp="482193")`. A recipient may also be a dict in the API's shape.

A rejected recipient is not an error. When **every** recipient is rejected the call raises
`NoValidRecipientsError`, whose `results` say why.

### WhatsApp session message

Inside the 24-hour customer service window, build a message with `unicom360.session`:

```python
from unicom360 import session
from unicom360.session import ListRow, ListSection, ReplyButton

client.whatsapp.send_session(
    session.text("260971234567", "Your order is ready.", reply_to=inbound_wamid)
)
client.whatsapp.send_session(
    session.buttons(
        "260971234567",
        "Collect today or deliver?",
        [ReplyButton("collect", "Collect"), ReplyButton("deliver", "Deliver")],
    )
)
```

| Builder | Sends |
|---|---|
| `session.text(to, text)` | text |
| `session.image(to, url, caption=None)` | image |
| `session.video(to, url, caption=None)` | video |
| `session.document(to, url, caption=None, filename=None)` | document |
| `session.audio(to, url)` | audio |
| `session.sticker(to, url)` | sticker |
| `session.buttons(to, body, buttons, header=None, footer=None)` | up to 3 reply buttons, each `ReplyButton(id, title)` or an `(id, title)` pair |
| `session.list(to, body, button, sections, header=None, footer=None)` | a list of `ListSection(rows=[ListRow(id, title, description=None)], title=None)` |
| `session.location(to, latitude, longitude, name=None, address=None)` | a location pin |
| `session.contacts(to, contacts)` | contact cards in Meta's shape (dicts) |
| `session.reaction(to, message_id, emoji)` | a reaction; `emoji=""` removes yours |

Every builder takes the keyword arguments `from_`, `user_reference_id`, `callback_url` and (all
but `reaction`) `reply_to`. `reply_to` and a reaction's `message_id` take either a `message_id`
a send returned or the `wamid.` id of an inbound message, exactly as a `message.received`
webhook delivers it. Outside the window the call raises `SessionWindowClosedError`: send a
template instead.

### WhatsApp status and templates

```python
status = client.whatsapp.status(["7c1f3a2e-5b64-4d2f-9a8e-0f1b2c3d4e5f"])  # 1 to 100 ids
entry = status.by_id("7c1f3a2e-5b64-4d2f-9a8e-0f1b2c3d4e5f")
if entry is not None:
    print(entry.status)  # ACCEPTED, SENT, DELIVERED, READ, FAILED, REJECTED, NOT_FOUND

templates = client.whatsapp.templates()
order_ready = templates.by_name("order_ready", "en_US")
```

### Balance and health

```python
from unicom360 import BundleType

client.balance.get().balance  # Decimal("1250"): the SMS bundle
client.balance.get(BundleType.WHATSAPP).balance  # SMS, SMS_INTERNATIONAL, EMAIL, WHATSAPP
client.balance.all().balances  # {"SMS": Decimal("1250"), ...}
client.health().status  # "ok"; sends no API key
```

Balances are `decimal.Decimal`, exactly as the gateway sent them.

Runnable versions of all of these are in [`examples/`](examples/).

## Results

Every result is an immutable, typed dataclass:

* fields named as in the API (`from_` for `from`), `None` when absent or null;
* `raw`: the JSON object it was parsed from, unmodified;
* `extra`: every field the gateway sent that this version does not model, so a field added
  tomorrow is readable today.

Statuses, categories and reasons are plain strings: a value this version does not know passes
through. `message_id` is always a string.

**SMS and email results are not in request order past the tenth recipient.** The SDK keeps the
response's order; find a recipient with the helpers:

| Result | Helpers |
|---|---|
| `SmsSendResult` | `accepted()`, `invalid()`, `by_number(number)` |
| `EmailSendResult` | `accepted()`, `invalid()`, `by_address(address)` |
| `TemplateSendResult` | `accepted()`, `rejected()`, `by_number(number)`; counts in `accepted_count`, `rejected_count` |
| `StatusResult` | `by_id(message_id)` |
| `TemplateList` | `by_name(name, language=None)` |

`by_number` compares digits only (`"+260 97 123 4567"` finds `"260971234567"`); it does not
expand local formats, so pass the international form. `by_address` ignores case and
surrounding spaces.

A partial success (an `Invalid mobile number` among the results, rejected template recipients)
is a result, never an exception.

## Errors

```
Unicom360Error
+-- ConfigurationError             no API key, an unusable option, a blank webhook secret
+-- APIConnectionError             no complete response (.sent, .cause)
|   +-- APITimeoutError
+-- APIStatusError                 any other non-2xx, or a 2xx that is not an envelope
|   +-- AuthenticationError        401
|   +-- RateLimitError             429 (.retry_after)
|   +-- InvalidRequestError        400: the request's shape is wrong
|   +-- APIServerError             5xx
+-- APIError                       HTTP 200 with success: false: a business refusal
|   +-- InsufficientBundleError
|   +-- DuplicateReferenceError    (.original_message_id)
|   +-- NoValidRecipientsError     (.results)
|   +-- SessionWindowClosedError
+-- SignatureVerificationError     a webhook failed verification (.reason)
```

HTTP 200 is not success: a refusal such as an unknown sender ID arrives as HTTP 200 with
`success: false` and raises `APIError`. Every error raised by an operation has `message`,
`http_status`, `api_reference` (quote it to support), `raw_body` and `attempts`. `APIStatusError`
and `APIError` add `code`, `data` and `headers`.

```python
from unicom360 import APIError, InsufficientBundleError, RateLimitError, codes

try:
    client.sms.send(from_="Unicom360", to="260971234567", message="Hello")
except InsufficientBundleError:
    ...  # top up
except RateLimitError as error:
    print(f"retry in {error.retry_after:.0f} s")
except APIError as error:
    if error.code == codes.INVALID_SENDER_ID:
        ...
    print(error.code, error.message, error.api_reference)
```

`code` is normalised from the gateway's message (`unicom360.normalize_code`), so sentences and
codes compare the same way: `Invalid From Sender ID` and `Invalid Sender` are both
`INVALID_SENDER_ID`, `duplicate user reference id` and `DUPLICATE_MSG_REF` are both
`DUPLICATE_REFERENCE`, and anything unrecognised is `UNKNOWN`. The constants are in
`unicom360.codes`: `INVALID_SENDER_ID`, `SENDER_ID_NOT_ALLOWED`, `INVALID_RECIPIENT_LIMIT`,
`INSUFFICIENT_BUNDLE`, `DUPLICATE_REFERENCE`, `INVALID_PARAMETERS`, `SENDER_REQUIRED`,
`TEMPLATE_NOT_FOUND`, `TEMPLATE_NOT_APPROVED`, `LANGUAGE_REQUIRED`, `TEMPLATE_SENDER_MISMATCH`,
`NO_VALID_RECIPIENTS`, `SEND_FAILED`, `SESSION_WINDOW_CLOSED`, `REPLY_TO_NOT_FOUND`,
`REACTION_TARGET_NOT_FOUND`, `INVALID_NUMBER`, `INVALID_USER_REFERENCE_ID`, `MEDIA_URL_INVALID`,
`CLIENT_NOT_FOUND`, `MISSING_API_KEY`, `INVALID_AUTHORIZATION`, `AUTHENTICATION_FAILED`,
`CREDENTIAL_DISABLED`, `CLIENT_DISABLED`, `CREDENTIAL_EXPIRED`, `IP_NOT_ALLOWED`,
`RATE_LIMIT_EXCEEDED` and more.

**A `DuplicateReferenceError` with `attempts` greater than 1 means an earlier attempt of the same
call very probably succeeded**: the retry was refused because that attempt had already used the
reference. Treat it as sent, and look it up rather than sending again.

## Retries

The client retries what is safe to retry, so a retry never sends a message twice:

| Outcome | Retried |
|---|---|
| HTTP 429 | always (it is answered before any processing) |
| No connection made (DNS, refused, TLS, connect timeout) | always |
| A failure after the request was sent, an HTTP 5xx, or `SEND_FAILED` | only if the call is retry-safe |
| HTTP 400, 401, any other 4xx, any other refusal | never |

Retry-safe calls: every read (`status`, `templates`, `balance`, `health`); an SMS or WhatsApp
session send with a `user_reference_id`; a template send where every recipient has one.
**Email is never retry-safe**, even with a reference: the gateway's duplicate check for email is
not atomic, so it is retried only after a 429 or a failure to connect.

Waits: after a 429, until the next UTC minute plus up to a second of jitter (the limit is a fixed
UTC-minute window and the gateway sends no `Retry-After`); otherwise full-jitter exponential
backoff (`random() * min(8, 0.5 * 2^attempt)` seconds). `max_retries` (default 2) bounds the
retries and `max_retry_wait` (default 60 s) any single wait; a 429 wait longer than
`max_retry_wait` raises at once. The raised error is the last attempt's, with `attempts` set.

```python
client = Unicom360(max_retries=4)
client.balance.get(max_retries=0)  # per call
```

## auto_reference_ids

```python
client = Unicom360(auto_reference_ids=True)
```

Off by default. When on, every send without a `user_reference_id` gets one before the first
attempt (`u360-` followed by 32 hex characters), reused on every retry, and each template
recipient without one gets its own. That makes SMS and WhatsApp sends retry-safe. A reference
you pass is never replaced. The generated values are in the request, in the debug log line of
the request, and in the result's `raw` where the API echoes them (template and session
results). For email the reference still lets the gateway refuse a later repeat of the same
send, but it does not make email retry-safe (see above).

## Webhooks

WhatsApp events (`message.status`, `message.received`, `webhook.test`) are signed. Verify and
parse a delivery with `webhooks.construct_event`, passing the **raw body bytes**, the request
headers and your webhook secret (the 43-character string from the portal, used as it is: never
base64-decode it):

```python
from unicom360 import SignatureVerificationError, webhooks

try:
    event = webhooks.construct_event(raw_body, headers, secret)  # tolerance=300 seconds
except SignatureVerificationError as error:
    ...  # answer 401; error.reason says which check failed

if isinstance(event, webhooks.MessageStatusEvent):
    print(event.data.message_id, event.data.status)  # sent, delivered, read, failed
elif isinstance(event, webhooks.MessageReceivedEvent):
    print(event.data.from_, event.data.type, event.data.text)
elif isinstance(event, webhooks.TestEvent):
    print(event.data.message)
else:  # webhooks.UnknownEvent: an event this version does not know; never raises
    print(event.event, event.data)
```

`webhooks.verify(raw_body, headers, secret, tolerance=300)` only verifies. `headers` can be a
dict, Flask/Werkzeug, Django or Starlette headers, or a list of pairs; names are matched without
regard to case.

A secret that is `None`, empty or only whitespace, as `str` or `bytes` (an unset environment
variable, say), raises `ConfigurationError` before any other check, because anyone can forge a
signature with an empty key. That is a fault in your configuration, not a failed verification:
let it answer 500, and do not catch it where you answer 401.

**Flask**

```python
@app.post("/webhooks/unicom360/whatsapp")
def whatsapp_webhook():
    try:
        event = webhooks.construct_event(request.get_data(), request.headers, SECRET)
    except SignatureVerificationError as error:
        return error.reason, 401
    handle(event)
    return "", 200
```

**Django**

```python
def whatsapp_webhook(request):  # route csrf_exempt(whatsapp_webhook), POST only
    try:
        event = webhooks.construct_event(request.body, request.headers, SECRET)
    except SignatureVerificationError as error:
        return HttpResponse(error.reason, status=401)
    handle(event)
    return HttpResponse(status=200)
```

**FastAPI**

```python
@app.post("/webhooks/unicom360/whatsapp")
async def whatsapp_webhook(request: Request) -> Response:
    body = await request.body()
    try:
        event = webhooks.construct_event(body, request.headers, SECRET)
    except SignatureVerificationError as error:
        return Response(error.reason, status_code=401)
    handle(event)
    return Response(status_code=200)
```

Full versions: [`examples/webhook_flask.py`](examples/webhook_flask.py),
[`examples/webhook_django.py`](examples/webhook_django.py),
[`examples/webhook_fastapi.py`](examples/webhook_fastapi.py).

Good to know:

* Deliveries are retried on any non-2xx (after 30 s, 2 min, 10 min, 30 min, 1 h, 3 h, 6 h and
  12 h). Answer 2xx quickly and drop repeats by `event.delivery_id`.
* `verify` rejects a timestamp more than `tolerance` seconds (300 by default) from your clock,
  in either direction.
* In `message.received`: a media caption arrives in `text`, not in `media`; `payload` is set only
  for location, contacts (`{"contacts": [...]}`), reaction, sticker and unsupported messages; an
  interactive or button reply has the chosen title in `text`, `payload` is `None`, and
  `reply_to` is the `wamid.` id of your interactive message (the button or row id is not passed
  on).

## SMS and email delivery reports

The reports posted to an SMS or email `callback_url` are **unsigned and never retried**, so
anyone can post one: treat them as hints, and confirm anything that matters another way.

```python
report = webhooks.parse_sms_callback(raw_body)  # message_id, status, mobile_number
report = webhooks.parse_email_callback(raw_body)  # message_id, status, email_address, message
```

Both raise `Unicom360Error` for a body that is not a JSON object. The email report's numeric
`message_id` becomes the string the send returned.

## GSM-7 helpers

The gateway accepts only GSM-7 text (the basic set plus `^{}\[~]|€`, no form feed), at most
1,200 characters, and bills `max(1, ceil(length / 160))` units per recipient (a CR LF pair
counts as one character). The SDK never checks this itself; these opt-in helpers give the
gateway's answers before you send:

```python
from unicom360 import gsm

gsm.is_gsm7("Hello €")  # True
gsm.length("Hi\r\nthere")  # 8
gsm.units("a" * 161)  # 2
gsm.non_gsm_characters("It’s")  # [NonGsmCharacter(char='’', index=2)]
gsm.validate_sms("It’s ready")  # [SmsIssue.NON_GSM]; also EMPTY and TOO_LONG
```

`SmsIssue` values compare equal to the strings `"empty"`, `"too_long"` and `"non_gsm"`.
`gsm.CHARSET`, `gsm.MAX_LENGTH` and `gsm.UNIT_LENGTH` are the gateway's values.

## Configuration

```python
Unicom360(
    api_key=None,  # default: UNICOM360_API_KEY
    base_url=None,  # default: UNICOM360_BASE_URL, else https://api.unicom360.com
    timeout=60.0,  # seconds per attempt, sending to the end of the body
    connect_timeout=10.0,  # seconds to connect, TLS included
    max_retries=2,
    max_retry_wait=60.0,
    auto_reference_ids=False,
    app_info=None,  # AppInfo("shopsync", "2.3.0", "https://shopsync.example")
    transport=None,  # see below
    logger=None,  # default: logging.getLogger("unicom360")
)
```

* A missing or blank API key raises `ConfigurationError` when the client is built. An explicit
  `api_key=""` does not fall back to the environment.
* `base_url` must be `https`; plain `http` is allowed only for `localhost`, `127.0.0.0/8` and
  `::1` (for a local mock). A path prefix is kept, trailing slashes are dropped, and a query
  string or fragment is refused.
* Redirects are never followed, so the API key is never sent to another host.
* The client is immutable and safe to share between threads.
  `client.with_options(timeout=5)` returns a copy with other options.
* `app_info` is appended to the User-Agent
  (`unicom360-python/0.1.0 (CPython 3.12.4; linux; x86_64) shopsync/2.3.0 (+https://shopsync.example)`).
* The API key never appears in `repr(client)`, in exceptions or in logs.

**Transport.** The default transport uses `urllib.request`, honours the usual proxy environment
variables (`HTTPS_PROXY`, `NO_PROXY`) and takes an `ssl.SSLContext`
(`UrllibTransport(ssl_context=...)`). Any object with a `send(request) -> Response` method can
replace it (another HTTP library, a fake in your tests); raise `unicom360.TransportError(sent=...,
timeout=...)` when no response arrives, saying whether the request may have reached the server.

**Async.** Version 0.1 is synchronous. An `AsyncUnicom360` on an optional `httpx` extra is planned
for 0.2; until then, call the client from a worker thread (`asyncio.to_thread`).

## Logging

The SDK logs through the standard `logging` module, on the `"unicom360"` logger (or the
`logger=` you pass), and adds no handlers of its own:

```python
import logging

logging.basicConfig()
logging.getLogger("unicom360").setLevel(logging.DEBUG)
```

* DEBUG: one line per attempt with the method, path, status (or the transport failure),
  `api_reference`, attempt number and duration, plus any generated `user_reference_id`.
* INFO: one line per scheduled retry with the attempt, the wait and the cause.

Nothing else is logged: never a body, a header, a parameter, a phone number, an address, the API
key or a webhook secret.

## Known differences from the published docs

This SDK follows the gateway's actual behaviour (as written down in `openapi.yaml`). Where the
API reference at unicom360.com/docs says otherwise:

1. **Request-shape errors can carry several messages.** A 400 from the SMS or email endpoint can
   list one message per problem; `InvalidRequestError.message` joins them with `"; "`.
2. **WhatsApp balances are whole numbers today.** The docs say they can be fractional (`37.5`);
   the gateway currently rounds them. Balances are `Decimal`, so fractional values will work
   unchanged when the gateway sends them.
3. **Local number formats.** Only local numbers starting `095`, `096`, `097` and `076` are
   normalised; another local form (for example `077...`) comes back `Invalid mobile number`.
   Send international numbers (`2609...`).
4. **The SMS and email `callback_url` is not validated** by the gateway (the WhatsApp one is).
5. **The WhatsApp `callback_url` limit of 300 is in bytes**, so a non-ASCII URL reaches it sooner.
6. **A session `text` that is only whitespace is refused**, like an empty one.
7. **The health `timestamp` has microseconds** (`...30.412345Z`), not milliseconds.
8. **A session `DuplicateReferenceError` can have `original_message_id = None`** when two
   requests race for the same reference.
9. **Rejected template recipients echo the request's values**, which can be numbers; the SDK
   always gives `to` and `user_reference_id` as strings.
10. **The balance endpoints can refuse with `CLIENT_NOT_FOUND`** (HTTP 200, `status: false`, no
    `api_reference`), raised as `APIError`.
11. **An email `user_reference_id` does not stop two overlapping requests** from both being
    accepted (a sequential repeat is refused). That is why email is never retried after the
    request may have reached the gateway.

## Versioning

The SDK follows [Semantic Versioning](https://semver.org/) and starts at 0.1.0; 1.0.0 follows
once live use shows no differences from the spec. Changes are listed in
[CHANGELOG.md](CHANGELOG.md). Security reports: see [SECURITY.md](SECURITY.md). Contributing:
see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT, see [LICENSE](LICENSE). Copyright (c) 2026 Techrode Solutions Limited.
