"""Tamper-evident audit trail."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class AuditRecord:
    tick: int
    payload: dict[str, Any]
    previous_hash: str
    digest: str


class AuditLog:
    """Append-only hash chain for governance decisions."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    def append(self, tick: int, payload: dict[str, Any]) -> AuditRecord:
        previous_hash = self._records[-1].digest if self._records else "GENESIS"
        body = {
            "tick": tick,
            "payload": payload,
            "previous_hash": previous_hash,
        }
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        record = AuditRecord(
            tick=tick,
            payload=payload,
            previous_hash=previous_hash,
            digest=digest,
        )
        self._records.append(record)
        return record

    def verify(self) -> bool:
        previous_hash = "GENESIS"
        for record in self._records:
            body = {
                "tick": record.tick,
                "payload": record.payload,
                "previous_hash": previous_hash,
            }
            encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            expected = hashlib.sha256(encoded).hexdigest()
            if expected != record.digest:
                return False
            previous_hash = record.digest
        return True

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(record) for record in self._records]
