"use strict";

const API = "/api/temporal";
const state = {study: null, operator: null, scenario: null, step: 1, interface: "full", raw: false, request: null, busy: false, reviewDrafts: {}};
const $ = (id) => document.getElementById(id);
const N = (value) => Number.isFinite(Number(value)) ? Number(value).toLocaleString("en-US") : "—";
const E = (value) => value === null || value === undefined ? "—" : Number(value).toLocaleString("en-US", {maximumFractionDigits: 3});
const P = (value) => Number.isFinite(value) ? `${(100 * value).toFixed(2)}%` : "—";
const families = {slm_small: "Small SLM", slm_medium: "Medium SLM", decision_tree: "Decision tree", random_forest: "Random forest", extra_trees: "Extra trees", hist_gradient_boosting: "Histogram boosting", xgboost: "XGBoost", knn: "K-nearest neighbours", logistic_regression: "Logistic regression", mlp: "Multilayer perceptron"};
const colors = {teal: "#197b79", mint: "#75a894", purple: "#8b78a3", orange: "#bd7952", grid: "#e4ebe4", text: "#7c9096"};

function el(tag, text, className) {const node = document.createElement(tag); if (text !== undefined && text !== null) node.textContent = String(text); if (className) node.className = className; return node;}
function badge(text, tone = "neutral") {return el("span", text, `badge ${tone}`);}
function message(id, text, tone = "") {const node = $(id); node.textContent = text || ""; node.className = `notice ${tone}${text ? "" : " hidden"}`;}
function clear(node) {node.replaceChildren();}
function detail(label, value, subtitle, large = false) {const wrapper = el("div"); wrapper.append(el("span", label, "detail-label"), el("div", value, `detail-value${large ? " large" : ""}`)); if (subtitle) wrapper.append(el("div", subtitle, "detail-sub")); return wrapper;}
function metric(label, value, note, tone = "") {const node = el("div", null, `metric ${tone}`); node.append(el("span", label, "metric-label"), el("div", value, "metric-value"), el("div", note, "metric-note")); return node;}
function ba(row, view = "attack", iface = state.interface, group = "eval_member") {const attack = view === "query_only" ? row[view] : row[view]?.[iface]; return attack?.groups?.[group]?.metrics?.balanced_accuracy;}
function scenarioName(id) {const fixed = /^epsilon-([\d.]+)-seed-(\d+)-(cached|fresh)$/.exec(id || ""); if (fixed) return `${fixed[3] === "cached" ? "Cached input" : "Independent score noise"} · ε ${fixed[1]} · seed ${fixed[2]}`; const renewed = /^renewed-history-cap-(\d+)$/.exec(id || ""); return renewed ? `Renewed caches · cumulative cap ε ${renewed[1]}` : id;}

async function api(path, payload, rawPayload) {const options = {headers: {Accept: "application/json"}, cache: "no-store"}; if (payload !== undefined) {options.method = "POST"; options.headers["Content-Type"] = "application/json"; options.body = rawPayload ?? JSON.stringify(payload);} const response = await fetch(`${API}${path}`, options); let data; try {data = await response.json();} catch {throw new Error(`The local service returned an unreadable response (${response.status}).`);} if (!response.ok) {const error = new Error(data.detail || data.message || "The release service rejected this action."); error.code = data.code || `HTTP ${response.status}`; throw error;} return data;}
function errorText(error) {const prefix = error.code ? `${error.code.replaceAll("_", " ")}: ` : ""; const retry = error.code === "revision_conflict" ? " Refresh the ledger and prepare a new request before committing." : ""; return prefix + error.message + retry;}

function svgEl(tag, attrs = {}, text) {const node = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value)); if (text !== undefined) node.textContent = text; return node;}
function chart(target, rows, series, range, ticks, title, cap) {
  const width = 560, height = 230, left = 44, top = 13, bottom = 33, right = 15, plotWidth = width-left-right, plotHeight = height-top-bottom;
  const svg = svgEl("svg", {viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": title}); svg.append(svgEl("title", {}, title));
  const maxStep = Math.max(...rows.map((row) => row.step), 1), x = (value) => left + (value-1) / Math.max(1, maxStep-1) * plotWidth, y = (value) => top + (range[1]-value)/(range[1]-range[0])*plotHeight;
  const denied = rows.filter((row) => row.decision === "blocked"); if (denied.length) {const from = Math.max(left, x(denied[0].step)-plotWidth/Math.max(1,maxStep-1)/2); svg.append(svgEl("rect", {x: from, y: top, width: width-right-from, height: plotHeight, fill: "#f9ebe4"}));}
  for (const tick of ticks) {svg.append(svgEl("line", {x1: left, y1: y(tick), x2: width-right, y2: y(tick), stroke: colors.grid, "stroke-width": 1})); svg.append(svgEl("text", {x: left-9, y: y(tick)+4, "text-anchor": "end", fill: colors.text, "font-size": 10}, E(tick)));}
  for (const row of rows) svg.append(svgEl("text", {x: x(row.step), y: height-10, "text-anchor": "middle", fill: colors.text, "font-size": 10}, String(row.step)));
  if (cap !== undefined) {svg.append(svgEl("line", {x1:left,y1:y(cap),x2:width-right,y2:y(cap),stroke:"#c89c62","stroke-width":1.2,"stroke-dasharray":"4 4"})); svg.append(svgEl("text", {x:width-right-3,y:y(cap)-5,"text-anchor":"end",fill:"#b5864d","font-size":10}, `cap ε ${E(cap)}`));}
  svg.append(svgEl("line", {x1:x(state.step),y1:top,x2:x(state.step),y2:height-bottom,stroke:"#c3d4c6","stroke-dasharray":"3 4"}));
  for (const item of series) {let path = "", started = false; rows.forEach((row) => {const value = item.get(row); if (!Number.isFinite(value)) {started = false; return;} path += started && item.step ? ` H${x(row.step)} V${y(value)}` : `${started ? " L" : "M"}${x(row.step)} ${y(value)}`; started = true;}); const line = svgEl("path", {d:path,fill:"none",stroke:item.color,"stroke-width":item.width || 2.3,"stroke-linejoin":"round","stroke-linecap":"round"}); if (item.dash) line.setAttribute("stroke-dasharray", item.dash); svg.append(line); const current = rows.find((row) => row.step === state.step), value = current && item.get(current); if (Number.isFinite(value)) svg.append(svgEl("circle", {cx:x(state.step),cy:y(value),r:3.5,fill:item.color,stroke:"#fffefa","stroke-width":1.5}));}
  target.replaceChildren(svg);
}

function renderStudy() {
  const study = state.study; if (!study) return; const summary = study.summary || {};
  $("study-status").textContent = study.status === "verified" ? "✓ Verified experimental replay" : "Evidence unavailable"; $("study-status").className = `badge ${study.status === "verified" ? "success" : "warning"}`;
  $("study-metrics").replaceChildren(metric("Release attempts", N(summary.attempts), "Ten ordered recipient histories"), metric("Admitted releases", N(summary.admitted), "Committed within the declared budget", "accent"), metric("Budget denials", N(summary.blocked), "Earlier disclosures remain available", "warning"), metric("Distinct model artifacts", N(summary.distinct_source_models), "Reused from 160 prior fits · no new training"));
  const scenarios = study.scenarios || []; const select = $("scenario-select"); clear(select); for (const scenario of scenarios) {const option = el("option", scenarioName(scenario.id)); option.value = scenario.id; select.append(option);} if (!scenarios.some((row) => row.id === state.scenario)) state.scenario = scenarios[0]?.id || null; select.value = state.scenario || ""; select.disabled = !scenarios.length;
  renderTimeline(); renderEvidence();
}

function renderTimeline() {
  const rows = (state.study?.prefixes || []).filter((row) => row.scenario === state.scenario).sort((a,b) => a.step-b.step); if (!rows.length) return;
  const maxStep = Math.max(...rows.map((row) => row.step)); state.step = Math.min(Math.max(1,state.step),maxStep); const current = rows.find((row) => row.step === state.step) || rows[0];
  $("step-range").disabled = false; $("step-range").max = maxStep; $("step-range").value = state.step; $("step-position").textContent = `Step ${state.step} of ${maxStep}`;
  const cap = current.ledger.budget_epsilon, max = Math.max(cap, ...rows.map((row) => row.ledger.maximum_spent_epsilon)); $("budget-label").textContent = `ε ${E(current.ledger.maximum_spent_epsilon)} of ${E(cap)}`;
  const tickSize = Math.max(1, Math.ceil(max/5)); const ticks = []; for (let value=0; value<=max; value+=tickSize) ticks.push(value);
  chart($("budget-chart"),rows,[{get:(row)=>row.ledger.maximum_spent_epsilon,color:colors.teal,step:true}],[0,Math.max(1,max)*1.15],ticks,"Maximum cumulative epsilon by release step",cap);
  const series = [{label:"Full score · members",get:(row)=>100*ba(row),color:colors.teal,key:"teal"},{label:"Full score · nonmembers",get:(row)=>100*ba(row,"attack",state.interface,"eval_nonmember"),color:colors.mint,key:"mint"},{label:"Query only · members",get:(row)=>100*ba(row,"query_only"),color:colors.purple,key:"purple",dash:"5 4"}];
  const viewLabel = state.interface === "full" ? "Full score" : state.interface === "round2" ? "Rounded score" : "Class label"; series[0].label = `${viewLabel} · members`; series[1].label = `${viewLabel} · nonmembers`;
  if (state.raw) series.push({label:"Raw input · evaluator control",get:(row)=>100*ba(row,"raw_bypass_control"),color:colors.orange,key:"orange",dash:"2 4"});
  chart($("attack-chart"),rows,series,[45,103],[50,60,70,80,90,100],"Held-out true-disability balanced accuracy across accepted model disclosures");
  clear($("attack-legend")); for (const item of series) {const node=el("span",null,"legend-item");node.append(el("span",null,`legend-swatch ink-${item.key}`),el("span",item.label));$("attack-legend").append(node);}
  $("view-context").textContent = state.interface === "full" ? "Actual recipient packages contain full-precision linked scores in addition to the models. Query-only results exclude those scores." : "Restricted-view counterfactual: the actual packages contain full-precision scores, so their recipients can use the stronger full-score view.";
  const model=detail(`Step ${current.step} · ${current.dataset}`,families[current.family] || current.family,current.arm,true); const decision = detail("Release decision",current.decision === "blocked" ? "Blocked" : "Committed",current.decision === "blocked" ? "Budget exceeded · no new package" : "Artifact delivered within budget");
  $("step-detail").replaceChildren(model,decision,detail("Cumulative ε",E(current.ledger.maximum_spent_epsilon),`Cap ε ${E(current.ledger.budget_epsilon)}`),detail("Member inference BA",P(ba(current)),`Income AUC ${current.utility?.roc_auc?.toFixed(3) || "—"}${current.decision === "blocked" ? " · not delivered" : ""}`));
  clear($("timeline-body")); for (const row of rows) {const tr=el("tr",null,row.step===state.step?"selected":"");const step=el("td"),button=el("button",String(row.step),"step-button");button.type="button";button.setAttribute("aria-label",`Inspect step ${row.step}, ${families[row.family] || row.family}`);button.addEventListener("click",()=>{state.step=row.step;renderTimeline();});step.append(button);const modelCell=el("td");modelCell.append(el("strong",families[row.family] || row.family));const status=el("td");status.append(badge(row.decision==="blocked"?"Blocked":"Committed",row.decision==="blocked"?"blocked":"success"));tr.append(step,modelCell,el("td",row.dataset),status,el("td",E(row.ledger.maximum_spent_epsilon)),el("td",P(ba(row))));$("timeline-body").append(tr);}
}

function renderEvidence() {const links=state.study?.links || {};clear($("evidence-links"));const labels={report_html:"Full study report",report_pdf:"Report PDF",report_markdown:"Report source",summary:"Study summary",theory:"Theory & assumptions",verification:"Independent verification",budget_plot:"Budget figure",attack_plot:"Inference figure",inference_pdf:"Inference figure · PDF",budget_pdf:"Privacy budget figure · PDF",inference_svg:"Inference figure · SVG",budget_svg:"Privacy budget figure · SVG",scenario_csv:"Timeline summaries · CSV",prefix_csv:"Every release prefix · CSV",attack_csv:"Attack results · CSV",utility_csv:"Prediction utility · CSV"};for(const [key,value] of Object.entries(links)){if(typeof value!=="string")continue;let url;try{url=new URL(value,location.href);}catch{continue;}if(url.origin!==location.origin || !["http:","https:"].includes(url.protocol))continue;const link=el("a",null,"evidence-link");link.href=url.pathname+url.search+url.hash;link.target="_blank";link.rel="noopener";link.append(el("span",labels[key] || key.replaceAll("_"," ")),el("span","↗"));$("evidence-links").append(link);}if(!$("evidence-links").children.length)$("evidence-links").append(el("p","Evidence links are not available from the local service.","muted"));clear($("registered-limitations"));for(const item of state.study?.limitations || [])$("registered-limitations").append(el("li",item));}

function workflowReady(){const flow=state.operator?.workflow;return state.operator?.status==="available" && flow?.version==="temporal-pipeline-v1" && flow.server_enforced===true && ["prepare","checks","review","commit","download"].every(stage=>flow.required_stages?.includes(stage));}
function canAct(action){
  if(state.busy || !workflowReady())return false;
  if(action==="prepare")return state.operator.models?.find((model)=>model.model_id===$("model-select").value)?.validity?.valid===true;
  const request=state.request, flag=action==="checks"?"check":action;
  if(action==="red-team")return request?.pipeline?.can_attach_red_team===true;
  if(!request || request[`can_${flag}`]!==true)return false;
  if(action==="revoke")return true;
  if(request.validity?.valid!==true)return false;
  if(action==="commit" && request.pipeline?.state!=="reviewed")return false;
  if(action==="review"){
    const rationale=$("review-rationale")?.value.trim() || "";
    return Boolean(request.pipeline?.check_digest) && rationale.length>=20 && rationale.length<=2000 && $("scope-ack")?.checked===true;
  }
  return true;
}
function selectedModel(){return state.operator?.models?.find((model)=>model.model_id===$("model-select").value);}
function workflowState(request){return request?.pipeline?.state || request?.state || "not prepared";}
function renderProvenance(){
  const node=$("model-provenance"),model=selectedModel();clear(node);
  if(!model){node.append(el("p","Select a model from the registered inventory.","small muted"));return;}
  const provenance=model.provenance || {};
  const heading=el("div",null,"provenance-heading");heading.append(el("strong","Registered data and DP channel"),badge(model.validity?.valid===true?"Currently valid":"Unavailable",model.validity?.valid===true?"success":"warning"));node.append(heading);
  const grid=el("div",null,"provenance-grid");
  grid.append(detail("Training dataset",model.dataset || "—"),detail("Attribute version",provenance.attribute_version || "Not supplied"),detail("Training records",N(provenance.training_units)),detail("Served records",N(provenance.serving_units)),detail("Training channel ε",E(provenance.training_epsilon)),detail("Score input",provenance.scoring || "Not supplied"));node.append(grid);
  node.append(el("p","Existing training artifact · this workflow does not retrain it.","small muted"));
  const details=el("details"),title=el("summary","Inspect registered bindings");details.append(title,digestBlock("Training cache",provenance.training_cache_id),digestBlock("Serving cache",provenance.serving_cache_id),digestBlock("Dataset version / digest",provenance.dataset_digest),digestBlock("Model artifact",provenance.artifact_digest),digestBlock("Evidence",provenance.evidence_digests));node.append(details);
  if(model.validity?.valid!==true)node.append(el("p",(model.validity?.reasons || ["Current provenance is unverified"]).map(value=>String(value).replaceAll("_"," ")).join("; "),"notice"));
}
function renderPipeline(){
  const request=state.request,model=selectedModel(),server=request?.pipeline?.stages || [],map=new Map(server.map(stage=>[stage.id,stage]));
  const provenanceStatus=request?(request.validity?.valid===true?"complete":"blocked"):(model?.validity?.valid===true?"complete":"pending");
  const stages=[{id:"provenance",label:"Registered data & DP channel",status:provenanceStatus,detail:request?"Model, data and DP channel bound to this request.":model?.validity?.valid===true?"Existing model, data roster and DP channel are registered. Request checks are still pending.":"Select an existing model with registered data and channel provenance."},
    ...[{id:"prepare",label:"Prepare bound request",detail:"Bind the model, evidence and ledger revision."},{id:"checks",label:"Run automated checks",detail:"Check provenance, validity, package binding and budget."},{id:"review",label:"Record operator review",detail:"Give a rationale and acknowledge the exact scope."},{id:"commit",label:"Commit privacy budget",detail:"Persist charges before authorizing delivery."},{id:"download",label:"Controlled delivery",detail:"Retrieve only the currently authorized package."}].map(stage=>({...stage,status:"pending",...map.get(stage.id)}))];
  clear($("pipeline-stages"));stages.forEach((stage,index)=>{const item=el("li",null,`pipeline-stage stage-${["complete","ready","blocked","pending"].includes(stage.status)?stage.status:"pending"}`);item.append(el("span",String(index+1).padStart(2,"0"),"stage-number"),el("strong",stage.label),el("span",stage.status==="complete"?"Complete":stage.status==="ready"?"Ready":stage.status==="blocked"?"Blocked":"Pending","stage-status"),el("p",stage.detail || ""));$("pipeline-stages").append(item);});
  $("pipeline-status").textContent=!workflowReady()&&state.operator?"Read-only · workflow unavailable":request?workflowState(request).replaceAll("_"," "):model?"Ready to prepare":"Select a model";
  $("pipeline-status").className=`badge ${["blocked","stale","revoked"].includes(workflowState(request))?"warning":request?.pipeline?.state==="committed"?"success":"neutral"}`;
}
function renderAudit(){
  const node=$("request-audit");clear(node);const events=state.request?.pipeline?.events || [];
  if(!events.length){node.append(el("p",state.request?"No workflow events are available for this request yet.":"Select a request to inspect its recorded checks, review and release events.","small muted"));return;}
  const list=el("ol",null,"audit-list");for(const event of events){const item=el("li"),headline=el("div",null,"audit-headline");headline.append(el("strong",String(event.action || "event").replaceAll("_"," ")),el("span",event.at?new Date(event.at*1000).toLocaleString():"Time unavailable","small muted"));item.append(el("span",N(event.sequence),"audit-sequence"),headline);if(event.detail){const details=el("details");details.append(el("summary","Event details"),el("pre",typeof event.detail==="string"?event.detail:JSON.stringify(event.detail,null,2)));item.append(details);}list.append(item);}node.append(list,el("p","Delivery authorization records access through the broker; it does not prove that a recipient saved the file.","small muted"));
}

function setBusy(value){state.busy=value;document.querySelectorAll("[data-mutation]").forEach((button)=>{button.disabled=!canAct(button.dataset.action);});document.querySelectorAll(".request-select").forEach(button=>{button.disabled=value;});$("refresh-operator").disabled=value;$("model-select").disabled=value || !state.operator?.models?.length;$("request-id").disabled=value;if($("review-rationale"))$("review-rationale").disabled=value;if($("scope-ack"))$("scope-ack").disabled=value;}
function nextRequestId(){const used=new Set((state.operator?.requests || []).map((request)=>request.request_id));let index=1;while(used.has(`release-${String(index).padStart(3,"0")}`))index++;return `release-${String(index).padStart(3,"0")}`;}
async function loadOperator(){try{state.operator=await api("/operator");if(state.request)state.request=state.operator.status==="available"?(state.operator.requests || []).find((request)=>request.request_id===state.request.request_id) || null:null;renderOperator();return workflowReady();}catch(error){state.operator=null;state.request=null;message("operator-message",errorText(error));renderOperator();return false;}}
function renderOperator(){const operator=state.operator,available=operator?.status==="available",summary=operator?.summary || {};$("operator-metrics").replaceChildren(metric("Committed releases",N(summary.committed_releases),`Ledger revision ${N(summary.revision)}`),metric("Maximum cumulative ε",E(summary.maximum_spent_epsilon),`${N(summary.charged_units)} protected records charged`,"accent"),metric("Per-record budget cap",E(summary.budget_epsilon),"Spending persists after revocation"));
  const select=$("model-select"),previous=select.value;clear(select);for(const model of operator?.models || []){const option=el("option",`${String(model.step || "").padStart(2,"0")} · ${families[model.family] || model.family || model.model_id} · ${model.dataset || ""}${model.validity?.valid!==true?" · unavailable":""}`);option.value=model.model_id;select.append(option);}if([...select.options].some((option)=>option.value===previous))select.value=previous;if(!select.options.length)select.append(el("option","No registered models available"));select.disabled=!available || !operator?.models?.length || state.busy;$("prepare-button").disabled=!canAct("prepare"); if(!$("request-id").value)$("request-id").value=nextRequestId();
  if(operator && !available)message("operator-message",operator.detail || operator.message || "The live workflow is not available. The verified research replay remains accessible.");else if(available&&!workflowReady())message("operator-message","The server has not reported the required enforced workflow version. Release actions are disabled; start the current pipeline service before proceeding.");
  clear($("operator-validity"));if(operator?.validity){const details=el("details"),summaryNode=el("summary","Current authorization and evidence status");details.append(summaryNode,el("pre",JSON.stringify(operator.validity,null,2)));$("operator-validity").append(details);}
  clear($("requests-body"));const requests=operator?.requests || [];$("requests-empty").classList.toggle("hidden",requests.length>0);for(const request of requests){const tr=el("tr"),status=el("td");status.append(badge(workflowState(request).replaceAll("_"," "),workflowState(request)==="committed"?"success":["revoked","blocked","stale"].includes(workflowState(request))?"warning":"neutral"));const action=el("td"),button=el("button","Inspect workflow","button secondary small request-select");button.type="button";button.disabled=state.busy;button.addEventListener("click",()=>{state.request=request;$("model-select").value=request.model_id;renderProvenance();renderRequest();$("request-review").scrollIntoView({behavior:"auto",block:"center"});});action.append(button);tr.append(el("td",request.request_id),el("td",request.model_id),status,el("td",N(request.revision ?? request.expected_revision)),action);$("requests-body").append(tr);}renderProvenance();renderRequest();}
function digestBlock(label,value){
  const node=el("div",null,"review-digest"),text=Array.isArray(value)?value.join("\n"):value || "Not supplied";node.append(el("strong",label));
  if(String(text).length>48){const details=el("details"),summary=el("summary",`${String(text).slice(0,18)}…${String(text).slice(-12)} · show full`);details.append(summary,el("code",text));node.append(details);}else node.append(el("span",text));return node;
}

function renderRedTeam(review,request){
  const screening=request.pipeline?.red_team;
  if(!screening)return;
  const box=el("section",null,"check-receipt");
  box.append(el("h3","Red-team screening"));
  box.append(badge(screening.mode==="legacy_unassessed"?"Legacy demonstration · unassessed":screening.satisfied?"Required screening passed":"Screening incomplete",screening.satisfied?"success":"warning"));
  box.append(el("p","This records the declared tests and controls for these exact model bytes. Passing these tests does not establish a privacy guarantee or agency approval.","small muted"));
  if(screening.reasons?.length){const reasons=el("ul");for(const reason of screening.reasons)reasons.append(el("li",String(reason).replaceAll("_"," ")));box.append(reasons);}
  for(const tool of screening.tools || []){
    const name=tool.tool_id==="native.membership_loss"?"Membership inference by prediction loss":tool.tool_id;
    const item=el("details");item.append(el("summary",`${name} · ${tool.status.replaceAll("_"," ")}`));
    for(const [metric,value] of Object.entries(tool.metrics || {}))item.append(el("p",`${metric.replaceAll("_"," ")}: ${E(value)}`,"small"));
    item.append(el("p",`Positive control AUC: ${E(tool.positive_control_auc)} · null control AUC: ${E(tool.null_control_auc)}`,"small"));
    item.append(el("p",`Audit records: ${N(tool.member_records)} members, ${N(tool.nonmember_records)} nonmembers`,"small muted"));
    box.append(item);
  }
  if(screening.policy_sha256)box.append(digestBlock("Test plan identity",screening.policy_sha256));
  if(screening.report_sha256)box.append(digestBlock("Attached report identity",screening.report_sha256));
  if(screening.required && request.pipeline?.can_attach_red_team){
    const form=el("form"),label=el("label","Attach a red-team report","field"),input=el("input");
    input.type="file";input.accept=".json,application/json";input.required=true;input.disabled=state.busy;label.append(input);
    const submit=el("button","Attach report","button secondary");submit.type="submit";submit.dataset.mutation="";submit.dataset.action="red-team";submit.disabled=!canAct("red-team");
    form.append(label,el("p","Choose the report JSON produced for the registered test plan. A changed report requires fresh checks and review.","small muted"),submit);
    form.addEventListener("submit",async event=>{
      event.preventDefault();if(!canAct("red-team")||!form.reportValidity())return;
      const file=input.files?.[0];if(!file)return;
      if(file.size>2*1024*1024-200){message("operator-message","Choose a red-team report smaller than 2 MB.");return;}
      try{const content=await file.text();JSON.parse(content);const payload={request_id:request.request_id};await mutate("red-team",payload,`{"request_id":${JSON.stringify(request.request_id)},"report":${content}}`);}
      catch{message("operator-message","The selected report could not be read as JSON.");}
    });
    box.append(form);
  }
  review.append(box);
}

function renderRequest(){
  renderPipeline();renderAudit();
  const request=state.request,review=$("request-review"),actions=$("request-actions");clear(actions);
  if(!request){
    $("request-status").textContent="No current request";$("request-status").className="badge neutral";review.className="empty-state";
    review.replaceChildren(el("span","↗","empty-icon"),el("h3",state.operator?.status==="available"?"Prepare a request to begin":"Current workflow unavailable"),el("p",state.operator?.status==="available"?"Run automated checks and record an operator review before committing or downloading.":"Refresh the workflow to verify its current state before taking an action."));actions.classList.add("hidden");return;
  }
  clear(review);review.className="";
  const valid=request.validity?.valid===true,pipeline=request.pipeline || {},phase=workflowState(request),preview=request.budget_preview || {};
  $("request-status").textContent=phase.replaceAll("_"," ")+(!valid&&phase!=="revoked"?" · unavailable":"");
  $("request-status").className=`badge ${["revoked","blocked","stale"].includes(phase)?"warning":!valid?"warning":phase==="committed"?"success":"neutral"}`;
  review.append(el("h3",request.request_id),el("p",request.model_id,"small muted"));
  const grid=el("div",null,"review-grid");grid.append(detail("Bound ledger revision",N(request.expected_revision)),detail("Score input",request.scoring || "—"),detail("Covered records",N(request.covered_units)),detail("New privacy charges",N(preview.new_unit_charges ?? request.new_unit_charges)),detail("Maximum ε after release",E(preview.maximum_spent_epsilon_after)),detail("Minimum remaining ε",E(preview.minimum_remaining_epsilon_after)));review.append(grid);
  const bindings=el("details",null,"binding-details");bindings.append(el("summary","Inspect artifact, evidence and charge bindings"),digestBlock("Bound model artifact",request.artifact_digest),digestBlock("Bound evidence",request.evidence_digests));for(const footprint of request.cache_footprints || [])bindings.append(el("p",`${footprint.cache_id} · ε ${E(footprint.epsilon_micros/1e6)} · ${N(footprint.units)} records`,"review-digest"));review.append(bindings);
  renderRedTeam(review,request);
  if(pipeline.check_digest){const checks=el("div",null,"check-receipt");checks.append(el("strong","Automated check receipt"),digestBlock("Bound check digest",pipeline.check_digest));if(pipeline.checked_at)checks.append(el("span",new Date(pipeline.checked_at*1000).toLocaleString(),"small muted"));review.append(checks);}
  const stale=request.state==="prepared"&&Number(request.expected_revision)!==Number(state.operator?.summary?.revision);
  if(!valid&&phase!=="revoked")review.append(el("p",`Current authorization is unavailable: ${(request.validity?.reasons || ["status unverified"]).map(value=>String(value).replaceAll("_"," ")).join("; ")}. Checks, commitment and delivery are blocked until validity is restored.`,"notice"));
  if(stale)review.append(el("p","The ledger changed after this request was prepared. Create a new request against the current revision, then repeat its checks and review.","notice"));
  else if(request.state==="prepared"&&preview.within_budget===false)review.append(el("p","This proposal exceeds the remaining privacy budget. It cannot be committed; revise the release plan.","notice"));
  else if(phase==="prepared"&&valid)review.append(el("p","Next: run the automated checks. Preparation alone does not authorize a release.","review-note"));
  else if(phase==="checked"&&valid)review.append(el("p","Checks are recorded. A local operator must now record a rationale and acknowledge the scope before commitment.","review-note"));
  else if(phase==="reviewed"&&valid)review.append(el("p","The recorded checks and local review make this request eligible for commitment. The server rechecks eligibility when you commit.","review-note"));
  else if(phase==="committed"&&valid)review.append(el("p","The budget is committed. Download explicitly through the controlled route while its checks, review and authorization remain current.","review-note"));
  else if(phase==="revoked")review.append(el("p","Future delivery is revoked. Previous recipients retain their copies, audit history and committed privacy charges remain.","review-note"));
  if(pipeline.review_rationale){const recorded=el("div",null,"recorded-review");recorded.append(el("strong","Recorded local operator rationale"),el("p",pipeline.review_rationale));if(pipeline.reviewed_at)recorded.append(el("span",new Date(pipeline.reviewed_at*1000).toLocaleString(),"small muted"));review.append(recorded);}
  if(request.can_review===true && pipeline.check_digest && valid){
    const form=el("form",null,"operator-review-form");form.id="operator-review-form";
    const label=el("label","Local operator rationale","field");label.htmlFor="review-rationale";
    const rationale=el("textarea");rationale.id="review-rationale";rationale.required=true;rationale.minLength=20;rationale.maxLength=2000;rationale.rows=4;rationale.disabled=state.busy;rationale.placeholder="Explain why this specific model and release scope should proceed, given the checks and available evidence.";
    const key=`${request.request_id}:${pipeline.check_digest}`,draft=state.reviewDrafts[key] || {rationale:"",accept:false};rationale.value=draft.rationale;label.append(rationale);
    const counter=el("p",`${rationale.value.trim().length} / 2000 characters · at least 20`,"small muted");counter.id="review-counter";
    const acknowledgement=el("label",null,"scope-ack"),checkbox=el("input");checkbox.type="checkbox";checkbox.id="scope-ack";checkbox.required=true;checkbox.disabled=state.busy;checkbox.checked=draft.accept;
    acknowledgement.append(checkbox,el("span","I have reviewed this request’s checks and accept its declared scope: one fixed-record disability bit with public inputs held fixed. This local decision does not certify acceptable inference risk, full-record privacy or a lifelong guarantee."));
    const submit=el("button","Record local review","button primary");submit.type="submit";submit.dataset.mutation="";submit.dataset.action="review";
    form.append(el("h3","04 / Local operator review"),label,counter,acknowledgement,submit);review.append(form);
    function update(){state.reviewDrafts[key]={rationale:rationale.value,accept:checkbox.checked};counter.textContent=`${rationale.value.trim().length} / 2000 characters · at least 20`;submit.disabled=!canAct("review");}
    rationale.addEventListener("input",update);checkbox.addEventListener("change",update);update();
    form.addEventListener("submit",event=>{event.preventDefault();if(!canAct("review")||!form.reportValidity())return;mutate("review",{request_id:request.request_id,check_digest:pipeline.check_digest,rationale:rationale.value.trim(),accept_scope:true});});
  }
  actions.classList.remove("hidden");
  function actionButton(label,action,tone,callback){const button=el("button",label,`button ${tone}`);button.type="button";button.dataset.mutation="";button.dataset.action=action;button.disabled=!canAct(action);button.addEventListener("click",callback);actions.append(button);}
  if(request.state==="prepared"){
    actionButton(pipeline.check_digest?"Run checks again":"Run automated checks","checks",phase==="prepared"?"primary":"secondary",()=>mutate("checks",{request_id:request.request_id}));
    actionButton("Commit budget & authorize release","commit","primary",()=>mutate("commit",{request_id:request.request_id}));
  }
  if(request.state==="committed")actionButton("Download authorized package","download","primary",()=>downloadPackage(request.request_id));
  if(request.state==="prepared"||request.state==="committed")actionButton("Revoke this request","revoke","danger",()=>mutate("revoke",{request_id:request.request_id}));
  if(phase==="revoked")actions.append(el("span","No further delivery authorized","small muted"));
}

async function mutate(action,payload,rawPayload){
  if(!canAct(action))return;setBusy(true);message("operator-message","");
  try{
    const result=await api(`/${action}`,payload,rawPayload);if(result.request)state.request=result.request;
    const refreshed=await loadOperator();if(!refreshed){message("operator-message","The action completed, but the current workflow could not be refreshed. Actions remain unavailable until a successful refresh.");return;}
    if(action==="prepare")$("request-id").value=nextRequestId();
    const messages={prepare:"Request bound to the model and current ledger. Run its automated checks next.",checks:"Automated checks recorded. Inspect their result, then record a local operator review if eligible.",review:"Local operator review recorded against this check digest. Commitment still requires your explicit action.",commit:"Budget committed and release authorized. Download the package explicitly through the controlled route.",revoke:"Future delivery revoked. Prior copies, audit history and committed privacy charges are unchanged."};
    const blocked=["blocked","stale"].includes(workflowState(state.request));message("operator-message",blocked?"The workflow recorded this action but the request remains blocked or stale. Inspect its stages and audit details before continuing.":messages[action] || "Workflow action recorded.",blocked?"":"success");
  }catch(error){message("operator-message",errorText(error));await loadOperator();}
  finally{setBusy(false);renderRequest();}
}

async function downloadPackage(requestId){if(!canAct("download"))return;setBusy(true);message("operator-message","");try{const response=await fetch(`${API}/downloads/${encodeURIComponent(requestId)}`,{cache:"no-store"});if(!response.ok){let error;try{const data=await response.json();error=new Error(data.detail || "Download rejected");error.code=data.code;}catch{error=new Error(`Download rejected (${response.status})`);}throw error;}const blob=await response.blob(),url=URL.createObjectURL(blob),link=el("a");link.href=url;link.download=`${requestId.replace(/[^a-zA-Z0-9._-]/g,"_")}.zip`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);const refreshed=await loadOperator();message("operator-message",refreshed?"Authorized package sent to the browser for download. Its delivery authorization is recorded in the audit trail.":"Authorized package sent to the browser, but the workflow could not be refreshed. Refresh before further actions.",refreshed?"success":"");}catch(error){message("operator-message",errorText(error));await loadOperator();}finally{setBusy(false);renderRequest();}}

for(const button of document.querySelectorAll("[data-view]"))button.addEventListener("click",()=>{for(const nav of document.querySelectorAll("[data-view]")){nav.classList.toggle("active",nav===button);if(nav===button)nav.setAttribute("aria-current","page");else nav.removeAttribute("aria-current");}for(const view of document.querySelectorAll(".view"))view.classList.toggle("hidden",view.id!==`view-${button.dataset.view}`);if(button.dataset.view==="operator")loadOperator();$("main").scrollIntoView({behavior:"auto",block:"start"});});
$("scenario-select").addEventListener("change",(event)=>{state.scenario=event.target.value;state.step=1;renderTimeline();});$("interface-select").addEventListener("change",(event)=>{state.interface=event.target.value;renderTimeline();});$("raw-toggle").addEventListener("change",(event)=>{state.raw=event.target.checked;renderTimeline();});$("step-range").addEventListener("input",(event)=>{state.step=Number(event.target.value);renderTimeline();});$("refresh-operator").addEventListener("click",()=>{message("operator-message","");loadOperator();});
$("prepare-form").addEventListener("submit",(event)=>{event.preventDefault();if(!canAct("prepare"))return;const requestId=$("request-id").value.trim(),modelId=$("model-select").value;if(!requestId || !modelId)return;mutate("prepare",{request_id:requestId,model_id:modelId,expected_revision:state.operator.summary.revision});});
$("study-metrics").replaceChildren(metric("Release attempts","—","Reading verified evidence"),metric("Admitted releases","—","Committed release history","accent"),metric("Budget denials","—","No new package on denial","warning"),metric("Distinct model artifacts","—","Existing trained models"));
api("/study").then((study)=>{state.study=study;renderStudy();if(study.status!=="verified")message("global-message",study.detail || "Verified research evidence is not available from the local service.");}).catch((error)=>{message("global-message",errorText(error));$("study-status").textContent="Evidence unavailable";});

function modelSelectionChanged(){
  const previousRequestId=state.request?.request_id;
  if(previousRequestId){for(const key of Object.keys(state.reviewDrafts)){if(key.startsWith(`${previousRequestId}:`))delete state.reviewDrafts[key];}}
  state.request=null;
  $("prepare-button").disabled=!canAct("prepare");
  renderProvenance();renderRequest();
}
$("model-select").addEventListener("change",modelSelectionChanged);
renderPipeline();loadOperator();
