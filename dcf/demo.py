"""Runnable proof-of-concept scenario."""

from __future__ import annotations

from dcf.audit import AuditLog
from dcf.core import (
    ContextInjector,
    DecisionEngine,
    Telemetry,
    default_candidates,
    default_field,
    default_invariants,
)
from dcf.knowledge import KnowledgeGraph, KnowledgeObject
from dcf.market import AgentBid, BrokeredMarket


def build_engine() -> DecisionEngine:
    field = default_field()
    injector = ContextInjector(field)
    return DecisionEngine(field, injector, default_invariants(), AuditLog())


def run_governance_demo() -> None:
    engine = build_engine()
    scenarios = [
        Telemetry(0.1, 0.94, 0.9, 0.86, 0.8, 0.8, 0.95, 0.0, False, 0.4),
        Telemetry(0.85, 0.72, 0.62, 0.45, 0.7, 3.0, 0.68, 0.0, False, 0.5),
        Telemetry(0.25, 0.35, 0.4, 0.38, 0.9, 7.5, 0.55, 0.0, False, 0.5),
        Telemetry(0.2, 0.9, 0.8, 0.8, 0.8, 0.8, 0.95, 0.02, False, 0.4),
    ]
    for telemetry in scenarios:
        decision = engine.decide(telemetry, default_candidates())
        print(f"tick={decision.tick}")
        print(f"  envelope={decision.envelope.value} confidence={decision.confidence:.3f}")
        print(f"  selected={decision.selected.name} score={decision.score:.3f}")
        if decision.invariant_response:
            print(f"  invariant={decision.invariant_name} response={decision.invariant_response.value}")
        if decision.rejected:
            reasons = ", ".join(f"{item.action}:{item.reason}" for item in decision.rejected)
            print(f"  rejected={reasons}")
        print(f"  audit_hash={decision.audit_record.digest[:16]}")
    print(f"audit_verified={engine.audit.verify()}")


def run_market_demo() -> None:
    market = BrokeredMarket()
    bids = [
        AgentBid("Geological Agent", "instrument_minutes", 20, 0.9, 0.25),
        AgentBid("Physics Agent", "instrument_minutes", 12, 0.7, 0.1),
        AgentBid("Navigation Agent", "instrument_minutes", 8, 0.55, 0.05),
    ]
    allocations = market.allocate({"instrument_minutes": 30}, bids)
    winners = [bid.agent for bid in allocations["instrument_minutes"]]
    print(f"market_winners={winners}")


def run_knowledge_demo() -> None:
    graph = KnowledgeGraph()
    graph.propose(KnowledgeObject("calibration-v1", "New spectrometer calibration tactic"))
    graph.sandbox_result("calibration-v1", True)
    graph.corroborate("calibration-v1", "ground-sim")
    graph.corroborate("calibration-v1", "peer-agent")
    graph.propose(
        KnowledgeObject(
            "assay-policy-v2",
            "Assay targeting policy derived from calibration-v1",
            parents={"calibration-v1"},
        )
    )
    graph.sandbox_result("assay-policy-v2", True)
    graph.corroborate("assay-policy-v2", "physics-agent")
    graph.corroborate("assay-policy-v2", "earth-review")
    print(f"adopted_before_revoke={sorted(graph.adopted())}")
    revoked = graph.revoke("calibration-v1", "poisoned source stream")
    print(f"revoked={sorted(revoked)} adopted_after_revoke={sorted(graph.adopted())}")


if __name__ == "__main__":
    run_governance_demo()
    run_market_demo()
    run_knowledge_demo()
