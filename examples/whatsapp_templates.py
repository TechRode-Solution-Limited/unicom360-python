"""List the approved WhatsApp templates and the parameters each expects.

UNICOM360_API_KEY=... python examples/whatsapp_templates.py
"""

from __future__ import annotations

from unicom360 import Unicom360


def main() -> None:
    client = Unicom360()
    listing = client.whatsapp.templates()
    for template in listing.templates:
        variables = template.body.variables if template.body else []
        print(template.name, template.language, template.category, variables)
    order_ready = listing.by_name("order_ready", "en_US")
    if order_ready is not None and order_ready.header is not None:
        print("order_ready header:", order_ready.header.type)


if __name__ == "__main__":
    main()
