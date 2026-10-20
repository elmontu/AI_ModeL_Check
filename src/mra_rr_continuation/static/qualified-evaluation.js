(() => {
  'use strict';
  const API = '/api/research-qualified-evaluation';
  const TASKS = ['moh', 'mas', 'msf'], COMPARATORS = ['public_only', 'independent_rr'];
  const COUNTS = {moh:{train:8822,auxiliary:1976,test:6016},mas:{train:156,auxiliary:60,test:56},msf:{train:4,auxiliary:4,test:8}};
  const PHASE5 = '1f533833767c74bf262c18145c9bbe8c';
  const SPEC = 'b6fd59634f6ca82224f7febabf0e1c9bd960101a4de6e676df00a49039244295';
  const HISTORICAL = ['specification.json','runtime.json','preregistration.json','encoding-audit.json','cohort-plan.json','margin-rationale.json','qualification.txt','registration-completion.json', ...TASKS.flatMap(id => ['source-' + id + '.csv','source-' + id + '-metadata.json'])];
  const ARTIFACTS = [...HISTORICAL.map(name => 'phase5-' + name), 'evaluation-reservation.json','execution-contract.json','execution-runtime.json','cohorts.json','inputs.json','evaluation.json','models.json','predictions.json','reference-blocks.json','simulation-diagnostics.json','reproducibility.json','evaluation.txt','evaluation-completion.json'];
  const byId = id => document.getElementById(id);
  const put = (id, value) => { byId(id).textContent = value; };
  const plain = value => typeof value === 'string' && value.length > 0;
  const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const runId = value => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const integer = value => Number.isInteger(value) && value >= 0;
  const printable = value => value === null || value === undefined ? 'Unavailable' : String(value);
  const decision = (lower, upper) => lower > 0 ? 'pass' : upper <= 0 ? 'fail' : 'inconclusive';
  const aggregate = values => values.includes('fail') ? 'fail' : values.every(value => value === 'pass') ? 'pass' : 'inconclusive';
  const label = value => ({pass:'Pass',fail:'Fail',inconclusive:'Inconclusive',evaluated:'Evaluated',running:'Running',blocked:'Blocked'})[value] || printable(value);
  const scope = value => Boolean(value && value.agency_acceptance === 'pending' && value.operational_usefulness === 'not_evaluated' && value.authorization_effect === 'none' && value.production_execution_qualified === false);
  const number = value => finite(value) ? value === 0 ? '0' : Math.abs(value) < 0.00001 ? value.toExponential(5) : value.toFixed(6) : 'Unavailable';
  let catalog = null, contract = null, run = null, runs = [], busy = false, uncertain = false, ready = false, timer = null;
  const controls = {start:byId('evaluate-run'),saved:byId('saved-run'),open:byId('open-run'),refresh:byId('refresh-runs')};
  function error(message) { put('error', message); byId('error').hidden = !message; }
  function connected(value) { byId('connection').classList.toggle('online', value); put('connection-label', value ? 'Local public evaluation API' : 'Connection unavailable'); }
  async function request(path, options = {}) {
    let response;
    try { response = await fetch(API + path, {credentials:'same-origin',cache:'no-store',...options,headers:{Accept:'application/json',...(options.body ? {'Content-Type':'application/json'} : {})}}); }
    catch (_) { connected(false); throw new Error('The local public evaluation service could not be reached. Refresh the saved run list before another request.'); }
    connected(true);
    let body;
    try { body = await response.json(); } catch (_) { throw new Error('The service returned unreadable public evidence. Delivery is blocked.'); }
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Public evaluation request refused (HTTP ' + response.status + ').');
    return body;
  }
  function validCatalog(value) {
    return Boolean(value && value.schema === 'mra-qualified-evaluation-catalog/1.0' && value.phase5_run_id === PHASE5 && value.specification_sha256 === SPEC && digest(value.execution_contract_sha256) && typeof value.ready === 'boolean' && scope(value.scope) && value.repetitions_per_task === 16384 && value.comparisons_required === 6 && Array.isArray(value.blocked_reasons) && Array.isArray(value.tasks) && (!value.ready || value.tasks.length === 3 && TASKS.every(id => value.tasks.filter(task => task && task.id === id && plain(task.title) && task.qualification && task.qualification.split_counts && ['train','auxiliary','test'].every(split => task.qualification.split_counts[split] === COUNTS[id][split])).length === 1)));
  }
  function validResult(value) {
    if (!value || value.schema !== 'mra-qualified-public-evaluation/1.0' || !['pass','fail','inconclusive'].includes(value.status) || !Array.isArray(value.task_results) || value.task_results.length !== 3 || value.preregistration_id !== PHASE5 || value.specification_sha256 !== SPEC || value.agency_acceptance !== 'pending' || value.production_execution_qualified !== false || value.public_usefulness !== 'evaluated' || value.operational_usefulness !== 'not_evaluated' || value.authorization_effect !== 'none') return false;
    const statuses = [];
    for (const id of TASKS) {
      const matches = value.task_results.filter(task => task && task.task_id === id);
      if (matches.length !== 1) return false;
      const task = matches[0], comparisons = task.comparisons;
      if (!comparisons || Object.keys(comparisons).length !== 2 || !COMPARATORS.every(name => {
        const comparison = comparisons[name];
        return comparison && comparison.margin === 0 && comparison.repetitions === 16384 && comparison.family_size === 6 && comparison.family_alpha === 0.05 && finite(comparison.gain) && finite(comparison.lower) && finite(comparison.upper) && comparison.lower >= -1 && comparison.upper <= 1 && comparison.lower <= comparison.gain && comparison.gain <= comparison.upper && comparison.status === decision(comparison.lower, comparison.upper);
      })) return false;
      const taskStatus = aggregate(COMPARATORS.map(name => comparisons[name].status));
      if (task.status !== taskStatus) return false;
      statuses.push(taskStatus);
    }
    return value.status === aggregate(statuses);
  }
  function artifactURL(artifact, owner) {
    if (!artifact || !runId(owner) || !ARTIFACTS.includes(artifact.name) || artifact.url !== API + '/runs/' + owner + '/artifacts/' + artifact.name || !digest(artifact.sha256) || !integer(artifact.bytes) || artifact.bytes < 1) return null;
    const url = new URL(artifact.url, window.location.origin);
    return url.origin === window.location.origin && !url.search && !url.hash && !url.username && !url.password ? url.pathname : null;
  }
  function validRun(value) {
    if (!value || value.schema !== 'mra-qualified-evaluation-run/1.0' || !runId(value.run_id) || value.phase5_run_id !== PHASE5 || value.specification_sha256 !== SPEC || !catalog || value.execution_contract_sha256 !== catalog.execution_contract_sha256 || !scope(value.scope) || !Array.isArray(value.artifacts)) return false;
    if (value.status === 'running') return Boolean(value.result === null && value.artifacts.length === 0 && value.progress && integer(value.progress.done) && value.progress.done <= 16384 && value.progress.total === 16384 && (value.progress.task === null || TASKS.includes(value.progress.task)));
    return value.status === 'evaluated' && plain(value.reserved_at) && plain(value.completed_at) && validResult(value.result) && value.artifacts.length === ARTIFACTS.length && ARTIFACTS.every(name => value.artifacts.filter(item => item && item.name === name && artifactURL(item, value.run_id)).length === 1);
  }
  function updateControls() {
    controls.start.disabled = busy || !ready || uncertain || runs.some(item => item.status === 'blocked') || Boolean(run && run.status === 'running');
    controls.start.textContent = busy ? 'Checking saved execution…' : run && run.status === 'evaluated' ? 'Reopen saved evaluation' : 'Run frozen public evaluation';
    controls.saved.disabled = busy || !runs.length;
    controls.open.disabled = busy || !runId(controls.saved.value);
    controls.refresh.disabled = busy;
    byId('setup-panel').setAttribute('aria-busy', busy ? 'true' : 'false');
  }
  async function perform(callback) {
    if (busy) return;
    busy = true; error(''); updateControls();
    try { await callback(); } catch (exc) { error(exc.message || 'Public evaluation request failed.'); }
    finally { busy = false; updateControls(); }
  }
  function binding(target, term, value) {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = term; dd.textContent = printable(value); target.append(dt, dd);
  }
  function publicURL(value) {
    let url; try { url = new URL(value); } catch (_) { return null; }
    return url.protocol === 'https:' && (url.hostname === 'gov.sg' || url.hostname.endsWith('.gov.sg')) && !url.username && !url.password ? url.href : null;
  }
  function renderTasks() {
    const cards = byId('task-cards'); cards.replaceChildren();
    for (const id of TASKS) {
      const task = catalog.tasks.find(value => value.id === id);
      const card = document.createElement('article'); card.className = 'task-card';
      const title = document.createElement('h3'); title.textContent = task ? task.agency + ' · ' + task.title : id.toUpperCase() + ' · Required frame unavailable'; card.append(title);
      if (task) {
        const splits = task.qualification.split_counts;
        for (const text of ['Unit: ' + task.unit,'Train / auxiliary / held-out: ' + [splits.train,splits.auxiliary,splits.test].join(' / '),task.source_attribution]) { const p = document.createElement('p'); p.textContent = text; card.append(p); }
        const list = document.createElement('ul'); (task.qualification.limitations || []).forEach(text => { const li = document.createElement('li'); li.textContent = text; list.append(li); }); card.append(list);
        const links = document.createElement('div'); links.className = 'source-links';
        for (const [text,value] of [['Official public source',task.source_url],['Public data licence',task.licence_url]]) { const url = publicURL(value); if (url) { const a = document.createElement('a'); a.href = url; a.textContent = text; a.target = '_blank'; a.rel = 'noopener noreferrer'; links.append(a); } }
        card.append(links);
      }
      cards.append(card);
    }
  }
  function renderCatalog() {
    ready = catalog.ready && Boolean(contract);
    put('source-badge', ready ? 'Frozen evidence verified' : 'Execution blocked');
    byId('source-badge').className = 'tag ' + (ready ? 'pass' : 'blocked');
    put('source-status', ready ? 'The unchanged Phase 5 plan, all three public frames and execution contract verify. Execution saves one retained history per domain and uses the fixed number of replications.' : 'Frozen source or runtime evidence is unavailable or invalid. Execution is blocked.');
    const blocked = byId('blocked-reasons'); blocked.replaceChildren(); blocked.hidden = !catalog.blocked_reasons.length;
    catalog.blocked_reasons.forEach(text => { const li = document.createElement('li'); li.textContent = printable(text); blocked.append(li); });
    const bindings = byId('plan-bindings'); bindings.replaceChildren();
    binding(bindings,'Phase 5 preregistration',PHASE5); binding(bindings,'Frozen specification SHA-256',SPEC); binding(bindings,'Execution contract SHA-256',catalog.execution_contract_sha256); binding(bindings,'Repetitions per domain','16,384 paired replications; fixed batches of 256'); binding(bindings,'Mandatory comparisons','Three domains × public-only and independent RR = six'); binding(bindings,'Research rule','Pass: lower gain > 0; fail: upper gain ≤ 0; otherwise inconclusive');
    put('contract-inspector',contract ? JSON.stringify(contract,null,2) : 'Execution contract unavailable; execution blocked.');
    const links = byId('contract-links'); links.replaceChildren();
    if (contract) { const a = document.createElement('a'); a.className = 'download-link'; a.href = API + '/execution-contract'; a.download = 'execution-contract.json'; a.textContent = 'execution-contract.json'; links.append(a); }
    renderTasks(); updateControls();
  }
  function renderRuns() {
    const selected = run && run.run_id || controls.saved.value;
    controls.saved.replaceChildren();
    if (!runs.length) { const option = document.createElement('option'); option.value = ''; option.textContent = 'No saved evaluations'; controls.saved.append(option); }
    for (const value of runs) { const option = document.createElement('option'); option.value = value.run_id; option.textContent = value.run_id + ' · ' + label(value.status); controls.saved.append(option); }
    if (runs.some(value => value.run_id === selected)) controls.saved.value = selected;
    updateControls();
  }
  async function loadRuns() {
    const value = await request('/runs');
    if (!value || value.schema !== 'mra-qualified-evaluation-runs/1.0' || !Array.isArray(value.runs) || !value.runs.every(item => item && runId(item.run_id) && ['running','evaluated','blocked'].includes(item.status)) || new Set(value.runs.map(item => item.run_id)).size !== value.runs.length) throw new Error('Saved evaluation list is inconsistent. Execution is blocked.');
    runs = value.runs; renderRuns();
  }
  function addRow(target, values, status) {
    const tr = document.createElement('tr');
    values.forEach((text,index) => { const td = document.createElement('td'); td.textContent = printable(text); if (index === 2 || index === 3) td.className = 'numeric'; if (index === 5) td.className = 'criterion ' + status; tr.append(td); }); target.append(tr);
  }
  function renderRun() {
    byId('run-detail').hidden = !run || run.status !== 'evaluated';
    if (!run) return;
    if (run.status === 'running') {
      const progress = run.progress, index = progress.task === null ? 0 : TASKS.indexOf(progress.task);
      put('execution-status', progress.task === null ? 'Preparing exact public outcome bits, retained responses and certificates before fitting.' : progress.task.toUpperCase() + ': ' + progress.done.toLocaleString() + ' / 16,384 paired replications completed. The retained history is already saved.');
      const bar = byId('evaluation-progress'); bar.hidden = false; bar.value = index * 16384 + progress.done;
      return;
    }
    byId('evaluation-progress').hidden = true;
    put('execution-status','Saved evaluation verified. Reopening and downloading rechecks the same captured evidence without drawing another history or block.');
    const result = run.result, status = result.status;
    put('research-decision',label(status)); put('result-badge',label(status));
    byId('result-badge').className = 'tag ' + status;
    const explanation = {pass:'All six mandatory comparisons show strictly positive lower expected Brier-gain bounds on their fixed public held-out frames.',fail:'At least one mandatory comparison has a nonpositive upper expected Brier-gain bound, so the frozen research criterion fails.',inconclusive:'The six mandatory comparisons do not all establish strict superiority, and no mandatory comparison establishes failure. The frozen research decision is inconclusive.'}[status];
    put('result-explanation',explanation + ' Agency acceptance, operational usefulness and release authorization remain pending or absent.');
    byId('result-explanation').className = 'result-explanation ' + status;
    const rows = byId('comparison-rows'); rows.replaceChildren();
    for (const id of TASKS) { const task = result.task_results.find(item => item.task_id === id); for (const comparator of COMPARATORS) { const comparison = task.comparisons[comparator]; addRow(rows,[id.toUpperCase(),comparator === 'public_only' ? 'Clean public-only auxiliary' : 'Independent RR',number(comparison.gain),'[' + number(comparison.lower) + ', ' + number(comparison.upper) + ']','Lower > 0; upper ≤ 0 fails',label(comparison.status)],comparison.status); } }
    const bindings = byId('result-bindings'); bindings.replaceChildren();
    binding(bindings,'Evaluation identifier',run.run_id); binding(bindings,'Execution reserved (UTC)',run.reserved_at); binding(bindings,'Completed (UTC)',run.completed_at); binding(bindings,'Monte Carlo scope','Fixed historical test-frame census, conditional on one saved retained history per domain'); binding(bindings,'Release authority','None');
    put('result-inspector',JSON.stringify(result,null,2));
    const links = byId('artifact-links'); links.replaceChildren();
    run.artifacts.forEach(artifact => { const url = artifactURL(artifact,run.run_id); if (!url) return; const a = document.createElement('a'); a.className = 'download-link'; a.href = url; a.download = artifact.name; a.textContent = artifact.name; a.title = 'SHA-256: ' + artifact.sha256 + ' · ' + artifact.bytes + ' bytes'; links.append(a); });
    put('artifact-status',run.artifacts.length + ' captured artifacts verified for delivery. Reference model and first-block scores are descriptive; the decision uses all fixed replications.');
  }
  function schedulePoll() {
    if (timer) window.clearTimeout(timer);
    timer = null;
    if (!run || run.status !== 'running') return;
    const owner = run.run_id;
    timer = window.setTimeout(() => {
      if (!run || run.run_id !== owner || run.status !== 'running') return;
      if (busy) { schedulePoll(); return; }
      perform(async () => { await openRun(owner); await loadRuns(); });
    },2000);
  }
  async function openRun(owner) {
    if (!runId(owner)) throw new Error('Select a valid saved evaluation identifier.');
    const value = await request('/runs/' + owner);
    if (!validRun(value) || value.run_id !== owner) { ready = false; throw new Error('Saved evaluation, authority fields, six decisions or artifact links failed validation. Delivery is blocked.'); }
    run = value; uncertain = false;
    window.history.replaceState(null,'','#run=' + owner);
    renderRun(); renderRuns(); schedulePoll();
  }
  async function setup() {
    const value = await request('/catalog');
    if (!validCatalog(value)) throw new Error('The source catalog differs from the frozen three-domain plan. Execution is blocked.');
    catalog = value; contract = null;
    if (catalog.ready) {
      const response = await fetch(API + '/execution-contract',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
      if (!response.ok) throw new Error('The fixed execution contract could not be verified.');
      const raw = new Uint8Array(await response.arrayBuffer());
      if (!window.crypto || !window.crypto.subtle) throw new Error('WebCrypto is required to verify the execution contract before execution.');
      const actual = Array.from(new Uint8Array(await window.crypto.subtle.digest('SHA-256',raw)),value => value.toString(16).padStart(2,'0')).join('');
      if (actual !== catalog.execution_contract_sha256) throw new Error('Execution contract bytes differ from the frozen catalog digest. Execution is blocked.');
      contract = JSON.parse(new TextDecoder().decode(raw));
    }
    renderCatalog(); await loadRuns();
    const match = /^#run=([a-f0-9]{32})$/.exec(window.location.hash);
    const owner = match ? match[1] : runs.find(item => item.status === 'evaluated' || item.status === 'running')?.run_id;
    if (owner) await openRun(owner);
    else if (runs.some(item => item.status === 'blocked')) put('execution-status','An interrupted or invalid evaluation is reserved and blocked. Preserve its evidence; a replacement draw is refused.');
    else uncertain = false;
  }
  controls.start.addEventListener('click',() => perform(async () => {
    uncertain = true; updateControls();
    const value = await request('/runs',{method:'POST',body:'{}'});
    if (!validRun(value)) { ready = false; throw new Error('The evaluation response differs from the frozen contract. Refresh saved evidence before proceeding.'); }
    run = value; uncertain = false; window.history.replaceState(null,'','#run=' + value.run_id); renderRun(); await loadRuns(); schedulePoll();
  }));
  controls.open.addEventListener('click',() => perform(() => openRun(controls.saved.value)));
  controls.saved.addEventListener('change',updateControls);
  controls.refresh.addEventListener('click',() => perform(setup));
  perform(setup);
})();
