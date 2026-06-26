"""Brokered multi-agent market for scarce ship resources."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentBid:
    agent: str
    resource: str
    requested_units: float
    mission_value: float
    cost: float

    @property
    def score(self) -> float:
        if self.requested_units <= 0.0:
            raise ValueError("requested_units must be positive")
        return (self.mission_value - self.cost) / self.requested_units


class BrokeredMarket:
    """Allocates resources to the highest value-per-unit admissible bids."""

    def allocate(self, capacities: dict[str, float], bids: list[AgentBid]) -> dict[str, list[AgentBid]]:
        remaining = capacities.copy()
        allocations: dict[str, list[AgentBid]] = {resource: [] for resource in capacities}
        ranked = sorted(bids, key=lambda bid: (bid.score, bid.mission_value), reverse=True)
        for bid in ranked:
            if bid.resource not in remaining:
                continue
            if bid.requested_units <= remaining[bid.resource]:
                allocations[bid.resource].append(bid)
                remaining[bid.resource] -= bid.requested_units
        return allocations
