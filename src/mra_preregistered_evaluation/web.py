
"""Read-only loopback demonstration of the frozen plan and completed evidence."""
from __future__ import annotations
from pathlib import Path
import threading
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import store

PREFIX = "/api/research-preregistered-evaluation"

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Frozen public retrospective evaluation</title>
<style>
:root{color-scheme:light;--ink:#162b40;--muted:#496075;--line:#c7d4df;--accent:#164c75;--paper:#fff;--bg:#f4f7fa}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font:16px/1.55 system-ui,sans-serif;color:var(--ink)}
main{max-width:1200px;margin:auto;padding:36px 24px 72px}nav{display:flex;flex-wrap:wrap;gap:12px 24px;padding-bottom:18px;border-bottom:1px solid var(--line)}
a{color:var(--accent)}h1{font-size:clamp(1.6rem,4vw,2.35rem);line-height:1.2;margin:32px 0 14px}h2{font-size:1.3rem;margin:0 0 12px}
p{margin:12px 0}.lead{max-width:920px;color:var(--muted)}.panel{background:var(--paper);padding:24px;margin:22px 0;border:1px solid var(--line);border-radius:8px}
.badge{display:inline-block;background:#e9eef4;border:1px solid var(--line);border-radius:4px;padding:4px 12px;font-weight:650}
.status-fail{background:#faeaea;color:#8c2323}.status-pass{background:#e5f2eb;color:#245a39}.status-inconclusive,.status-not_evaluable{background:#fff2d7;color:#6e4b0b}
button{background:var(--accent);color:#fff;border:0;border-radius:4px;padding:10px 16px;font:inherit;cursor:pointer}button:disabled{opacity:.6;cursor:wait}
button:focus-visible,a:focus-visible{outline:3px solid #ee991a;outline-offset:3px}.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:770px;font-size:.95rem}
th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{background:#eef3f7}td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
dl{display:grid;grid-template-columns:minmax(180px,1fr) 3fr;gap:8px 20px}dt{font-weight:650}dd{margin:0;overflow-wrap:anywhere}
.note{color:var(--muted);font-size:.95rem}#error{color:#8c2323;font-weight:650}#replay-message{min-height:1.6em}code{font-size:.86rem;overflow-wrap:anywhere}
@media(max-width:600px){main{padding:20px 14px 48px}.panel{padding:18px}dl{display:block}dt{margin-top:14px}dd{margin-top:3px}}
</style></head><body><main>
<nav aria-label="Evidence navigation"><a href="/research-preregistered-evaluation">Frozen evaluation</a><a href="/research-source-readiness">Verified source readiness</a><a href="/">Assurance console</a><a href="http://127.0.0.1:8765/research-qualified-evaluation#run=42f8bd981ec870538d861ef0871404a7">Preserved Phase 6 results</a></nav>
<h1>Phase 7C public retrospective evaluation</h1>
<p class="lead">The separately frozen Phase 7B plan fixes the source, learner, comparisons, randomization and uncertainty before this execution. MAS supports a limited retrospective diagnostic. MOH and MSF remain mandatory unsupported domains.</p>
<div id="error" role="alert"></div>
<section class="panel" aria-labelledby="state-title"><h2 id="state-title">Execution evidence</h2>
<p><span id="overall" class="badge">Loading verified status</span></p><p id="state-detail"></p>
<dl><dt>Preregistration</dt><dd><code id="registration"></code></dd><dt>Runtime freeze</dt><dd><code id="runtime"></code></dd><dt>Completion</dt><dd><code id="completion"></code></dd></dl>
<p><button id="replay" type="button" disabled>Verify captured-byte replay</button></p><p id="replay-message" role="status" aria-live="polite"></p>
</section>
<section class="panel" aria-labelledby="comparisons-title"><h2 id="comparisons-title">All eighteen mandatory comparisons</h2>
<p class="note">Gain is comparator Brier loss minus candidate Brier loss. Positive gain favors the candidate. The guarded simultaneous bands retain the eighteen-cell allocation, including the twelve unsupported slots. Unsupported statistics remain unavailable.</p>
<div class="tablewrap"><table><thead><tr><th scope="col">Domain</th><th scope="col">Comparator</th><th scope="col">Mean gain</th><th scope="col">Guarded band</th><th scope="col">Finding</th></tr></thead><tbody id="comparisons"></tbody></table></div>
</section>
<section class="panel" aria-labelledby="scope-title"><h2 id="scope-title">What these findings establish</h2>
<p>Each MAS trial scores all forty-six final origins from September 2015 through June 2019, then the protocol averages 16,384 complete retained-plus-fresh trials. Validation is descriptive and never selects a model, tolerance or verdict. The historical outcomes were previously observed; this frame is not untouched data.</p>
<p>The bands describe randomization over this fixed historical frame under ideal independent tickets. Seeded PCG64 supplies a reproducible computational approximation. There is no population, future, real-time or person-level inference.</p>
<p>The cap-nine certificate concerns replacement of one constructed binary pair with fixed public features and other rows. Whole-matrix replacement permits the conservative product cap nine to the power 294. A raw source month can affect several overlapping pairs and the public design; no raw-month or person-level privacy claim follows.</p>
<p>Agency acceptance and a positive practical benefit threshold remain pending. Usefulness evidence and a mathematical certificate confer no release authority. The earlier Phase 6 failure and unsupported source findings remain preserved.</p>
</section>
<section class="panel" aria-labelledby="artifacts-title"><h2 id="artifacts-title">Captured evidence artifacts</h2><p class="note">Downloads return the same externally bound saved bytes. Each artifact retains its SHA-256 and byte count in the completion.</p><ul id="artifacts"><li>Artifacts become available after a verified completion.</li></ul></section>
<p><a href="/api/research-preregistered-evaluation/protocol">Inspect the frozen protocol and execution contract</a>  |  <a href="/api/research-preregistered-evaluation/status">Inspect the status evidence</a></p>
</main><script>
const $=id=>document.getElementById(id);
const comparators=['independent_rr','clean_matched_logistic','clean_persistence','clean_seasonal_naive','clean_expanding_month_rate','clean_expanding_logistic'];
const labels={independent_rr:'Independent RR',clean_matched_logistic:'Clean matched logistic',clean_persistence:'Clean persistence',clean_seasonal_naive:'Clean seasonal naive',clean_expanding_month_rate:'Clean expanding month rate',clean_expanding_logistic:'Clean expanding logistic'};
function text(id,value){$(id).textContent=value;}
function number(value){return typeof value==='number'?value.toFixed(6):'Unavailable';}
function renderRows(rows){$('comparisons').replaceChildren();for(const row of rows){const tr=document.createElement('tr');for(const value of [row.domain.toUpperCase(),labels[row.comparator],number(row.mean_gain),typeof row.lower==='number'?'['+number(row.lower)+', '+number(row.upper)+']':'Unavailable',row.verdict.replaceAll('_',' ')]){const td=document.createElement('td');td.textContent=value;tr.append(td);}$('comparisons').append(tr);}}
async function refresh(){try{const response=await fetch('/api/research-preregistered-evaluation/status');const data=await response.json();if(!response.ok)throw new Error(data.detail||'Evidence unavailable');text('registration',data.preregistration_id);text('runtime',data.runtime_sha256||'Runtime has not been frozen');text('completion',data.completion_sha256||'Execution has not completed');const summary=data.summary;const verdict=summary?summary.overall_verdict:data.execution_state;text('overall',verdict.replaceAll('_',' '));$('overall').className='badge status-'+verdict;text('state-detail',data.message);renderRows(summary?summary.comparisons:['moh','mas','msf'].flatMap(domain=>comparators.map(comparator=>({domain,comparator,mean_gain:null,lower:null,upper:null,verdict:domain==='mas'?'not_executed':'not_evaluable'}))));$('replay').disabled=!data.completed;if(data.completed){const catalogResponse=await fetch('/api/research-preregistered-evaluation/artifacts');const catalog=await catalogResponse.json();if(!catalogResponse.ok)throw new Error(catalog.detail||'Artifact catalog unavailable');$('artifacts').replaceChildren();for(const item of catalog.files){const li=document.createElement('li');const a=document.createElement('a');a.href='/api/research-preregistered-evaluation/artifacts/'+item.path.split('/').map(encodeURIComponent).join('/');a.textContent=item.path+' ('+item.bytes+' bytes)';li.append(a);$('artifacts').append(li);}}text('error','');}catch(error){text('error',error.message);text('overall','Evidence unavailable');$('replay').disabled=true;}}
$('replay').addEventListener('click',async()=>{$('replay').disabled=true;text('replay-message','Replaying the same captured inputs and checking every bound numerical artifact.');try{const response=await fetch('/api/research-preregistered-evaluation/replay',{method:'POST'});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Replay refused');text('replay-message','Full deterministic replay passed. Saved evidence is unchanged.');}catch(error){text('replay-message','Replay refused: '+error.message);}await refresh();});
refresh();
</script></body></html>
"""

def create_app(repository, runtime_path=None, runtime_sha256=None, qualification_path=None,
               qualification_sha256=None, execution_dir=None, completion_sha256=None):
    from mra_source_readiness.web import create_console_app
    root = Path(repository).resolve()
    store.verify_registration(root)
    app = create_console_app(root / ".local/demo-data", root)
    app.title = "Frozen public retrospective evaluation"
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    pins = {"runtime_path": runtime_path, "runtime_sha256": runtime_sha256,
            "qualification_path": qualification_path, "qualification_sha256": qualification_sha256,
            "execution_dir": execution_dir, "completion_sha256": completion_sha256}
    completed = execution_dir is not None
    if completed and any(value is None for value in pins.values()):
        raise store.ExecutionError("Completed demo requires all external runtime, qualification and completion pins")
    if completed:
        # A cold application never treats a local seal as independent authority.
        # Full replay must succeed before any completed numerical finding is served.
        store.open_completed(root, execution_dir, completion_sha256, runtime_path, runtime_sha256,
                             qualification_path, qualification_sha256, replay=True)
    lock = threading.Lock()

    def load(replay=False):
        if not completed:
            return None
        try:
            return store.open_completed(root, execution_dir, completion_sha256, runtime_path,
                                        runtime_sha256, qualification_path, qualification_sha256, replay=replay)
        except (store.ExecutionError, OSError, ValueError, KeyError) as exc:
            raise HTTPException(409, "Completed evidence verification refused: " + str(exc)) from exc

    @app.get("/research-preregistered-evaluation", response_class=HTMLResponse)
    def page():
        return HTMLResponse(PAGE)

    @app.get(PREFIX + "/protocol")
    def protocol():
        registration = store.verify_registration(root)
        return {"preregistration_id": store.REGISTRATION_ID,
                "scientific_specification_sha256": store.SPEC_SHA256,
                "execution_contract_sha256": store.CONTRACT_SHA256,
                "scientific_specification": store._json(store._read(registration / "scientific-preregistration.json")),
                "execution_contract": store._json(store._read(registration / "execution-contract.json")),
                "authorization_effect": "none"}

    @app.get(PREFIX + "/status")
    def status():
        value = load()
        if value is not None:
            return {"preregistration_id": store.REGISTRATION_ID, "runtime_sha256": runtime_sha256,
                    "completion_sha256": completion_sha256, "completed": True,
                    "execution_state": "completed", "summary": value["completion"]["summary"],
                    "message": "The externally pinned completion passed a full replay at application startup. Every status read verifies its captured bytes and current runtime.",
                    "authorization_effect": "none"}
        state = store.status(root, runtime_sha256)
        entries = state["executions"]
        execution_state = "reserved_incomplete" if any(item["reserved"] and not item["completed"] for item in entries) else "not_executed"
        message = "The benchmark has not executed. Mandatory MOH and MSF slots remain unsupported."
        qualification = None
        if runtime_path is not None:
            try:
                store.verify_runtime(root, runtime_path, runtime_sha256)
                if qualification_path is not None:
                    raw = store._read(Path(qualification_path))
                    if store.sha(raw) != qualification_sha256:
                        raise store.ExecutionError("Qualification differs from external pin")
                    qualification = store._json(raw)
                    try:
                        store.verify_qualification(qualification_path, qualification_sha256, runtime_sha256)
                    except store.ExecutionError:
                        execution_state = "qualification_blocked"
                        message = "Independent numerical qualification has not passed. No benchmark execution is authorized by this evidence."
            except (store.ExecutionError, OSError, ValueError) as exc:
                raise HTTPException(409, "Runtime evidence verification refused: " + str(exc)) from exc
        if execution_state == "reserved_incomplete":
            message = "An incomplete execution reservation is retained. Replacement or retry is forbidden."
        return {"preregistration_id": store.REGISTRATION_ID, "runtime_sha256": runtime_sha256,
                "completion_sha256": None, "completed": False, "execution_state": execution_state,
                "summary": None, "qualification": qualification, "message": message,
                "authorization_effect": "none", "agency_acceptance": "pending", "agency_practical_margin": None}

    def catalog():
        result = load()
        if result is None:
            raise HTTPException(409, "No completed artifact catalog exists")
        completion = result["completion"]
        files = completion["input_files"] + completion["files"] + [completion["reservation"]]
        files += [{"path": "completion.json", "sha256": completion_sha256,
                   "bytes": len(store._read(Path(execution_dir) / "completion.json"))}]
        return files

    @app.get(PREFIX + "/artifacts")
    def artifacts():
        return {"execution_id": Path(execution_dir).name if execution_dir else None,
                "completion_sha256": completion_sha256, "files": catalog(),
                "same_captured_bytes": True, "authorization_effect": "none"}

    @app.get(PREFIX + "/artifacts/{artifact_path:path}")
    def artifact(artifact_path: str):
        bindings = {item["path"]: item for item in catalog()}
        if artifact_path not in bindings:
            raise HTTPException(404, "Artifact is absent from the externally pinned completion")
        binding = bindings[artifact_path]
        try:
            data = store._verify_file(Path(execution_dir), binding)
        except (store.ExecutionError, OSError, ValueError) as exc:
            raise HTTPException(409, "Captured artifact changed") from exc
        media = "application/json" if artifact_path.endswith(".json") else "text/csv" if artifact_path.endswith(".csv") else "text/plain" if artifact_path.endswith(".txt") else "application/octet-stream"
        return Response(data, media_type=media, headers={"ETag": '"' + binding["sha256"] + '"',
                       "Content-Disposition": 'attachment; filename="' + Path(artifact_path).name + '"'})

    @app.post(PREFIX + "/replay")
    async def replay(request: Request):
        origin = request.headers.get("origin")
        expected_origin = str(request.base_url).rstrip("/")
        if origin != expected_origin or request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
            raise HTTPException(403, "Verification replay requires a same-origin request")
        if request.headers.get("content-length", "0") != "0" or await request.body() != b"":
            raise HTTPException(422, "Verification replay accepts only an empty fixed request")
        if not completed:
            raise HTTPException(409, "No completed execution exists to replay")
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "A verification replay is already running")
        try:
            result = await run_in_threadpool(load, replay=True)
            return {"execution_id": result["execution_id"], "completion_sha256": result["completion_sha256"],
                    "full_deterministic_replay": True, "same_captured_bytes": True,
                    "new_execution_reserved": False, "authorization_effect": "none"}
        finally:
            lock.release()
    return app

