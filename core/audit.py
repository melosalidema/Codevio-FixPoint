from __future__ import annotations

from typing import Any

from core.canonical import canonical_json, sha256_hex
from core.schemas import LedgerEntry, LedgerType

GENESIS = "0" * 64


class AuditLog:
    def __init__(self) -> None:
        self.entries: list[LedgerEntry] = []

    def append(self, run_id: str, entry_type: LedgerType, payload: dict[str, Any]) -> LedgerEntry:
        seq = len(self.entries)
        prev_hash = self.entries[-1].hash if self.entries else GENESIS
        body = {
            "seq": seq,
            "run_id": run_id,
            "type": entry_type.value,
            "payload": payload,
            "prev_hash": prev_hash,
        }
        digest = sha256_hex(canonical_json(body))
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
        prev = GENESIS
        for index, entry in enumerate(self.entries):
            if entry.seq != index:
                return False, f"seq_gap_at_{index}"
            if entry.prev_hash != prev:
                return False, f"broken_link_at_{index}"
            body = {
                "seq": entry.seq,
                "run_id": entry.run_id,
                "type": entry.type.value,
                "payload": entry.payload,
                "prev_hash": entry.prev_hash,
            }
            if sha256_hex(canonical_json(body)) != entry.hash:
                return False, f"tampered_at_{index}"
            prev = entry.hash
        return True, "ok"
