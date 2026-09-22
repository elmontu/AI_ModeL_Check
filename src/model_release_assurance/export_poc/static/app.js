"use strict";
let current = null;
let plan = null;
let catalog = null;
let busy = false;
let planRequest = 0;
const el = (id) => document.getElementById(id);
async function request(path, payload) {
  const response = await fetch(path, payload === undefined ? {cache: "no-store"} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}
function note(text, error = false) { el("message").textContent = text; el("message").classList.toggle("error", error); }
function node(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; }
function controls() {
  const pending = current && current.candidates.some(c => c.status === "prepared" && !c.stale);
  el("prepare").disabled = busy || !plan || !plan.ready || plan.route === "reuse" || pending || !current || plan.history_revision !== current.revision;
  el("route").disabled = busy || !current;
  el("refresh").disabled = busy;
  document.querySelectorAll("button.mutate").forEach(button => { button.disabled = busy || button.dataset.stale === "true"; });
}
async function updatePlan() {
  const sequence = ++planRequest;
  plan = null; controls();
  el("reuse").hidden = true;
  el("plan-bound").textContent = "Checking…";
  const route = el("route").value;
  const construction = catalog && catalog.second_stage_routes.find(item => item.route === route);
  el("route-description").textContent = construction ? construction.construction : route === "reuse"
    ? "Reuse exactly the latest committed model. There is no retraining and no new random draw."
    : "Protect the first service-use observation with randomized response, then fit one forecast probability per public group.";
  try {
    const result = await request("/api/plan?route=" + encodeURIComponent(route));
    if (sequence !== planRequest) return;
    plan = result;
    el("plan-bound").textContent = plan.ready
      ? "ε " + plan.current_epsilon.toFixed(4) + " → " + plan.proposed_epsilon.toFixed(4) + " · δ = 0"
      : "Unavailable for this history";
    el("plan-description").textContent = plan.ready ? plan.privacy_cost_interpretation : plan.block_message;
    el("plan-accounting").textContent = "Required access: " + plan.required_private_access;
    if (plan.ready && plan.route === "reuse") {
      el("reuse").href = "/api/exports/" + encodeURIComponent(plan.reuse_release_id);
      el("reuse").download = "committed-model.json";
      el("reuse").hidden = false;
    }
  } catch (e) {
    if (sequence !== planRequest) return;
    el("plan-bound").textContent = "Plan unavailable";
    el("plan-description").textContent = e.message;
    el("plan-accounting").textContent = "";
    note(e.message, true);
  }
  controls();
}
async function refresh() {
  el("verification").textContent = "Check disclosure records, artifact bindings and cumulative accounting.";
  try { current = await request("/api/status"); }
  catch (e) { current = null; plan = null; controls(); throw e; }
  el("revision").textContent = current.revision;
  el("release-count").textContent = current.releases.length;
  el("epsilon").textContent = Math.log(current.history_ratio).toFixed(4);
  el("ratio").textContent = "Likelihood ratio ≤ " + current.history_ratio + "×";
  el("phase").textContent = current.releases.length === 2 ? "Two-stage limit reached" : current.releases.length === 1 ? "First disclosure retained" : "No committed disclosures";
  el("state").textContent = JSON.stringify(current, null, 2);
  el("candidates").replaceChildren();
  el("releases").replaceChildren();
  for (const candidate of current.candidates.filter(c => c.status === "prepared")) {
    const item = node("div", undefined, "item");
    item.append(node("strong", "Prepared stage " + candidate.stage + " · " + candidate.route));
    item.append(node("div", "Request " + candidate.request_id + " · revision " + candidate.base_revision + (candidate.stale ? " · stale, cannot commit" : " · candidate stays internal"), "meta"));
    const button = node("button", "Commit exact model", "mutate");
    button.dataset.stale = String(candidate.stale);
    button.addEventListener("click", () => run(async () => {
      await request("/api/commit", {request_id: candidate.request_id, expected_revision: candidate.base_revision});
      note("Exact model and privacy history committed. Delivery now checks this recorded artifact.");
    }));
    item.append(button); el("candidates").append(item);
  }
  for (const release of current.releases) {
    const item = node("div", undefined, "item");
    item.append(node("strong", "Stage " + release.stage + " · " + release.route + (release.revoked ? " · distribution stopped" : " · committed")));
    item.append(node("div", "Cumulative ε ≤ " + Math.log(release.history_ratio).toFixed(4) + ", δ = 0 · revision " + release.revision + " · SHA-256 " + release.artifact_sha256, "meta"));
    if (release.parent_artifact_sha256) item.append(node("div", "Retained parent: " + release.parent_artifact_sha256, "meta"));
    const actions = node("div", undefined, "actions");
    if (!release.revoked) {
      const download = node("a", "Download committed model");
      download.href = "/api/exports/" + encodeURIComponent(release.release_id);
      download.download = "stage-" + release.stage + "-model.json";
      actions.append(download);
      const evaluate = node("button", "Evaluate public holdout", "secondary");
      const result = node("div", "", "evaluation");
      evaluate.addEventListener("click", async () => {
        evaluate.disabled = true;
        try {
          const data = await request("/api/exports/" + encodeURIComponent(release.release_id) + "/evaluation");
          result.textContent = "Brier score: " + data.brier_score.toFixed(4) + " · Mean group count error: " + data.group_count_mae.toFixed(2) + "\n" + data.citizens + " public held-out synthetic records. Descriptive utility, not a release approval.";
        } catch (e) { note(e.message, true); }
        finally { evaluate.disabled = false; }
      });
      actions.append(evaluate);
      const revoke = node("button", "Stop future downloads", "secondary mutate");
      revoke.addEventListener("click", () => run(async () => {
        await request("/api/revoke", {release_id: release.release_id});
        note("Future download admission stopped. Existing copies and cumulative privacy cost remain.");
      }));
      actions.append(revoke); item.append(actions, result);
    } else {
      item.append(node("p", "Existing copies remain disclosed. This release still counts in the complete history."));
    }
    el("releases").append(item);
  }
  if (!current.candidates.length) el("candidates").append(node("p", "No candidate yet. Inspect the first-release plan and prepare a model."));
  if (current.releases.length === 0) el("route").value = "first";
  else if (current.releases.length === 2) el("route").value = "reuse";
  else if (el("route").value === "first") el("route").value = "central-count";
  await updatePlan();
  controls();
}
async function run(action) {
  if (busy) return;
  busy = true; controls();
  try { await action(); } catch (e) { note(e.message, true); }
  finally {
    try { await refresh(); } catch (e) { note(e.message, true); }
    busy = false; controls();
  }
}
el("prepare").addEventListener("click", () => run(async () => {
  if (!plan || !plan.ready || plan.route === "reuse" || plan.history_revision !== current.revision) throw new Error("Refresh the current plan before preparing.");
  await request("/api/prepare", {request_id: crypto.randomUUID(), stage: plan.stage, route: plan.route, expected_revision: plan.history_revision});
  note("Candidate prepared internally. Commit it against the same history to enable delivery.");
}));
el("route").addEventListener("change", updatePlan);
el("refresh").addEventListener("click", () => run(async () => note("History refreshed.")));
el("verify").addEventListener("click", async () => {
  el("verify").disabled = true;
  try {
    const data = await request("/api/history/verify");
    el("verification").textContent = "Consistent at revision " + data.revision + ": " + data.committed_count + " committed releases, " + data.revoked_count + " revoked, history ratio " + data.history_ratio + "×. Public history SHA-256: " + data.public_history_sha256;
  } catch (e) {
    el("verification").textContent = "History check failed: " + e.message;
    note(e.message, true);
  } finally { el("verify").disabled = false; }
});
request("/api/capabilities").then(data => {
  catalog = data;
  el("catalog").textContent = JSON.stringify(data, null, 2);
  return refresh();
}).then(() => note("Ready. The same disclosure history is retained across restarts."))
  .catch(e => { note(e.message, true); el("catalog").textContent = "Unavailable: " + e.message; controls(); });
