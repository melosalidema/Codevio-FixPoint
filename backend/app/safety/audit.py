from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.safety.canonical import canonical_json, sha256_hex
from app.safety.models import LedgerEntry, LedgerType

GENESIS = "0" * 64


def entry_hash(
    seq: int, run_id: str, entry_type: LedgerType | str, payload: dict[str, Any], prev_hash: str
) -> str:
    """Hash of one ledger entry, chained to the previous entry's hash."""
    type_value = entry_type.value if isinstance(entry_type, LedgerType) else entry_type
    body = {
        "seq": seq,
        "run_id": run_id,
        "type": type_value,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    return sha256_hex(canonical_json(body))


class AuditLog:
    """In-memory append-only ledger built during a run.

    Entries are persisted to Postgres by the repository; verification works on
    either the in-memory list or entries loaded back from the database.
    """

    def __init__(self) -> None:
        self.entries: list[LedgerEntry] = []

    def append(self, run_id: str, entry_type: LedgerType, payload: dict[str, Any]) -> LedgerEntry:
        seq = len(self.entries)
        prev_hash = self.entries[-1].hash if self.entries else GENESIS
        digest = entry_hash(seq, run_id, entry_type, payload, prev_hash)
        entry = LedgerEntry(
            seq=seq,
            run_id=run_id,
            type=entry_type,
            payload=payload,
            prev_hash=prev_hash,
            hash=digest,
        )
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> tuple[bool, str]:
        return verify_entries(self.entries)


def verify_entries(entries: Iterable[LedgerEntry]) -> tuple[bool, str]:
    """Recompute the hash chain over an ordered list of entries.

    Any gap, broken link, or mutated payload makes verification fail with the
    exact index where the chain diverges.
    """
    prev = GENESIS
    for index, entry in enumerate(entries):
        if entry.seq != index:
            return False, f"seq_gap_at_{index}"
        if entry.prev_hash != prev:
            return False, f"broken_link_at_{index}"
        expected = entry_hash(entry.seq, entry.run_id, entry.type, entry.payload, entry.prev_hash)
        if expected != entry.hash:
            return False, f"tampered_at_{index}"
        prev = entry.hash
    return True, "ok"
