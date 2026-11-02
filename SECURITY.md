# Security policy

## Reporting a vulnerability

Please report security problems privately, never in a public issue or pull request.

* **GitHub:** use private vulnerability reporting on this repository (the "Security" tab, then
  "Report a vulnerability").
* **Email:** info@techrode.co, with "Security" in the subject.

Tell us what is affected, how to reproduce it, and what an attacker could do with it. We
acknowledge reports within three working days and keep you informed until it is fixed.

## Scope

This repository is the official Python SDK for the Unicom360 API. In scope: anything in the SDK
that could expose an API key or a webhook secret (in logs, exceptions or `repr`), accept a
forged or replayed webhook, send a request somewhere other than the configured base URL, or
repeat a send that should not be repeated.

The webhook secrets in `tests/conformance` are throwaway test vectors, not credentials.
Problems in the Unicom360 API itself can be sent to the same address.

## Supported versions

Only the latest release receives security fixes.
