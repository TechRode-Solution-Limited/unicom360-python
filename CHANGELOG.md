# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-04

First release, targeting the Unicom360 API contract v0.1.0.

### Added

- `Unicom360` client (synchronous, no dependencies) with every operation of the public API:
  `sms.send`, `email.send`, `whatsapp.send_template`, `whatsapp.send_session`,
  `whatsapp.status`, `whatsapp.templates`, `balance.get`, `balance.all` and `health`.
- Typed, immutable result models that keep unknown fields (`extra`) and the parsed JSON
  (`raw`), with lookup helpers (`by_number`, `by_address`, `by_id`, `by_name`, `accepted`,
  `invalid`, `rejected`). Balances are `decimal.Decimal`.
- Builders for template parameters (`TemplateHeader`, `TemplateBody`, `TemplateButton`,
  `TemplateRecipient`) and session messages (`unicom360.session`).
- The error hierarchy rooted at `Unicom360Error`, with error codes normalised from the
  gateway's messages (`unicom360.codes`, `normalize_code`).
- Safe automatic retries (429, failures before sending, and 5xx, failures after sending and
  `SEND_FAILED` on retry-safe calls only), with UTC-minute waits after a 429 and full-jitter
  backoff otherwise; the `auto_reference_ids` option.
- Webhook verification and parsing (`unicom360.webhooks.verify`, `construct_event`) and the
  unsigned SMS and email delivery reports (`parse_sms_callback`, `parse_email_callback`). A
  secret that is `None`, empty or only whitespace raises `ConfigurationError` before any other
  check, because anyone can forge a signature with an empty key.
- Opt-in GSM-7 helpers (`unicom360.gsm`).
- A pluggable transport (`Transport`, `TransportError`) with a standard-library default
  (`UrllibTransport`) that never follows redirects.
- Logging through `logging.getLogger("unicom360")`, with the API key and webhook secrets
  redacted everywhere.
- The contract's conformance suite (v0.1.0), a Prism contract test, examples for every
  operation and webhook receivers for Flask, Django and FastAPI.

[0.1.0]: https://github.com/TechRode-Solution-Limited/unicom360-python/releases/tag/v0.1.0
