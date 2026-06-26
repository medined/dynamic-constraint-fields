"""Knowledge object governance with DAG rollback."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KnowledgeObject:
    key: str
    description: str
    parents: set[str] = field(default_factory=set)
    sandbox_passed: bool = False
    corroborating_sources: set[str] = field(default_factory=set)
    adopted: bool = False
    revoked: bool = False


class KnowledgeGraph:
    """Tracks learning adoption and revokes poisoned descendants."""

    def __init__(self, required_sources: int = 2) -> None:
        self.required_sources = required_sources
        self.objects: dict[str, KnowledgeObject] = {}

    def propose(self, ko: KnowledgeObject) -> None:
        missing = ko.parents - self.objects.keys()
        if missing:
            raise ValueError(f"unknown parent knowledge objects: {sorted(missing)}")
        self.objects[ko.key] = ko

    def sandbox_result(self, key: str, passed: bool) -> None:
        ko = self.objects[key]
        ko.sandbox_passed = passed
        self._refresh_adoption(ko)

    def corroborate(self, key: str, source: str) -> None:
        ko = self.objects[key]
        ko.corroborating_sources.add(source)
        self._refresh_adoption(ko)

    def revoke(self, key: str, reason: str) -> set[str]:
        if key not in self.objects:
            raise KeyError(key)
        affected = {key}
        changed = True
        while changed:
            changed = False
            for candidate in self.objects.values():
                if candidate.key in affected:
                    continue
                if candidate.parents & affected:
                    affected.add(candidate.key)
                    changed = True
        for affected_key in affected:
            ko = self.objects[affected_key]
            ko.revoked = True
            ko.adopted = False
            ko.description = f"{ko.description} [REVOKED: {reason}]"
        return affected

    def adopted(self) -> set[str]:
        return {key for key, ko in self.objects.items() if ko.adopted and not ko.revoked}

    def _refresh_adoption(self, ko: KnowledgeObject) -> None:
        parents_adopted = all(self.objects[parent].adopted for parent in ko.parents)
        enough_sources = len(ko.corroborating_sources) >= self.required_sources
        ko.adopted = ko.sandbox_passed and enough_sources and parents_adopted and not ko.revoked
