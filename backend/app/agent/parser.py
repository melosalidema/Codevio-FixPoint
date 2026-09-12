from __future__ import annotations

import re

from app.safety.models import ParsedFacts

# Heuristics that flag attacker-influenceable instructions. Flags never block
# on their own; they inform the gateway and the audit trail.
INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r"ignore\s+(the\s+)?(policy|previous|prior|all)?\s*(instructions|rules)?", "ignore_policy"),
    (r"disregard\s+(the\s+)?(policy|rules|instructions)", "disregard_policy"),
    (r"^\s*system\s*:", "fake_system_role"),
    (r"refund\s+.{0,40}\bto\b\s+.{0,30}(card|account|new)", "redirect_destination"),
    (r"new\s+card", "new_card_destination"),
    (r"forward\s+.{0,30}(records|data|transcript).{0,20}(external|outside|to)", "external_exfil"),
    (r"\b(delete|remove|destroy)\b.{0,30}\b(record|customer|account|log)", "delete_request"),
    (r"169\.254\.169\.254|metadata\.google|/latest/meta-data", "ssrf_metadata"),
    (r"(reveal|print|show|repeat).{0,30}(system\s*prompt|instructions)", "prompt_extraction"),
    (r"attacker|evil\.com|@example\.evil", "known_attacker_marker"),
]

AMOUNT_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
ORDER_RE = re.compile(r"(?:order|invoice|charge)\s*#?\s*([A-Za-z0-9\-]{3,})", re.IGNORECASE)
CARD_RE = re.compile(r"(?:card|account)\D{0,20}(\d{4})", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
HASH_ID_RE = re.compile(r"\b(ch_[A-Za-z0-9]+)\b")


def _to_cents(raw: str) -> int:
    return int(round(float(raw.replace(",", "")) * 100))


def parse(text: str) -> ParsedFacts:
    """Quarantine parser: untrusted text -> strict structured facts.

    This implementation is deterministic (no LLM, no tools). It only extracts
    data; it cannot act, so a successful injection in the text cannot cause a
    mutation by itself.
    """
    injection_flags = [
        label
        for pattern, label in INJECTION_PATTERNS
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    ]
    amount = None
    match = AMOUNT_RE.search(text)
    if match:
        amount = _to_cents(match.group(1))

    requested = "unknown"
    lowered = text.lower()
    if "refund" in lowered or "refunded" in lowered:
        requested = "refund"
    if "store credit" in lowered:
        requested = "store_credit"
    if re.search(r"\bdeny\b|\breject\b|\bdo not refund\b", lowered):
        requested = "deny"

    order_match = ORDER_RE.search(text)
    card_match = CARD_RE.search(text)
    email_match = EMAIL_RE.search(text)
    charge_match = HASH_ID_RE.search(text)

    return ParsedFacts(
        customer_email=email_match.group(0) if email_match else None,
        order_id=order_match.group(1) if order_match else (charge_match.group(1) if charge_match else None),
        requested_action=requested,
        amount_cents=amount,
        destination=f"card_{card_match.group(1)}" if card_match else None,
        injection_flags=injection_flags,
        raw_excerpt=text.strip()[:500],
    )
