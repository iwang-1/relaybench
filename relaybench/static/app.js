"use strict";
const el = id => document.getElementById(id);
const node = (tag, text, cls) => {
  const item = document.createElement(tag);
  item.textContent = text;
  if (cls) item.className = cls;
  return item;
};
const policies = {reconcile: "Reconcile on timeout", blind_retry: "Blind retry", ollama: "Local model"};
const faults = {none: "No fault", before_commit: "Timeout before commit", lost_ack: "Lost acknowledgment"};
const checks = {single_matching_receipt: "Exactly one matching receipt", inventory_conserved: "Expected inventory in every pool", agent_finished: "Agent signaled completion"};
let active, inspected, busy = false;

async function api(path, data) {
  const options = data === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)};
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) throw Error(value.error || response.statusText);
  return value;
}

function show(id, trace) {
  active = id;
  inspected = trace;
  el("comparison").textContent = "";
  const {metrics, initial, events} = trace;
  el("name").textContent = policies[trace.policy];
  el("status").textContent = metrics.passed ? "Passed" : "Failed";
  el("status").className = "pill " + (metrics.passed ? "pass" : "fail");
  el("context").textContent = faults[trace.fault] + " · Seed " + trace.seed + " · Reserve " + initial.request.units + " from " + initial.request.pool;
  for (const key of ["steps", "writes", "timeouts"]) el(key).textContent = metrics[key];
  el("events").replaceChildren(...events.map(event => {
    const detail = node("details", "");
    const summary = node("summary", "");
    const outcome = event.observation.error || (event.observation.finished ? "finished" : "ok");
    summary.append(node("small", String(event.step).padStart(2, "0")), node("span", event.action?.tool || "invalid action"),
      node("small", outcome, outcome === "timeout" ? "fail" : ""));
    detail.append(summary, node("pre", JSON.stringify(event, null, 2)));
    return detail;
  }));
  el("checks").replaceChildren(...Object.entries(metrics.checks).map(([k,v]) => node("p", (v ? "✓  " : "×  ") + checks[k], v ? "pass" : "fail")));
  el("result").textContent = "";
}

async function guarded(fn) {
  if (busy) return;
  busy = true;
  el("error").textContent = "";
  el("run").disabled = el("replay").disabled = el("compare").disabled = true;
  try { await fn(); } catch (error) { el("error").textContent = error.message; }
  finally { busy = false; el("run").disabled = false; el("replay").disabled = !active; el("compare").disabled = !active || inspected.policy === "ollama"; }
}

async function historyList(selectLatest = false) {
  const runs = await api("/api/runs");
  if (selectLatest && runs.length) show(runs[0].id, await api("/api/runs/" + runs[0].id));
  el("history").replaceChildren(...runs.map(run => {
    const button = node("button", (run.passed ? "✓ " : "× ") + policies[run.policy] + " · " + run.seed);
    button.title = faults[run.fault] + " · " + run.id;
    button.setAttribute("aria-current", String(active === run.id));
    button.onclick = () => guarded(async () => { show(run.id, await api("/api/runs/" + run.id)); await historyList(); });
    return button;
  }));
  if (!runs.length) el("history").append(node("p", "No runs yet."));
}

el("config").onsubmit = event => {
  event.preventDefault();
  guarded(async () => {
    const run = await api("/api/runs", {seed: Number(el("seed").value), policy: el("policy").value, fault: el("fault").value});
    show(run.id, run.trace);
    await historyList();
  });
};
el("compare").onclick = () => guarded(async () => {
  const policy = inspected.policy === "reconcile" ? "blind_retry" : "reconcile";
  const {trace} = await api("/api/runs", {seed: inspected.seed, fault: inspected.fault, policy});
  const count = Math.max(trace.events.length, inspected.events.length);
  let difference = "Identical tool decisions.";
  for (let i = 0; i < count; i++) {
    const left = inspected.events[i]?.action.tool || "stopped";
    const right = trace.events[i]?.action.tool || "stopped";
    if (left !== right) {
      difference = "First different decision at step " + (i + 1) + " (" + left + " / " + right + ").";
      break;
    }
  }
  el("comparison").textContent = policies[policy] + (trace.metrics.passed ? " passed" : " failed") +
    " with " + trace.metrics.writes + " committed write(s). " + difference;
  await historyList();
});
el("replay").onclick = () => guarded(async () => {
  const result = await api("/api/runs/" + active + "/replay", {});
  el("result").textContent = result.verified ? "Verified all " + result.steps + " transitions · SHA-256 " + result.checksum.slice(0,12) : "First divergence at " + result.divergence;
});
guarded(async () => {
  const config = await api("/api/config");
  if (config.model) el("policy").add(new Option("Local · " + config.model, "ollama"));
  await historyList(true);
});
