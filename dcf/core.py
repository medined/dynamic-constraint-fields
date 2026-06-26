"""Core governance sphere implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from dcf.audit import AuditLog, AuditRecord


class InvariantResponse(str, Enum):
    HALT = "HALT"
    FALLBACK = "FALLBACK"
    ESCALATE = "ESCALATE"


class Envelope(str, Enum):
    FULL = "FULL"
    CAUTIOUS = "CAUTIOUS"
    SAFE_SUBSET = "SAFE_SUBSET"


class ActionType(str, Enum):
    OBSERVE = "OBSERVE"
    LOG = "LOG"
    BEACON = "BEACON"
    REPOSITION_SENSOR = "REPOSITION_SENSOR"
    ORIENT_TELESCOPE = "ORIENT_TELESCOPE"
    HIGH_RES_CAPTURE = "HIGH_RES_CAPTURE"
    SAMPLE_CONSUMPTION = "SAMPLE_CONSUMPTION"
    FIRE_THRUSTERS = "FIRE_THRUSTERS"
    HALT = "HALT"
    FALLBACK = "FALLBACK"
    ESCALATE = "ESCALATE"


SAFE_ACTIONS = {ActionType.OBSERVE, ActionType.LOG, ActionType.BEACON}
REVERSIBLE_ACTIONS = SAFE_ACTIONS | {
    ActionType.REPOSITION_SENSOR,
    ActionType.ORIENT_TELESCOPE,
}


@dataclass(frozen=True)
class Telemetry:
    radiation: float
    sensor_confidence: float
    fuel_remaining: float
    power_remaining: float
    storage_remaining: float
    communication_latency: float
    instrument_health: float
    science_bay_pressure: float
    trajectory_intersects_atmosphere: bool
    reactor_temperature: float


@dataclass
class Node:
    key: str
    label: str
    salience: float = 0.5


@dataclass(frozen=True)
class Action:
    name: str
    action_type: ActionType
    utility: dict[str, float]
    cost: float = 0.0
    reversible: bool = True


@dataclass(frozen=True)
class Invariant:
    name: str
    response: InvariantResponse
    violated: Callable[[Telemetry], bool]
    description: str


@dataclass(frozen=True)
class Rejection:
    action: str
    reason: str


@dataclass(frozen=True)
class Decision:
    tick: int
    envelope: Envelope
    confidence: float
    resultant: dict[str, float]
    selected: Action
    score: float
    rejected: tuple[Rejection, ...]
    invariant_response: InvariantResponse | None
    invariant_name: str | None
    audit_record: AuditRecord


class ImperativeField:
    """Continuous field of mission imperatives and edge affinities."""

    def __init__(self, nodes: list[Node], edges: dict[tuple[str, str], float]) -> None:
        self.nodes = {node.key: node for node in nodes}
        self.edges = {self._edge_key(a, b): weight for (a, b), weight in edges.items()}

    def set_salience(self, key: str, salience: float) -> None:
        self.nodes[key].salience = clamp(salience)

    def set_edge(self, left: str, right: str, weight: float) -> None:
        self.edges[self._edge_key(left, right)] = clamp(weight, -1.0, 1.0)

    def resultant(self) -> dict[str, float]:
        raw: dict[str, float] = {}
        for key, node in self.nodes.items():
            influence = node.salience
            for other_key, other_node in self.nodes.items():
                if key == other_key:
                    continue
                influence += self.edges.get(self._edge_key(key, other_key), 0.0) * other_node.salience
            raw[key] = max(0.0, influence)
        total = sum(raw.values())
        if total == 0.0:
            return {key: 0.0 for key in self.nodes}
        return {key: value / total for key, value in raw.items()}

    def snapshot(self) -> dict[str, object]:
        return {
            "nodes": {key: node.salience for key, node in self.nodes.items()},
            "edges": {f"{a}:{b}": weight for (a, b), weight in self.edges.items()},
        }

    @staticmethod
    def _edge_key(left: str, right: str) -> tuple[str, str]:
        return tuple(sorted((left, right)))


class ContextInjector:
    """Maps telemetry into smoothed node salience and edge affinities."""

    def __init__(self, field: ImperativeField, smoothing: float = 0.35) -> None:
        if not 0.0 < smoothing <= 1.0:
            raise ValueError("smoothing must be in the range (0, 1]")
        self.field = field
        self.smoothing = smoothing

    def update(self, telemetry: Telemetry) -> float:
        confidence = compute_confidence(telemetry)
        targets = {
            "N1": max(telemetry.radiation, 1.0 - telemetry.instrument_health),
            "N2": telemetry.sensor_confidence * telemetry.storage_remaining,
            "N3": 1.0 - min(telemetry.fuel_remaining, telemetry.power_remaining),
            "N4": min(1.0, telemetry.communication_latency / 10.0),
        }
        for key, target in targets.items():
            current = self.field.nodes[key].salience
            self.field.set_salience(key, smooth(current, target, self.smoothing))

        fidelity_resource = -0.2 - 0.8 * (1.0 - telemetry.power_remaining)
        preservation_resource = 0.2 + 0.7 * max(telemetry.radiation, 1.0 - telemetry.instrument_health)
        alignment_fidelity = -0.6 * min(1.0, telemetry.communication_latency / 10.0)
        self._smooth_edge("N2", "N3", fidelity_resource)
        self._smooth_edge("N1", "N3", preservation_resource)
        self._smooth_edge("N2", "N4", alignment_fidelity)
        return confidence

    def _smooth_edge(self, left: str, right: str, target: float) -> None:
        key = ImperativeField._edge_key(left, right)
        current = self.field.edges.get(key, 0.0)
        self.field.set_edge(left, right, smooth(current, target, self.smoothing))


class InvariantBoundary:
    """Deterministic outer shell for override-immune invariant gates."""

    def __init__(self, invariants: list[Invariant]) -> None:
        self.invariants = invariants

    def evaluate(self, telemetry: Telemetry) -> Invariant | None:
        for invariant in self.invariants:
            if invariant.violated(telemetry):
                return invariant
        return None


class DecisionEngine:
    """Per-tick deterministic decision pipeline."""

    def __init__(
        self,
        field: ImperativeField,
        injector: ContextInjector,
        boundary: InvariantBoundary,
        audit: AuditLog,
    ) -> None:
        self.field = field
        self.injector = injector
        self.boundary = boundary
        self.audit = audit
        self.tick = 0

    def decide(self, telemetry: Telemetry, candidates: list[Action]) -> Decision:
        self.tick += 1
        confidence = self.injector.update(telemetry)
        envelope = envelope_for(confidence)
        resultant = self.field.resultant()
        invariant = self.boundary.evaluate(telemetry)

        rejected: list[Rejection] = []
        if invariant is not None:
            selected = invariant_action(invariant)
            score = 1.0
            rejected.extend(Rejection(action.name, f"invariant:{invariant.name}") for action in candidates)
        else:
            admissible: list[tuple[float, Action]] = []
            for action in candidates:
                reason = envelope_rejection(envelope, action)
                if reason is not None:
                    rejected.append(Rejection(action.name, reason))
                    continue
                score = score_action(action, resultant)
                admissible.append((score, action))
            if admissible:
                score, selected = max(admissible, key=lambda item: (item[0], item[1].name))
            else:
                selected = Action("Beacon safe state", ActionType.BEACON, {"N4": 1.0})
                score = score_action(selected, resultant)

        audit_payload = {
            "telemetry": telemetry.__dict__,
            "field": self.field.snapshot(),
            "resultant": resultant,
            "confidence": confidence,
            "envelope": envelope.value,
            "selected_action": selected.name,
            "selected_type": selected.action_type.value,
            "score": score,
            "rejected": [rejection.__dict__ for rejection in rejected],
            "invariant": invariant.name if invariant else None,
            "response": invariant.response.value if invariant else None,
        }
        record = self.audit.append(self.tick, audit_payload)
        return Decision(
            tick=self.tick,
            envelope=envelope,
            confidence=confidence,
            resultant=resultant,
            selected=selected,
            score=score,
            rejected=tuple(rejected),
            invariant_response=invariant.response if invariant else None,
            invariant_name=invariant.name if invariant else None,
            audit_record=record,
        )


def default_field() -> ImperativeField:
    return ImperativeField(
        nodes=[
            Node("N1", "Instrument Preservation"),
            Node("N2", "Data Fidelity"),
            Node("N3", "Resource Efficiency"),
            Node("N4", "Autonomy Alignment"),
        ],
        edges={
            ("N2", "N3"): -0.4,
            ("N1", "N3"): 0.5,
            ("N2", "N4"): -0.1,
        },
    )


def default_invariants() -> InvariantBoundary:
    return InvariantBoundary(
        [
            Invariant(
                name="Vacuum Integrity",
                response=InvariantResponse.HALT,
                violated=lambda t: t.science_bay_pressure > 0.0,
                description="HALT if science bay pressure is above vacuum.",
            ),
            Invariant(
                name="Orbital Floor",
                response=InvariantResponse.FALLBACK,
                violated=lambda t: t.trajectory_intersects_atmosphere,
                description="FALLBACK if trajectory intersects planetary atmosphere.",
            ),
            Invariant(
                name="Reactor Temperature",
                response=InvariantResponse.HALT,
                violated=lambda t: t.reactor_temperature > 0.92,
                description="HALT if reactor temperature exceeds normalized limit.",
            ),
        ]
    )


def default_candidates() -> list[Action]:
    return [
        Action("Passive observation sweep", ActionType.OBSERVE, {"N2": 0.4, "N3": 0.2}, cost=0.05),
        Action("Log and beacon health digest", ActionType.BEACON, {"N4": 0.8, "N3": 0.2}, cost=0.03),
        Action("Reposition spectrometer", ActionType.REPOSITION_SENSOR, {"N1": 0.2, "N2": 0.6}, cost=0.12),
        Action("Orient telescope with reaction wheels", ActionType.ORIENT_TELESCOPE, {"N2": 0.7, "N3": -0.1}, cost=0.2),
        Action("High resolution capture", ActionType.HIGH_RES_CAPTURE, {"N2": 1.0, "N3": -0.4}, cost=0.35),
        Action(
            "Consume stored sample for assay",
            ActionType.SAMPLE_CONSUMPTION,
            {"N2": 0.9, "N3": -0.2},
            cost=0.5,
            reversible=False,
        ),
        Action("Fire thrusters for geometry", ActionType.FIRE_THRUSTERS, {"N2": 0.8, "N3": -0.5}, cost=0.6),
    ]


def compute_confidence(telemetry: Telemetry) -> float:
    comm = 1.0 - min(1.0, telemetry.communication_latency / 10.0)
    confidence = (
        telemetry.sensor_confidence * 0.45
        + telemetry.instrument_health * 0.25
        + comm * 0.2
        + min(telemetry.fuel_remaining, telemetry.power_remaining) * 0.1
    )
    return clamp(confidence)


def envelope_for(confidence: float) -> Envelope:
    if confidence > 0.8:
        return Envelope.FULL
    if confidence > 0.4:
        return Envelope.CAUTIOUS
    return Envelope.SAFE_SUBSET


def envelope_rejection(envelope: Envelope, action: Action) -> str | None:
    if envelope == Envelope.FULL:
        return None
    if envelope == Envelope.CAUTIOUS:
        if action.action_type not in REVERSIBLE_ACTIONS or not action.reversible:
            return "envelope:cautious_requires_reversible"
        return None
    if action.action_type not in SAFE_ACTIONS:
        return "envelope:safe_subset"
    return None


def score_action(action: Action, resultant: dict[str, float]) -> float:
    score = sum(resultant.get(key, 0.0) * value for key, value in action.utility.items())
    return score - action.cost


def invariant_action(invariant: Invariant) -> Action:
    action_type = ActionType[invariant.response.value]
    return Action(f"{invariant.response.value}: {invariant.name}", action_type, {}, reversible=True)


def smooth(current: float, target: float, rate: float) -> float:
    return clamp(current + (target - current) * rate, -1.0, 1.0)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))
