from __future__ import annotations

from app.safety.audit import AuditLog, verify_entries
from app.safety.models import LedgerType


def test_chain_stays_valid():
    log = AuditLog()
    log.append("run_1", LedgerType.PLAN, {"a": 1})
    log.append("run_1", LedgerType.MUTATION, {"b": 2})
    log.append("run_1", LedgerType.VERIFICATION, {"c": 3})
    ok, reason = log.verify_chain()
    assert ok and reason == "ok"


def test_tamper_is_detected():
    log = AuditLog()
    log.append("run_1", LedgerType.PLAN, {"a": 1})
    log.append("run_1", LedgerType.MUTATION, {"b": 2})
    log.entries[0].payload["a"] = 999
    ok, reason = log.verify_chain()
    assert not ok
    assert reason.startswith("tampered_at_")


def test_broken_link_detected():
    log = AuditLog()
    log.append("run_1", LedgerType.PLAN, {"a": 1})
    log.append("run_1", LedgerType.PLAN, {"b": 2})
    log.entries[1].prev_hash = "0" * 64
    ok, reason = log.verify_chain()
    assert not ok


def test_verify_entries_works_on_loaded_rows():
    log = AuditLog()
    log.append("run_1", LedgerType.PLAN, {"a": 1})
    log.append("run_1", LedgerType.REPORT, {"b": 2})
    ok, reason = verify_entries(list(log.entries))
    assert ok and reason == "ok"
