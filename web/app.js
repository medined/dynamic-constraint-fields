const state = {
  running: false,
  timer: null,
  busy: false
};

const controls = [...document.querySelectorAll("[data-control]")];
const toggleRun = document.querySelector("#toggleRun");
const stepButton = document.querySelector("#step");
const resetButton = document.querySelector("#reset");
const shellStage = document.querySelector("#shellStage");
const acceptedLane = document.querySelector("#acceptedLane");

const AGENTS = {
  OBSERVE: "science",
  HIGH_RES_CAPTURE: "science",
  SAMPLE_CONSUMPTION: "science",
  REPOSITION_SENSOR: "systems",
  ORIENT_TELESCOPE: "systems",
  BEACON: "systems",
  LOG: "systems",
  FIRE_THRUSTERS: "nav"
};

const AGENT_POINTS = {
  science: { x: 22, y: 28 },
  nav: { x: 22, y: 72 },
  systems: { x: 50, y: 50 }
};

const PORT_POINTS = [
  { x: 82, y: 25 },
  { x: 90, y: 50 },
  { x: 82, y: 75 }
];

controls.forEach((control) => {
  const output = control.parentElement.querySelector("output");
  if (output) {
    output.value = control.value;
  }
  control.addEventListener("input", () => {
    if (output) {
      output.value = Number(control.value).toFixed(control.step === "0.1" ? 1 : 2);
    }
  });
});

toggleRun.addEventListener("click", () => {
  state.running = !state.running;
  toggleRun.textContent = state.running ? "Pause" : "Start";
  toggleRun.classList.toggle("primary", state.running);
  if (state.running) {
    tick();
    state.timer = window.setInterval(tick, 1000);
  } else {
    window.clearInterval(state.timer);
  }
});

stepButton.addEventListener("click", tick);

resetButton.addEventListener("click", async () => {
  await fetch("/api/reset", { method: "POST" });
  document.querySelector("#tick").textContent = "0";
  document.querySelector("#envelope").textContent = "IDLE";
  document.querySelector("#confidence").textContent = "0.00";
  document.querySelector("#selected").textContent = "Awaiting tick";
  document.querySelector("#shellDecision").textContent = "Awaiting actions";
  document.querySelector("#shellMode").textContent = "IDLE";
  document.querySelector("#commentary").replaceChildren();
  document.querySelector("#rejected").replaceChildren();
  acceptedLane.replaceChildren();
  shellStage.querySelectorAll(".action-token").forEach((token) => token.remove());
  document.querySelector("#logStatus").textContent = "Log reset. Next tick will append a fresh JSONL entry.";
});

async function tick() {
  if (state.busy) {
    return;
  }
  state.busy = true;
  try {
    const response = await fetch("/api/tick", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readControls())
    });
    render(await response.json());
  } finally {
    state.busy = false;
  }
}

function readControls() {
  const values = {};
  controls.forEach((control) => {
    if (control.type === "checkbox") {
      values[control.dataset.control] = control.checked;
    } else {
      values[control.dataset.control] = Number(control.value);
    }
  });
  return values;
}

function render(payload) {
  document.querySelector("#tick").textContent = payload.tick;
  const envelope = document.querySelector("#envelope");
  envelope.textContent = payload.envelope;
  envelope.className = `env-${payload.envelope}`;
  document.querySelector("#confidence").textContent = payload.confidence.toFixed(2);
  document.querySelector("#selected").textContent = payload.selected.name;
  document.querySelector("#logStatus").textContent =
    `Writing JSONL decisions to:\n${payload.log_path}\nLatest audit hash: ${payload.audit.hash}`;

  renderBars(payload.resultant);
  renderShell(payload);
  renderCommentary(payload.commentary);
  renderRejected(payload.rejected);
}

function renderNodes(nodes) {
  Object.entries(nodes).forEach(([key, value]) => {
    const node = document.querySelector(`[data-node="${key}"]`);
    node.querySelector("strong").textContent = value.toFixed(2);
    const scale = 0.86 + value * 0.34;
    node.style.transform = `scale(${scale})`;
    node.style.borderColor = value > 0.6 ? "var(--accent)" : "var(--line)";
    node.style.setProperty("--pulse", `${Math.round(value * 28)}px`);
  });
}

function renderEdges(edges) {
  setEdge("edgeN1N3", edges["N1:N3"]);
  setEdge("edgeN2N3", edges["N2:N3"]);
  setEdge("edgeN2N4", edges["N2:N4"]);
}

function setEdge(id, value = 0) {
  const edge = document.querySelector(`#${id}`);
  edge.classList.toggle("positive", value >= 0.05);
  edge.classList.toggle("negative", value <= -0.05);
  edge.style.strokeWidth = String(1 + Math.abs(value) * 5);
}

function renderBars(resultant) {
  Object.entries(resultant).forEach(([key, value]) => {
    const row = document.querySelector(`[data-bar="${key}"]`);
    row.querySelector("meter").value = value;
    row.querySelector("output").value = value.toFixed(2);
  });
}

function renderCommentary(text) {
  const list = document.querySelector("#commentary");
  const item = document.createElement("li");
  item.textContent = text;
  list.prepend(item);
  while (list.children.length > 12) {
    list.lastElementChild.remove();
  }
}

function renderRejected(rejected) {
  const list = document.querySelector("#rejected");
  list.replaceChildren();
  if (rejected.length === 0) {
    const item = document.createElement("li");
    item.textContent = "No candidates rejected on this tick.";
    list.append(item);
    return;
  }
  rejected.forEach((entry) => {
    const item = document.createElement("li");
    item.textContent = `${entry.action}: ${entry.reason}`;
    list.append(item);
  });
}

function renderShell(payload) {
  const actions = payload.actions || actionsFromLegacyPayload(payload);
  const ports = document.querySelectorAll("[data-port]");
  const selected = payload.selected.name;
  const rejectedCount = actions.filter((action) => action.status === "rejected").length;

  document.querySelector("#shellDecision").textContent = selected;
  document.querySelector("#shellMode").textContent = `${payload.envelope} / ${rejectedCount} rejected`;
  ports.forEach((port) => {
    port.classList.remove("open", "blocked");
    void port.offsetWidth;
  });

  shellStage.querySelectorAll(".action-token").forEach((token) => token.remove());
  acceptedLane.replaceChildren();

  actions.forEach((action, index) => {
    const portIndex = index % PORT_POINTS.length;
    const port = document.querySelector(`[data-port="${portIndex}"]`);
    port.classList.add(action.status === "rejected" ? "blocked" : "open");
    spawnActionToken(action, index, portIndex);
    if (action.status !== "rejected") {
      addAcceptedChip(action);
    }
  });
}

function actionsFromLegacyPayload(payload) {
  const rejected = payload.rejected.map((entry) => ({
    name: entry.action,
    type: "UNKNOWN",
    status: "rejected",
    reason: entry.reason
  }));
  return [
    {
      name: payload.selected.name,
      type: payload.selected.type,
      status: "selected",
      reason: ""
    },
    ...rejected
  ];
}

function spawnActionToken(action, index, portIndex) {
  const stageRect = shellStage.getBoundingClientRect();
  const agent = AGENTS[action.type] || "systems";
  const start = pointToPixels(AGENT_POINTS[agent], stageRect);
  const port = pointToPixels(PORT_POINTS[portIndex], stageRect);
  const exit = pointToPixels({ x: 112, y: PORT_POINTS[portIndex].y }, stageRect);
  const jitter = ((index % 3) - 1) * 14;
  const token = document.createElement("div");
  const rejected = action.status === "rejected";

  token.className = `action-token ${actionShape(action.type)} ${rejected ? "rejected" : "accepted"} ${action.status}`;
  token.textContent = rejected ? rejectionLabel(action.reason) : actionLabel(action.name);
  token.title = rejected ? `${action.name}: ${action.reason}` : action.name;
  token.style.left = `${start.x}px`;
  token.style.top = `${start.y + jitter}px`;
  token.style.setProperty("--dx-port", `${port.x - start.x}px`);
  token.style.setProperty("--dy-port", `${port.y - start.y - jitter}px`);
  token.style.setProperty("--dx-exit", `${exit.x - start.x}px`);
  token.style.setProperty("--dy-exit", `${exit.y - start.y - jitter}px`);
  token.style.setProperty("--reject-dx", `${index % 2 === 0 ? -74 : 74}px`);
  token.style.animationDelay = `${index * 80}ms`;
  shellStage.append(token);
}

function pointToPixels(point, rect) {
  return {
    x: rect.width * point.x / 100,
    y: rect.height * point.y / 100
  };
}

function addAcceptedChip(action) {
  const chip = document.createElement("span");
  chip.textContent = action.status === "selected" ? `SELECTED ${actionLabel(action.name)}` : actionLabel(action.name);
  chip.className = action.status === "selected" ? "selected" : "";
  acceptedLane.append(chip);
}

function actionLabel(name) {
  return name
    .split(" ")
    .filter((word) => !["and", "for", "with"].includes(word.toLowerCase()))
    .map((word) => word[0])
    .join("")
    .slice(0, 4)
    .toUpperCase();
}

function rejectionLabel(reason) {
  if (reason.includes("safe_subset")) {
    return "SAFE";
  }
  if (reason.includes("reversible")) {
    return "REVERS";
  }
  if (reason.includes("Vacuum")) {
    return "VACUUM";
  }
  if (reason.includes("Orbital")) {
    return "ORBIT";
  }
  if (reason.includes("Reactor")) {
    return "HEAT";
  }
  return "BLOCK";
}

function actionShape(type) {
  if (type === "FIRE_THRUSTERS") {
    return "shape-diamond";
  }
  if (type === "HIGH_RES_CAPTURE" || type === "SAMPLE_CONSUMPTION") {
    return "shape-pill";
  }
  if (type === "BEACON" || type === "OBSERVE") {
    return "shape-round";
  }
  return "shape-button";
}
