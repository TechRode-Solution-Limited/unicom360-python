"""Check that the gateway is up. Sends no API key, but the client still needs one configured.

UNICOM360_API_KEY=... python examples/health.py
"""

from __future__ import annotations

import logging

from unicom360 import APIConnectionError, Unicom360


def main() -> None:
    # One debug line per attempt (method, path, status, api_reference, attempt, duration).
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("unicom360").setLevel(logging.DEBUG)

    client = Unicom360(timeout=10, max_retries=1)
    try:
        health = client.health()
    except APIConnectionError as error:
        raise SystemExit(f"Unreachable: {error}") from error
    print(health.status, health.version, health.environment, health.timestamp)


if __name__ == "__main__":
    main()
