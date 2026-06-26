# Dynamic Constraint Fields POC

Proof-of-concept implementation of a hybrid autonomy-governance architecture for an
autonomous science vessel.

The system separates probabilistic local preferences from deterministic safety
enforcement:

- `InvariantBoundary`: override-immune boolean gates for hard red lines.
- `ImperativeField`: weighted mission objectives and relationships.
- `ContextInjector`: translates telemetry into smoothed node salience and edge weights.
- `DecisionEngine`: deterministic per-tick pipeline for candidate scoring, envelope
  contraction, invariant filtering, execution selection, and audit logging.
- `BrokeredMarket`: multi-agent bidding for constrained ship resources.
- `KnowledgeGraph`: sandbox/corroboration governance and descendant rollback for
  knowledge objects.

## Run the Demo

```bash
python3 -m dcf.demo
```

The demo prints each tick's selected action, rejected candidates, envelope state,
invariant response, and audit hash.

## Run the Visual Demo

```bash
python3 -m dcf.visual_server
```

Then open `http://127.0.0.1:8765`. The browser controls adjust telemetry and
agent behavior bias while the server writes one JSONL decision record per tick to
`logs/visual_demo.jsonl`.

## Run Tests

```bash
python3 -m unittest discover -s tests
```

## Project Layout

```text
dcf/
  audit.py       # tamper-evident audit records
  core.py        # telemetry, imperatives, actions, decision pipeline
  demo.py        # runnable proof-of-concept scenario
  knowledge.py   # knowledge object governance and rollback
  market.py      # brokered multi-agent allocation
tests/
  test_governance.py
```
