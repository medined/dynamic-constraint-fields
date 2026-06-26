# Visual Demo Server

This project includes a small local web server for the browser-based Dynamic
Constraint Fields demo. The server uses only Python's standard library and serves
the static files in `web/`.

## Requirements

- Python 3.10 or newer
- A shell opened at the repository root

No package installation is required for the web server.

## Run the Server

From the repository root:

```bash
python3 -m dcf.visual_server
```

The server prints the URL and decision-log path:

```text
Visual demo: http://127.0.0.1:8765
Decision log: /path/to/repo/logs/visual_demo.jsonl
```

Open the printed URL in a browser. By default, that is:

```text
http://127.0.0.1:8765
```

Stop the server with `Ctrl+C`.

## Default Configuration

The default server configuration is defined in `dcf/visual_server.py`:

- Host: `127.0.0.1`
- Port: `8765`
- Static assets: `web/index.html`, `web/app.js`, and `web/styles.css`
- Decision log: `logs/visual_demo.jsonl`

The server recreates `logs/visual_demo.jsonl` when the simulation resets. Each
tick appends one JSON object containing telemetry, field state, selected action,
rejections, invariant response, and audit hash information.

## Run with Custom Host, Port, or Log Path

The module entry point does not currently parse command-line arguments. To run
with custom values, call `run()` from Python:

```bash
python3 - <<'PY'
from pathlib import Path

from dcf.visual_server import run

run(
    host="127.0.0.1",
    port=9000,
    log_path=Path("logs/custom_visual_demo.jsonl"),
)
PY
```

Then open:

```text
http://127.0.0.1:9000
```

Use host `0.0.0.0` only when you intentionally want the demo reachable from
other machines on the network.

## HTTP Routes

- `GET /` serves the visual demo page.
- `GET /app.js` serves the browser application script.
- `GET /styles.css` serves demo styling.
- `GET /api/status` returns server status and the decision-log path.
- `POST /api/reset` resets the simulation and clears the decision log.
- `POST /api/tick` advances the simulation using the posted control values.

## Troubleshooting

If the server fails because the port is already in use, run it with a different
port through the custom `run()` example above.

If the browser page loads but does not update, check the terminal running the
server for errors and verify that requests to `/api/status` return JSON.
