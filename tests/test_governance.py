from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from dcf.audit import AuditLog
from dcf.core import (
    ActionType,
    ContextInjector,
    DecisionEngine,
    Envelope,
    Telemetry,
    default_candidates,
    default_field,
    default_invariants,
)
from dcf.knowledge import KnowledgeGraph, KnowledgeObject
from dcf.market import AgentBid, BrokeredMarket
from dcf.visual_server import VisualSimulation


def make_engine() -> DecisionEngine:
    field = default_field()
    return DecisionEngine(field, ContextInjector(field), default_invariants(), AuditLog())


class GovernanceTests(unittest.TestCase):
    def test_low_confidence_contracts_to_safe_subset(self) -> None:
        engine = make_engine()
        telemetry = Telemetry(
            radiation=0.2,
            sensor_confidence=0.2,
            fuel_remaining=0.2,
            power_remaining=0.2,
            storage_remaining=0.9,
            communication_latency=9.0,
            instrument_health=0.4,
            science_bay_pressure=0.0,
            trajectory_intersects_atmosphere=False,
            reactor_temperature=0.3,
        )
        decision = engine.decide(telemetry, default_candidates())
        self.assertEqual(decision.envelope, Envelope.SAFE_SUBSET)
        self.assertIn(decision.selected.action_type, {ActionType.OBSERVE, ActionType.LOG, ActionType.BEACON})
        self.assertTrue(any(rejection.reason == "envelope:safe_subset" for rejection in decision.rejected))

    def test_invariant_overrides_candidate_scoring(self) -> None:
        engine = make_engine()
        telemetry = Telemetry(
            radiation=0.1,
            sensor_confidence=0.95,
            fuel_remaining=0.9,
            power_remaining=0.9,
            storage_remaining=0.9,
            communication_latency=0.1,
            instrument_health=0.98,
            science_bay_pressure=0.01,
            trajectory_intersects_atmosphere=False,
            reactor_temperature=0.3,
        )
        decision = engine.decide(telemetry, default_candidates())
        self.assertEqual(decision.selected.action_type, ActionType.HALT)
        self.assertEqual(decision.invariant_name, "Vacuum Integrity")
        self.assertEqual(len(decision.rejected), len(default_candidates()))

    def test_audit_log_detects_tampering(self) -> None:
        engine = make_engine()
        telemetry = Telemetry(0.1, 0.9, 0.9, 0.9, 0.9, 0.5, 0.9, 0.0, False, 0.2)
        engine.decide(telemetry, default_candidates())
        self.assertTrue(engine.audit.verify())
        engine.audit.records[0].payload["selected_action"] = "tampered"
        self.assertFalse(engine.audit.verify())

    def test_knowledge_rollback_revokes_descendants(self) -> None:
        graph = KnowledgeGraph()
        graph.propose(KnowledgeObject("root", "root tactic"))
        graph.sandbox_result("root", True)
        graph.corroborate("root", "a")
        graph.corroborate("root", "b")
        graph.propose(KnowledgeObject("child", "derived tactic", parents={"root"}))
        graph.sandbox_result("child", True)
        graph.corroborate("child", "c")
        graph.corroborate("child", "d")
        self.assertEqual(graph.adopted(), {"root", "child"})
        self.assertEqual(graph.revoke("root", "bad data"), {"root", "child"})
        self.assertEqual(graph.adopted(), set())

    def test_market_allocates_highest_value_per_unit(self) -> None:
        market = BrokeredMarket()
        allocations = market.allocate(
            {"power": 10},
            [
                AgentBid("geology", "power", 8, 0.9, 0.2),
                AgentBid("physics", "power", 5, 0.7, 0.1),
                AgentBid("navigation", "power", 5, 0.6, 0.2),
            ],
        )
        self.assertEqual([bid.agent for bid in allocations["power"]], ["physics", "navigation"])

    def test_visual_simulation_writes_jsonl_tick_log(self) -> None:
        with TemporaryDirectory() as directory:
            log_path = Path(directory) / "visual.jsonl"
            simulation = VisualSimulation(log_path)
            payload = simulation.tick(
                {
                    "radiation": 0.1,
                    "sensor_confidence": 0.9,
                    "fuel_remaining": 0.9,
                    "power_remaining": 0.9,
                    "storage_remaining": 0.8,
                    "communication_latency": 0.5,
                    "instrument_health": 0.95,
                    "science_bay_pressure": 0.0,
                    "trajectory_intersects_atmosphere": False,
                    "reactor_temperature": 0.3,
                    "science_bias": 0.5,
                    "resource_caution": 0.5,
                    "alignment_bias": 0.5,
                }
            )
            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn("commentary", payload)
            self.assertIn('"tick": 1', lines[0])


if __name__ == "__main__":
    unittest.main()
