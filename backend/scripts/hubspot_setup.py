"""Validate a HubSpot private-app token and wire it into backend/.env.

This removes every step after the one only the account owner can do: copying
the Access token from the private app's Auth tab. The script:

1. validates the token against the live HubSpot API,
2. probes the notes scope (used for run-note sync and verification),
3. writes ``FIXPOINT_CRM_BACKEND=hubspot`` and ``FIXPOINT_HUBSPOT_TOKEN`` into
   ``.env`` (replacing the commented template lines),
4. optionally seeds demo data and restarts the launchd-managed backend.

The token is never printed.

Usage:
    cd backend
    python -m scripts.hubspot_setup --token pat-eu1-... --seed --restart
    # or omit --token to be prompted without echo
"""

from __future__ import annotations

import argparse
import getpass
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

API_BASE = "https://api.hubapi.com"
BACKEND_PATTERN = re.compile(r"^\s*#?\s*FIXPOINT_CRM_BACKEND=")
TOKEN_PATTERN = re.compile(r"^\s*#?\s*FIXPOINT_HUBSPOT_TOKEN=")
# Private-app access tokens: pat-<region>-<uuid>, e.g. pat-na1-... / pat-eu1-...
PRIVATE_APP_TOKEN = re.compile(r"^pat-[a-z0-9]+-[0-9a-fA-F-]{30,}$")
REQUIRED_SCOPES = {
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.notes.read",
    "crm.objects.notes.write",
}


def _get(token: str, path: str, params: dict[str, Any], transport: Any = None) -> httpx.Response:
    with httpx.Client(transport=transport, timeout=15) as client:
        return client.get(
            f"{API_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )


def fetch_token_info(token: str, transport: Any = None) -> dict[str, Any] | None:
    """Return hub id + scopes for a private-app token, or None if unavailable."""
    try:
        with httpx.Client(transport=transport, timeout=15) as client:
            response = client.post(
                f"{API_BASE}/oauth/v2/private-apps/get/access-token-info",
                json={"accessToken": token},
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def validate_token(token: str, transport: Any = None) -> tuple[bool, str]:
    """Confirm the token exists and can read contacts."""
    if not PRIVATE_APP_TOKEN.match(token):
        return (
            False,
            "not a private-app Access token. Access tokens start with 'pat-<region>-' "
            "(e.g. pat-na1-... or pat-eu1-...) and are copied from the app's Auth tab "
            "via 'Show token'. The Client ID and Client secret are different values.",
        )
    try:
        response = _get(token, "/crm/v3/objects/contacts", {"limit": 1}, transport)
    except httpx.HTTPError as error:
        return False, f"network error: {type(error).__name__}"
    if response.status_code == 401:
        return (
            False,
            "invalid token (401). Copy the Access token from Private App → Auth; "
            "it starts with 'pat-' (e.g. pat-eu1-...).",
        )
    if response.status_code == 403:
        return False, "token lacks the crm.objects.contacts.read scope"
    if response.status_code >= 400:
        return False, f"HubSpot returned HTTP {response.status_code}"
    return True, "contacts read ok"


def probe_notes_scope(token: str, transport: Any = None) -> tuple[bool, str]:
    """Best-effort check that notes read is granted (write cannot be probed safely)."""
    try:
        response = _get(token, "/crm/v3/objects/notes", {"limit": 1}, transport)
    except httpx.HTTPError as error:
        return False, f"network error: {type(error).__name__}"
    if response.status_code == 403:
        return False, "missing crm.objects.notes.read/write scope"
    if response.status_code >= 400:
        return False, f"HTTP {response.status_code}"
    return True, "notes scope ok"


def update_env(path: Path, token: str) -> None:
    """Enable the HubSpot CRM backend in .env, replacing commented lines."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    output: list[str] = []
    seen_backend = False
    seen_token = False
    for line in lines:
        if BACKEND_PATTERN.match(line):
            output.append("FIXPOINT_CRM_BACKEND=hubspot")
            seen_backend = True
        elif TOKEN_PATTERN.match(line):
            output.append(f"FIXPOINT_HUBSPOT_TOKEN={token}")
            seen_token = True
        else:
            output.append(line)
    if not seen_backend:
        output.append("FIXPOINT_CRM_BACKEND=hubspot")
    if not seen_token:
        output.append(f"FIXPOINT_HUBSPOT_TOKEN={token}")
    path.write_text("\n".join(output).rstrip("\n") + "\n", encoding="utf-8")


def restart_backend(backend_dir: Path) -> int:
    """Restart the launchd-managed backend, or print instructions elsewhere."""
    python = backend_dir / ".venv" / "bin" / "python"
    if sys.platform != "darwin" or shutil.which("launchctl") is None or not python.exists():
        print("Restart the backend to apply the change:")
        print(f"  cd {backend_dir} && .venv/bin/python -m uvicorn app.main:app --port 8000")
        return 0
    subprocess.run(["launchctl", "remove", "fixpoint-backend"], check=False, capture_output=True)
    command = (
        f"cd {backend_dir} && exec {python} -m uvicorn app.main:app --port 8000 "
        ">> /tmp/fixpoint-backend.log 2>&1"
    )
    result = subprocess.run(
        ["launchctl", "submit", "-l", "fixpoint-backend", "--", "/bin/zsh", "-lc", command],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"launchctl failed: {result.stderr.strip()}", file=sys.stderr)
        return 1
    print("Backend restarted under launchctl (:8000).")
    return 0


def main(argv: list[str] | None = None, transport: Any = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and install a HubSpot private-app token")
    parser.add_argument("--token", default="", help="private-app access token (pat-...); prompted if omitted")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="env file to update")
    parser.add_argument("--seed", action="store_true", help="also seed the demo contact")
    parser.add_argument("--with-duplicate", action="store_true", help="seed a duplicate-email contact")
    parser.add_argument("--create-status-property", action="store_true", help="create the status property")
    parser.add_argument("--restart", action="store_true", help="restart the launchd backend")
    args = parser.parse_args(argv)

    token = args.token or getpass.getpass("HubSpot private-app token (pat-...): ").strip()
    if not token:
        print("Error: no token supplied.", file=sys.stderr)
        return 1

    ok, detail = validate_token(token, transport)
    print(f"token: {detail}")
    if not ok:
        return 1

    info = fetch_token_info(token, transport)
    if info is not None:
        scopes = {str(scope) for scope in info.get("scopes") or []}
        hub = info.get("hubId") or info.get("hub_id") or "unknown"
        missing = REQUIRED_SCOPES - scopes
        print(f"portal {hub}: {len(scopes)} scope(s)" + (f"; missing {sorted(missing)}" if missing else ""))
        if missing:
            print("Add the missing scopes in the private app, then re-run.", file=sys.stderr)
            return 1
    else:
        notes_ok, notes_detail = probe_notes_scope(token, transport)
        print(f"notes scope: {notes_detail}")
        if not notes_ok:
            print(
                "Warning: run notes are required for sync/verification; fix the scopes.",
                file=sys.stderr,
            )
            return 1

    update_env(args.env_file, token)
    print(f"Updated {args.env_file}: FIXPOINT_CRM_BACKEND=hubspot, FIXPOINT_HUBSPOT_TOKEN=<set>")

    if args.seed:
        from scripts import hubspot_seed

        seed_argv = ["--yes"]
        if args.with_duplicate:
            seed_argv.append("--with-duplicate")
        if args.create_status_property:
            seed_argv.append("--create-status-property")
        if hubspot_seed.main(seed_argv) != 0:
            return 1

    if args.restart:
        return restart_backend(Path.cwd())

    print("Restart the backend to apply the change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
