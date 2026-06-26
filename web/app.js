const state = {
  running: false,
  timer: null,
  busy: false
};

const controls = [...document.querySelectorAll("[data-control]")];
const toggleRun = document.querySelector("#toggleRun");
const stepButton = document.querySelector("#step");
const resetButton = document.querySelector("#reset");

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
  document.querySelector("#commentary").replaceChildren();
  document.querySelector("#rejected").replaceChildren();
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

  renderNodes(payload.field.nodes);
  renderEdges(payload.field.edges);
  renderBars(payload.resultant);
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
