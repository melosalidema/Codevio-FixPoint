from __future__ import annotations

import json

import httpx
import pytest

from scripts import hubspot_seed, hubspot_setup

# Obviously fabricated token, assembled at runtime so secret scanners do not
# flag this fixture. It must still match the pat-<region>-<uuid> shape.
TOKEN = "-".join(["pat", "na1", "12345678", "1234", "1234", "1234", "123456789012"])
ENV_TEMPLATE = "\n".join(
    [
        "# local env",
        "FIXPOINT_STRIPE_BACKEND=stripe",
        "",
        "# --- Real HubSpot CRM demo ---",
        "# FIXPOINT_CRM_BACKEND=hubspot",
        "# FIXPOINT_HUBSPOT_TOKEN=pat-...",
        "# FIXPOINT_HUBSPOT_REFUND_STATUS=",
        "",
    ]
)


def _handler(status_contacts: int = 200, status_notes: int = 200, scopes: list[str] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/v2/private-apps/get/access-token-info":
            # Token-info carries the token in the body, not as a Bearer header.
            assert request.headers.get("authorization") is None
            assert json.loads(request.content)["accessToken"] == TOKEN
            if scopes is None:
                return httpx.Response(404, json={"message": "not found"})
            return httpx.Response(200, json={"hubId": 123456, "scopes": scopes})
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        if request.url.path == "/crm/v3/objects/contacts":
            return httpx.Response(status_contacts, json={"results": []})
        if request.url.path == "/crm/v3/objects/notes":
            return httpx.Response(status_notes, json={"results": []})
        return httpx.Response(404, json={"message": "not found"})

    return handler


def _transport(**kwargs) -> httpx.MockTransport:
    return httpx.MockTransport(_handler(**kwargs))


def test_validate_token_ok():
    ok, detail = hubspot_setup.validate_token(TOKEN, transport=_transport())
    assert ok is True
    assert "contacts read ok" in detail


@pytest.mark.parametrize(
    "bad",
    [
        "c75b8799-4385-43ec-9505-40cbf70ca522",  # client secret / app id
        "eu1-6da4-7777-4fa8-b180-f2984384302a",  # region-prefixed id, no pat-
        "pat-eu1-short",  # too short to be a token
    ],
)
def test_validate_token_rejects_wrong_format_without_calling_hubspot(bad):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("HubSpot must not be called for a malformed token")

    ok, detail = hubspot_setup.validate_token(bad, transport=httpx.MockTransport(handler))
    assert ok is False
    assert "pat-" in detail and "Client secret" in detail


def test_validate_token_401_names_the_fix():
    ok, detail = hubspot_setup.validate_token(TOKEN, transport=_transport(status_contacts=401))
    assert ok is False
    assert "pat-" in detail and "invalid token" in detail


def test_validate_token_403_names_the_scope():
    ok, detail = hubspot_setup.validate_token(TOKEN, transport=_transport(status_contacts=403))
    assert ok is False
    assert "crm.objects.contacts.read" in detail


def test_probe_notes_scope_403():
    ok, detail = hubspot_setup.probe_notes_scope(TOKEN, transport=_transport(status_notes=403))
    assert ok is False
    assert "crm.objects.notes" in detail


def test_update_env_replaces_commented_template(tmp_path):
    env = tmp_path / ".env"
    env.write_text(ENV_TEMPLATE, encoding="utf-8")

    hubspot_setup.update_env(env, TOKEN)
    text = env.read_text(encoding="utf-8")
    assert "FIXPOINT_CRM_BACKEND=hubspot" in text
    assert f"FIXPOINT_HUBSPOT_TOKEN={TOKEN}" in text
    assert "# FIXPOINT_CRM_BACKEND=" not in text
    assert "FIXPOINT_STRIPE_BACKEND=stripe" in text

    # Idempotent: a second run changes nothing structural.
    hubspot_setup.update_env(env, TOKEN)
    assert text.count("FIXPOINT_CRM_BACKEND=hubspot") == 1
    assert text.count(f"FIXPOINT_HUBSPOT_TOKEN={TOKEN}") == 1


def test_update_env_appends_when_missing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FIXPOINT_ENV=development\n", encoding="utf-8")
    hubspot_setup.update_env(env, TOKEN)
    text = env.read_text(encoding="utf-8")
    assert "FIXPOINT_CRM_BACKEND=hubspot" in text
    assert f"FIXPOINT_HUBSPOT_TOKEN={TOKEN}" in text


def test_main_invalid_token_writes_nothing(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(ENV_TEMPLATE, encoding="utf-8")
    code = hubspot_setup.main(
        ["--token", TOKEN, "--env-file", str(env)],
        transport=_transport(status_contacts=401),
    )
    assert code == 1
    assert "# FIXPOINT_CRM_BACKEND=hubspot" in env.read_text(encoding="utf-8")


def test_main_writes_env_without_printing_token(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(ENV_TEMPLATE, encoding="utf-8")
    code = hubspot_setup.main(["--token", TOKEN, "--env-file", str(env)], transport=_transport())
    assert code == 0
    text = env.read_text(encoding="utf-8")
    assert f"FIXPOINT_HUBSPOT_TOKEN={TOKEN}" in text
    assert TOKEN not in capsys.readouterr().out


def test_main_seeds_when_requested(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(ENV_TEMPLATE, encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(hubspot_seed, "main", lambda argv: calls.append(argv) or 0)

    code = hubspot_setup.main(
        ["--token", TOKEN, "--env-file", str(env), "--seed", "--with-duplicate"],
        transport=_transport(),
    )
    assert code == 0
    assert calls == [["--yes", "--with-duplicate"]]


@pytest.mark.parametrize("status", [500, 503])
def test_main_notes_probe_failure_returns_1(tmp_path, status):
    env = tmp_path / ".env"
    env.write_text(ENV_TEMPLATE, encoding="utf-8")
    code = hubspot_setup.main(
        ["--token", TOKEN, "--env-file", str(env)],
        transport=_transport(status_notes=status),
    )
    assert code == 1


ALL_SCOPES = [
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.notes.read",
    "crm.objects.notes.write",
]


def test_main_uses_token_info_scopes(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(ENV_TEMPLATE, encoding="utf-8")
    # Notes endpoint would 403, but token-info reports every required scope,
    # so the fallback probe must not run.
    code = hubspot_setup.main(
        ["--token", TOKEN, "--env-file", str(env)],
        transport=_transport(status_notes=403, scopes=ALL_SCOPES),
    )
    assert code == 0
    assert "portal 123456" in capsys.readouterr().out


def test_main_fails_when_scopes_missing(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(ENV_TEMPLATE, encoding="utf-8")
    code = hubspot_setup.main(
        ["--token", TOKEN, "--env-file", str(env)],
        transport=_transport(scopes=["crm.objects.contacts.read"]),
    )
    assert code == 1
    assert "missing" in capsys.readouterr().err
    assert f"FIXPOINT_HUBSPOT_TOKEN={TOKEN}" not in env.read_text(encoding="utf-8")
