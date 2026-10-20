/* Fixed Phase 5 public-source qualification and preregistration; no fitting endpoint. */
(() => {
  'use strict';
  const API = '/api/research-qualified-benchmark';
  const TASKS = ['moh', 'mas', 'msf'];
  const ARTIFACTS = ['specification.json', 'runtime.json', 'preregistration.json', 'encoding-audit.json', 'cohort-plan.json', 'margin-rationale.json', 'qualification.txt', 'registration-completion.json', ...TASKS.flatMap(task => ['source-' + task + '.csv', 'source-' + task + '-metadata.json'])];
  const byId = id => document.getElementById(id);
  const controls = {register: byId('register-run'), saved: byId('saved-run'), open: byId('open-run'), refresh: byId('refresh-runs')};
  let catalog = null, specification = null, run = null, runs = [], busy = false, action = '', sourceReady = false, uncertain = false;
  const put = (id, value) => { byId(id).textContent = value; };
  const printable = value => value === null || value === undefined ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  const digest = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
  const runId = value => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value);
  const text = value => typeof value === 'string' && value.trim().length > 0;
  const integer = value => Number.isSafeInteger(value) && value >= 0;
  const validScope = scope => Boolean(scope && scope.data === 'official public aggregate records' && scope.representation === 'Census of eligible published historical held-out observations only' && scope.agency_acceptance === 'pending' && scope.operational_usefulness === 'not_evaluated' && scope.authorization_effect === 'none' && scope.production_execution_qualified === false);
  const validMargin = margin => Boolean(margin && margin.metric === 'Brier loss' && margin.value === '0/1' && margin.pass === 'lower gain > 0' && margin.fail === 'upper gain <= 0' && text(margin.rationale) && margin.operational_margin === null && margin.agency_acceptance === 'pending');
  const validQualification = value => Boolean(value && integer(value.raw_observations) && integer(value.eligible_observations) && value.eligible_observations > 0 && value.raw_observations >= value.eligible_observations && value.split_counts && ['train', 'auxiliary', 'test'].every(split => integer(value.split_counts[split]) && value.split_counts[split] > 0) && ['train', 'auxiliary', 'test'].reduce((sum, split) => sum + value.split_counts[split], 0) === value.eligible_observations && Array.isArray(value.features) && value.features.length > 0 && value.features.every(text) && value.unknown_or_missing_encodings === 0 && text(value.calendar_method) && Array.isArray(value.limitations) && value.limitations.every(text));
  const taskSet = tasks => Array.isArray(tasks) && tasks.length === 3 && TASKS.every((id, index) => tasks[index] && tasks[index].id === id);
  const validTask = task => Boolean(task && TASKS.includes(task.id) && text(task.agency) && text(task.title) && text(task.source_url) && text(task.licence_url) && text(task.source_attribution) && text(task.unit) && task.temporal_splits && ['train', 'auxiliary', 'test'].every(split => text(task.temporal_splits[split])) && validMargin(task.research_margin));
  const validCatalog = value => Boolean(value && value.schema === 'mra-qualified-benchmark-catalog/1.0' && digest(value.specification_sha256) && validScope(value.scope) && Array.isArray(value.tasks_order) && value.tasks_order.length === 3 && TASKS.every((id, index) => value.tasks_order[index] === id) && taskSet(value.tasks) && value.tasks.every(validTask) && Array.isArray(value.blocked_reasons) && value.blocked_reasons.every(text));
  const validSpecification = value => Boolean(value && value.schema === 'mra-qualified-public-preregistration/1.0' && validScope(value.scope) && Array.isArray(value.tasks_order) && value.tasks_order.length === 3 && TASKS.every((id, index) => value.tasks_order[index] === id && value.sources && value.sources[id]) && Array.isArray(value.comparisons) && value.comparisons.length === 6 && TASKS.every(id => ['public_only', 'independent_rr'].every(comparator => value.comparisons.filter(comparison => comparison && comparison.task === id && comparison.comparator === comparator).length === 1)));
  const validRegistered = value => Boolean(value && value.schema === 'mra-qualified-benchmark-run/1.0' && runId(value.run_id) && value.status === 'preregistered' && text(value.preregistered_at) && digest(value.specification_sha256) && validScope(value.scope) && taskSet(value.tasks) && value.tasks.every(task => validTask(task) && validQualification(task.qualification)) && value.comparisons_required === 6 && value.public_usefulness === 'not_evaluated' && Array.isArray(value.artifacts) && ARTIFACTS.every(name => value.artifacts.filter(artifact => artifact && artifact.name === name && digest(artifact.sha256) && integer(artifact.bytes) && artifact.bytes > 0 && artifactURL(artifact, value.run_id)).length === 1));
  const currentPlan = () => Boolean(run && catalog && run.specification_sha256 === catalog.specification_sha256);
  const formatTime = value => { const date = new Date(value); return Number.isNaN(date.getTime()) ? printable(value) : date.toLocaleString(undefined, {year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}); };
  function showError(message) { put('error', message); byId('error').hidden = !message; }
  function connected(online) { byId('connection').classList.toggle('online', online); put('connection-label', online ? 'Local public qualification API' : 'Connection unavailable'); }
  async function request(path, options = {}) {
    let response;
    try { response = await fetch(API + path, {credentials: 'same-origin', cache: 'no-store', ...options, headers: {Accept: 'application/json', ...(options.body ? {'Content-Type': 'application/json'} : {})}}); }
    catch (_) { connected(false); sourceReady = false; throw new Error('The local qualification service could not be reached. Start the demo, then refresh before continuing.'); }
    let body, specificationBytes = null;
    try {
      if (path === '/specification') { const raw = await response.text(); specificationBytes = new TextEncoder().encode(raw); body = JSON.parse(raw); }
      else body = await response.json();
    }
    catch (_) { sourceReady = false; throw new Error('The service returned unreadable evidence. Refresh and reopen the saved plan.'); }
    connected(true);
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'The public qualification request was refused (HTTP ' + response.status + ').');
    if (specificationBytes) {
      if (!window.crypto || !window.crypto.subtle) { sourceReady = false; throw new Error('This browser cannot verify the fixed specification digest. Open the loopback demo in a browser with WebCrypto support.'); }
      const actual = Array.from(new Uint8Array(await window.crypto.subtle.digest('SHA-256', specificationBytes)), value => value.toString(16).padStart(2, '0')).join('');
      if (!catalog || actual !== catalog.specification_sha256) { sourceReady = false; throw new Error('The fixed specification bytes do not match the source catalog. Preregistration is blocked.'); }
    }
    return body;
  }
  function updateControls() {
    const blockedSaved = Boolean(catalog && runs.some(item => item.status !== 'preregistered' && item.specification_sha256 === catalog.specification_sha256));
    controls.register.disabled = busy || !sourceReady || uncertain || blockedSaved || Boolean(run && (!validRegistered(run) || !currentPlan()));
    controls.register.textContent = action === 'register' ? 'Preregistering…' : 'Preregister fixed public benchmark';
    controls.saved.disabled = busy || !runs.length;
    controls.open.disabled = busy || !runId(controls.saved.value);
    controls.refresh.disabled = busy;
    byId('setup-panel').setAttribute('aria-busy', busy ? 'true' : 'false');
    byId('run-detail').setAttribute('aria-busy', busy ? 'true' : 'false');
  }
  async function perform(kind, callback) {
    if (busy) return;
    busy = true; action = kind; showError(''); updateControls();
    try { await callback(); }
    catch (error) { showError(error.message || 'The public qualification request failed.'); }
    finally { busy = false; action = ''; updateControls(); }
  }
  function addBinding(target, label, value) {
    const term = document.createElement('dt'), description = document.createElement('dd');
    term.textContent = label; description.textContent = printable(value); target.append(term, description);
  }
  function artifactURL(artifact, owner) {
    if (!artifact || typeof artifact.name !== 'string' || typeof artifact.url !== 'string') return null;
    if (owner ? !runId(owner) || !ARTIFACTS.includes(artifact.name) : artifact.name !== 'qualified-benchmark-specification.json') return null;
    const expected = owner ? API + '/runs/' + owner + '/artifacts/' + artifact.name : API + '/specification';
    if (artifact.url !== expected) return null;
    const url = new URL(artifact.url, window.location.origin);
    return url.origin === window.location.origin && !url.search && !url.hash && !url.username && !url.password ? url.pathname : null;
  }
  function renderLinks(target, artifacts, owner) {
    target.replaceChildren();
    let count = 0;
    if (Array.isArray(artifacts)) artifacts.forEach(artifact => {
      const url = artifactURL(artifact, owner);
      if (!url) return;
      const link = document.createElement('a'); link.className = 'download-link'; link.href = url; link.download = artifact.name; link.textContent = artifact.name;
      if (digest(artifact.sha256)) link.title = 'SHA-256: ' + artifact.sha256 + ' · ' + printable(artifact.bytes) + ' bytes';
      target.append(link); count += 1;
    });
    return count;
  }
  function publicURL(value) {
    if (typeof value !== 'string') return null;
    let url;
    try { url = new URL(value); } catch (_) { return null; }
    return url.protocol === 'https:' && (url.hostname === 'gov.sg' || url.hostname.endsWith('.gov.sg')) && !url.username && !url.password ? url.href : null;
  }
  function row(target, values) { const tr = document.createElement('tr'); values.forEach(value => { const cell = document.createElement('td'); cell.textContent = printable(value); tr.append(cell); }); target.append(tr); }
  function renderTasks(tasks) {
    const cards = byId('task-cards'), encodings = byId('encoding-rows'), margins = byId('margin-rows');
    cards.replaceChildren(); encodings.replaceChildren(); margins.replaceChildren();
    TASKS.forEach(id => {
      const task = Array.isArray(tasks) ? tasks.find(item => item && item.id === id) : null;
      const article = document.createElement('article'); article.className = 'task-card';
      const heading = document.createElement('h3'); heading.textContent = task ? task.agency + ' · ' + task.title : id.toUpperCase() + ' · Required public task unavailable'; article.append(heading);
      if (!task) { const absent = document.createElement('p'); absent.className = 'source-state warning'; absent.textContent = 'Required public domain is missing; registration is blocked.'; article.append(absent); cards.append(article); row(encodings, [id.toUpperCase(), 'Unavailable', 'Unavailable', 'Not validated', 'Unavailable']); row(margins, [id.toUpperCase(), 'Unavailable', 'Registration blocked', 'Unavailable', 'Pending']); return; }
      const unit = document.createElement('p'); unit.className = 'frame-unit'; unit.textContent = 'Observation unit: ' + printable(task.unit); article.append(unit);
      const attribution = document.createElement('p'); attribution.textContent = printable(task.source_attribution); article.append(attribution);
      ['train', 'auxiliary', 'test'].forEach(split => { const paragraph = document.createElement('p'); paragraph.textContent = ({train: 'Training frame', auxiliary: 'Clean auxiliary frame', test: 'Held-out target frame'})[split] + ': ' + printable(task.temporal_splits && task.temporal_splits[split]); article.append(paragraph); });
      const qualification = task.qualification, valid = validQualification(qualification);
      const state = document.createElement('p'); state.className = 'source-state' + (valid ? '' : ' warning'); state.textContent = valid ? 'Public encodings and finite frame validated' : 'Public qualification incomplete · registration blocked'; article.append(state);
      if (qualification) {
        const features = document.createElement('p'); features.textContent = 'Validated public features: ' + (Array.isArray(qualification.features) ? qualification.features.join(', ') : 'unavailable'); article.append(features);
        if (Array.isArray(qualification.limitations)) { const limitations = document.createElement('ul'); qualification.limitations.forEach(value => { const item = document.createElement('li'); item.textContent = printable(value); limitations.append(item); }); article.append(limitations); }
      }
      const links = document.createElement('div'); links.className = 'source-links';
      [['Official public source', task.source_url], ['Public data licence', task.licence_url]].forEach(([label, value]) => { const url = publicURL(value); if (!url) return; const link = document.createElement('a'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = label; links.append(link); }); article.append(links); cards.append(article);
      const splits = qualification && qualification.split_counts;
      row(encodings, [task.agency, qualification ? printable(qualification.raw_observations) + ' / ' + printable(qualification.eligible_observations) : 'Not validated', splits ? ['train', 'auxiliary', 'test'].map(split => printable(splits[split])).join(' / ') : 'Not validated', qualification ? qualification.unknown_or_missing_encodings : 'Not validated', qualification ? qualification.calendar_method : 'Not validated']);
      const margin = task.research_margin;
      row(margins, [task.agency, margin ? margin.metric + ' · ' + margin.value : 'Unavailable', margin ? 'Pass: ' + margin.pass + '; fail: ' + margin.fail + '; otherwise inconclusive' : 'Unavailable', margin ? margin.rationale : 'Unavailable', 'Agency acceptance pending; operational positive margin not approved']);
    });
  }
  function renderCatalog() {
    const valid = validCatalog(catalog);
    sourceReady = Boolean(valid && validSpecification(specification) && catalog.ready === true && catalog.blocked_reasons.length === 0 && catalog.tasks.every(task => validQualification(task.qualification)));
    put('source-badge', sourceReady ? 'Three public frames validated' : 'Preregistration blocked');
    put('source-status', sourceReady ? 'All three public sources on D passed encoding validation and complete eligible-frame accounting. The fixed plan is ready for prospective preregistration.' : 'One or more mandatory public sources, encoding checks, frame counts or plan bindings are unavailable or rejected. Preregistration is blocked; no task is substituted.');
    byId('source-status').classList.toggle('warning', !sourceReady);
    const reasons = byId('blocked-reasons'); reasons.replaceChildren();
    if (catalog && Array.isArray(catalog.blocked_reasons)) catalog.blocked_reasons.forEach(value => { const item = document.createElement('li'); item.textContent = printable(value); reasons.append(item); });
    if (!valid) { const item = document.createElement('li'); item.textContent = 'The complete three-domain public plan could not be validated.'; reasons.append(item); }
    reasons.hidden = reasons.children.length === 0;
    put('stage-state-1', sourceReady ? 'Three domains validated' : 'Mandatory validation pending');
    put('stage-state-2', sourceReady ? 'Eligible frames accounted for' : 'Coverage validation pending');
    byId('stage-1').classList.toggle('done', sourceReady); byId('stage-2').classList.toggle('done', sourceReady);
    put('encoding-status', sourceReady ? 'Validated' : 'Incomplete');
    renderTasks(catalog && catalog.tasks);
    put('qualification-inspector', JSON.stringify(catalog && catalog.tasks ? catalog.tasks.map(task => ({id: task.id, qualification: task.qualification})) : null, null, 2));
    put('specification-digest', 'Specification SHA-256: ' + printable(catalog && catalog.specification_sha256));
    put('specification-inspector', JSON.stringify(specification, null, 2));
    renderLinks(byId('specification-links'), [{name: 'qualified-benchmark-specification.json', url: API + '/specification'}], null);
    updateControls();
  }
  function renderSavedRuns() {
    const selected = run ? run.run_id : controls.saved.value;
    controls.saved.replaceChildren();
    const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = runs.length ? 'Select a saved public plan…' : 'No saved public preregistrations'; controls.saved.append(placeholder);
    runs.forEach(item => { if (!runId(item.run_id)) return; const option = document.createElement('option'); option.value = item.run_id; option.textContent = formatTime(item.preregistered_at) + ' · ' + item.run_id.slice(0, 8) + ' · ' + printable(item.status).replaceAll('_', ' '); controls.saved.append(option); });
    if (runs.some(item => item.run_id === selected)) controls.saved.value = selected;
    updateControls();
  }
  async function refreshRuns() {
    const data = await request('/runs');
    if (!data || data.schema !== 'mra-qualified-benchmark-runs/1.0' || !Array.isArray(data.runs)) throw new Error('The saved public plan list has an unexpected format.');
    runs = data.runs;
    const unavailable = Math.max(Number.isSafeInteger(data.unavailable_run_count) && data.unavailable_run_count > 0 ? data.unavailable_run_count : 0, runs.filter(item => item.status !== 'preregistered').length);
    put('saved-run-status', unavailable ? unavailable + ' preserved preregistration(s) could not be validated. Keep the saved evidence for inspection.' : '');
    byId('saved-run-status').hidden = !unavailable; renderSavedRuns();
  }
  function renderRun() {
    byId('run-detail').hidden = !run;
    if (!run) { updateControls(); return; }
    const valid = validRegistered(run), matching = currentPlan();
    put('run-label', 'Saved plan ' + printable(run.run_id));
    put('registration-status', valid ? 'Preregistered' : 'Incomplete evidence · blocked');
    byId('registration-status').className = 'tag ' + (valid ? 'preregistered' : 'blocked');
    put('plan-decision', valid ? 'Preregistered' : 'Incomplete');
    const bindings = byId('registration-bindings'); bindings.replaceChildren();
    addBinding(bindings, 'Preregistered before fitting', formatTime(run.preregistered_at));
    addBinding(bindings, 'Registration ID', run.run_id);
    addBinding(bindings, 'Specification SHA-256', run.specification_sha256);
    addBinding(bindings, 'Mandatory comparisons', run.comparisons_required);
    addBinding(bindings, 'Population claim', run.scope && run.scope.representation);
    addBinding(bindings, 'Public usefulness', 'Not evaluated');
    addBinding(bindings, 'Agency acceptance', 'Pending');
    addBinding(bindings, 'Release authorization', 'None');
    put('registration-inspector', JSON.stringify(run, null, 2));
    const message = valid ? 'All three public frames, validated encodings and six comparison criteria are prospectively retained. Public usefulness has not been evaluated. Reopening verifies this saved plan without fitting.' : 'The saved registration is incomplete or has missing mandatory evidence. Preserve it; replacement registration is blocked across requests and restarts.';
    put('registration-explanation', matching ? message : message + ' Its specification differs from the current catalog; registration is blocked.');
    put('pipeline-message', uncertain ? 'Registration outcome is unconfirmed. Refresh and open the saved public plan before taking another action.' : message);
    put('stage-state-3', valid ? 'Fixed plan preregistered' : 'Saved evidence incomplete');
    put('stage-state-4', valid ? 'Source and plan evidence saved' : 'Preserved for inspection');
    byId('stage-3').classList.toggle('done', valid); byId('stage-4').classList.toggle('done', valid);
    const count = renderLinks(byId('artifact-links'), run.artifacts, run.run_id);
    put('artifact-status', count + ' saved artifact(s) available. Usefulness scores and agency acceptance are not established by preregistration.');
    updateControls();
  }
  function adopt(value) {
    if (!value || !runId(value.run_id)) { uncertain = true; throw new Error('The service returned an invalid registration identity. Refresh and inspect the saved list before continuing.'); }
    run = value; uncertain = !validRegistered(value);
    window.history.replaceState(null, '', '#run=' + run.run_id); renderRun();
  }
  async function openRun(id) { if (!runId(id)) throw new Error('Choose a valid saved public plan.'); adopt(await request('/runs/' + id)); }
  async function refresh() {
    sourceReady = false; updateControls();
    catalog = await request('/catalog'); specification = await request('/specification'); renderCatalog(); await refreshRuns();
    if (run) { try { await openRun(run.run_id); } catch (error) { uncertain = true; renderRun(); throw error; } }
  }
  controls.register.addEventListener('click', () => perform('register', async () => {
    if (!sourceReady || uncertain || run && (!validRegistered(run) || !currentPlan())) return;
    put('pipeline-message', 'Saving the fixed prospective public plan before any benchmark fitting.');
    try { adopt(await request('/runs', {method: 'POST', body: '{}'})); }
    catch (error) { uncertain = true; put('pipeline-message', 'Registration outcome is unconfirmed. Refresh the saved list and open the retained plan; do not attempt a replacement registration.'); throw error; }
    await refreshRuns(); byId('registration-title').focus();
  }));
  controls.open.addEventListener('click', () => perform('open', async () => { await openRun(controls.saved.value); byId('registration-title').focus(); }));
  controls.saved.addEventListener('change', updateControls);
  controls.refresh.addEventListener('click', () => perform('refresh', refresh));
  perform('initialize', async () => { await refresh(); const match = /^#run=([0-9a-f]{32})$/.exec(window.location.hash || ''); if (match) await openRun(match[1]); });
})();
