"""Seed HubSpot CRM data for the Fixpoint demo.

Finds or creates the demo contact ``jane@acme.com`` and optionally a duplicate
for the ambiguity demo. Idempotent: repeated runs reuse existing contacts.

WARNING: HubSpot private-app tokens write to a REAL portal. There is no test
mode. Use a free developer test account or sandbox. This script prints a loud
warning and requires ``--yes`` (or an interactive confirmation) before writing.

Usage:
    python -m scripts.hubspot_seed --yes
    python -m scripts.hubspot_seed --yes --with-duplicate
    python -m scripts.hubspot_seed --yes --create-status-property
"""

from __future__ import annotations

import argparse
import os
import sys

from app.config import get_settings
from app.providers.hubspot_live import HubSpotLive
from app.providers.world import Contact, ProviderError

DEMO_EMAIL = "jane@acme.com"
DEMO_FIRSTNAME = "Jane"
DEMO_LASTNAME = "Doe"
SEED_TENANT = "seed"


def _create_contact(client: HubSpotLive, firstname: str, lastname: str) -> Contact:
    data = client._request(  # noqa: SLF001 - seeding uses the raw provider request
        "POST",
        "/crm/v3/objects/contacts",
        json_body={"properties": {"email": DEMO_EMAIL, "firstname": firstname, "lastname": lastname}},
    )
    contact = client.get_contact(SEED_TENANT, str(data.get("id", "")))
    if contact is None:
        raise ProviderError("hubspot", 500, "created contact could not be read back")
    return contact


def _ensure_status_property(client: HubSpotLive, name: str) -> bool:
    """Create the status property when missing. Returns True when created."""
    try:
        client._request("GET", f"/crm/v3/properties/contacts/{name}")  # noqa: SLF001
        return False
    except ProviderError as error:
        if error.status != 404:
            raise
    client._request(  # noqa: SLF001
        "POST",
        "/crm/v3/properties/contacts",
        json_body={
            "name": name,
            "label": "Fixpoint Status",
            "type": "string",
            "fieldType": "text",
            "groupName": "contactinformation",
        },
    )
    return True


def _confirm(assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print(
            "Error: refusing to write to a HubSpot portal non-interactively. Re-run with --yes.",
            file=sys.stderr,
        )
        return False
    print("WARNING: this writes to a REAL HubSpot portal (there is no test mode).")
    answer = input('Type "seed" to continue: ').strip()
    return answer == "seed"


def main(argv: list[str] | None = None, client: HubSpotLive | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed HubSpot CRM data for Fixpoint")
    parser.add_argument(
        "--token", default="", help="HubSpot private-app token (defaults to FIXPOINT_HUBSPOT_TOKEN)"
    )
    parser.add_argument("--with-duplicate", action="store_true", help="also create a duplicate-email contact")
    parser.add_argument(
        "--create-status-property",
        action="store_true",
        help="create the configured status property if missing (needs crm.schemas.contacts.write)",
    )
    parser.add_argument("--status-property", default="", help="status property name (default from settings)")
    parser.add_argument("--yes", action="store_true", help="skip the interactive confirmation")
    args = parser.parse_args(argv)

    settings = get_settings()
    status_property = args.status_property or settings.hubspot_status_property
    token = args.token or os.environ.get("FIXPOINT_HUBSPOT_TOKEN", "") or settings.hubspot_token

    if client is None:
        if not token:
            print(
                "Error: no HubSpot token. Set FIXPOINT_HUBSPOT_TOKEN or pass --token.", file=sys.stderr
            )
            return 1
        client = HubSpotLive(token, status_property=status_property)

    if not _confirm(args.yes):
        return 1

    print("WARNING: writes affect a real HubSpot portal; use a developer test account.")

    try:
        contacts = client.find_contacts(SEED_TENANT, email=DEMO_EMAIL)
        if len(contacts) > 1:
            print(f"Warning: {len(contacts)} contacts already match {DEMO_EMAIL}; reusing the first.")
        if contacts:
            contact = contacts[0]
            print(f"Reusing contact {contact.id} ({DEMO_EMAIL}).")
        else:
            contact = _create_contact(client, DEMO_FIRSTNAME, DEMO_LASTNAME)
            print(f"Created contact {contact.id} ({DEMO_EMAIL}).")

        if args.with_duplicate and len(contacts) < 2:
            duplicate = _create_contact(client, DEMO_FIRSTNAME, f"{DEMO_LASTNAME} (duplicate)")
            print(f"Created duplicate contact {duplicate.id} for the ambiguity demo.")
            print("Note: portals with 'unique email' enabled will reject this.")
        elif args.with_duplicate:
            print("Duplicate contacts already present; nothing to create.")

        created_property = False
        if args.create_status_property:
            created_property = _ensure_status_property(client, status_property)
            print(
                f"Status property '{status_property}' "
                + ("created." if created_property else "already exists.")
            )
    except ProviderError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print("\nSeed complete.")
    print(f"  contact:  {contact.id} ({DEMO_EMAIL})")
    print(f"  duplicates: {'yes' if args.with_duplicate else 'no'}")
    if args.create_status_property:
        print(f"  status property: {status_property}")
    print("\nSuggested Fixpoint run text:")
    print(f'  "I was double charged, please refund the duplicate charge for {DEMO_EMAIL}"')
    print("  amount_cents=4200 ($42.00)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
