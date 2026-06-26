"""Local visual demo server for the dynamic constraint field."""

from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any
from urllib.parse import urlparse

from dcf.audit import AuditLog
from dcf.core import (
    Action,
    ContextInjector,
    Decision,
    DecisionEngine,
    Telemetry,
    clamp,
    default_candidates,
    default_field,
    default_invariants,
)


ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = ROOT / "web"
LOG_DIR = ROOT / "logs"
DEFAULT_LOG = LOG_DIR / "visual_demo.jsonl"


class VisualSimulation:
    """Stateful simulation wrapper used by the browser demo."""

    def __init__(self, log_path: Path = DEFAULT_LOG) -> None:
        self.log_path = log_path
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> dict[str, Any]:
        with self._lock:
            field = default_field()
            self.engine = DecisionEngine(field, ContextInjector(field), default_invariants(), AuditLog())
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text("", encoding="utf-8")
            return {"ok": True, "log_path": str(self.log_path)}

    def tick(self, controls: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            telemetry = telemetry_from_controls(controls)
            candidates = candidates_from_controls(controls)
            decision = self.engine.decide(telemetry, candidates)
            payload = decision_payload(decision, telemetry, self.engine.field.snapshot(), self.log_path)
            self._append_log(payload)
            return payload

    def _append_log(self, payload: dict[str, Any]) -> None:
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def telemetry_from_controls(controls: dict[str, Any]) -> Telemetry:
    return Telemetry(
        radiation=number(controls, "radiation", 0.1),
        sensor_confidence=number(controls, "sensor_confidence", 0.9),
        fuel_remaining=number(controls, "fuel_remaining", 0.8),
        power_remaining=number(controls, "power_remaining", 0.8),
        storage_remaining=number(controls, "storage_remaining", 0.8),
        communication_latency=number(controls, "communication_latency", 1.0, 0.0, 10.0),
        instrument_health=number(controls, "instrument_health", 0.9),
        science_bay_pressure=number(controls, "science_bay_pressure", 0.0),
        trajectory_intersects_atmosphere=bool(controls.get("trajectory_intersects_atmosphere", False)),
        reactor_temperature=number(controls, "reactor_temperature", 0.3),
    )


def candidates_from_controls(controls: dict[str, Any]) -> list[Action]:
    science_bias = number(controls, "science_bias", 0.5)
    resource_caution = number(controls, "resource_caution", 0.5)
    alignment_bias = number(controls, "alignment_bias", 0.5)
    candidates: list[Action] = []
    for action in default_candidates():
        utility = dict(action.utility)
        if "N2" in utility:
            utility["N2"] *= 0.6 + science_bias * 1.2
        if "N3" in utility:
            if utility["N3"] < 0.0:
                utility["N3"] *= 0.6 + resource_caution * 1.4
            else:
                utility["N3"] *= 0.8 + resource_caution * 0.8
        if "N4" in utility:
            utility["N4"] *= 0.6 + alignment_bias * 1.2
        cost = action.cost * (0.7 + resource_caution * 0.9)
        candidates.append(
            Action(
                name=action.name,
                action_type=action.action_type,
                utility=utility,
                cost=cost,
                reversible=action.reversible,
            )
        )
    return candidates


def decision_payload(
    decision: Decision,
    telemetry: Telemetry,
    field_snapshot: dict[str, object],
    log_path: Path,
) -> dict[str, Any]:
    return {
        "tick": decision.tick,
        "telemetry": asdict(telemetry),
        "field": field_snapshot,
        "resultant": decision.resultant,
        "confidence": decision.confidence,
        "envelope": decision.envelope.value,
        "selected": {
            "name": decision.selected.name,
            "type": decision.selected.action_type.value,
            "score": decision.score,
        },
        "rejected": [asdict(rejection) for rejection in decision.rejected],
        "invariant": {
            "name": decision.invariant_name,
            "response": decision.invariant_response.value if decision.invariant_response else None,
        },
        "audit": {
            "hash": decision.audit_record.digest,
            "previous_hash": decision.audit_record.previous_hash,
            "verified": True,
        },
        "commentary": commentary_for(decision),
        "log_path": str(log_path),
    }


def commentary_for(decision: Decision) -> str:
    if decision.invariant_response:
        return (
            f"Tick {decision.tick}: {decision.invariant_name} crossed a hard boundary. "
            f"The governance shell issued {decision.invariant_response.value} and rejected all planner candidates."
        )
    rejected = len(decision.rejected)
    if decision.envelope.value == "SAFE_SUBSET":
        return (
            f"Tick {decision.tick}: confidence is {decision.confidence:.2f}, so authority contracted to SAFE_SUBSET. "
            f"The agent is limited to observation, logging, and beacon actions."
        )
    if decision.envelope.value == "CAUTIOUS":
        return (
            f"Tick {decision.tick}: confidence is {decision.confidence:.2f}; only reversible actions are admitted. "
            f"{rejected} candidate(s) were filtered before selecting {decision.selected.name}."
        )
    return (
        f"Tick {decision.tick}: confidence is {decision.confidence:.2f}; the full envelope is available. "
        f"The field bias selected {decision.selected.name}."
    )


def number(
    controls: dict[str, Any],
    key: str,
    default: float,
    low: float = 0.0,
    high: float = 1.0,
) -> float:
    try:
        return clamp(float(controls.get(key, default)), low, high)
    except (TypeError, ValueError):
        return default


class DemoHandler(BaseHTTPRequestHandler):
    simulation: VisualSimulation

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._serve_file(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
            return
        if path in {"/app.js", "/styles.css"}:
            content_type = "text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8"
            self._serve_file(STATIC_ROOT / path.removeprefix("/"), content_type)
            return
        if path == "/api/status":
            self._json({"ok": True, "log_path": str(self.simulation.log_path)})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/reset":
            self._json(self.simulation.reset())
            return
        if path == "/api/tick":
            controls = self._read_json()
            self._json(self.simulation.tick(controls))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        try:
            value = json.loads(body)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def _json(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        encoded = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run(host: str = "127.0.0.1", port: int = 8765, log_path: Path = DEFAULT_LOG) -> None:
    DemoHandler.simulation = VisualSimulation(log_path)
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"Visual demo: http://{host}:{port}")
    print(f"Decision log: {log_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped visual demo.")


if __name__ == "__main__":
    run()
