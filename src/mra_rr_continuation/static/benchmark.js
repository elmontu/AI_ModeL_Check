/* This page accepts only the packaged public benchmark and registered local artifacts. */
(() => {
  'use strict';
  const API = '/api/research-benchmark';
  const DOMAINS = ['acs', 'bts', 'hmda', 'tlc'];
  const ROUTES = ['public_only', 'independent_rr', 'certified_continuation'];
  const COMPARATORS = ['public_only', 'independent_rr'];
  const ROUTE_NAMES = {public_only: 'Clean public-only', independent_rr: 'Independent RR', certified_continuation: 'Certified continuation'};
  const LABELS = {pass: 'Pass', fail: 'Fail', inconclusive: 'Inconclusive', not_evaluated: 'Not evaluated'};
  const byId = id => document.getElementById(id);
  const controls = {register: byId('register-run'), saved: byId('saved-run'), open: byId('open-run'), refresh: byId('refresh-runs'), evaluate: byId('evaluate-run')};
  let catalog = null, run = null, runs = [], busy = false, sourceReady = false, action = '', uncertain = false;
  const put = (id, value) => { byId(id).textContent = value; };
  const printable = value => value === null || value === undefined ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const number = value => finite(value) ? value.toFixed(5) : '—';
  const digest = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
  const runId = value => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value);
  const taskSource = (spec, corpus) => spec && spec.sources ? spec.sources[corpus] || {} : {};
  const taskTitle = (spec, corpus) => taskSource(spec, corpus).title || corpus.toUpperCase();
  const validSpec = spec => Boolean(spec && spec.schema === 'mra-public-benchmark-specification/1.0' && Array.isArray(spec.tasks_order) && spec.tasks_order.length === 4 && DOMAINS.every((corpus, index) => spec.tasks_order[index] === corpus && spec.sources && spec.sources[corpus] && digest(spec.sources[corpus].data_sha256) && digest(spec.sources[corpus].manifest_sha256)));
  const sourceSet = sources => Array.isArray(sources) && sources.length === 4 && DOMAINS.every(corpus => sources.filter(source => source.corpus === corpus).length === 1);
  const sourcesMatch = (sources, spec) => sourceSet(sources) && DOMAINS.every(corpus => { const source = sources.find(item => item.corpus === corpus), pinned = taskSource(spec, corpus); return source.data_sha256 === pinned.data_sha256 && source.manifest_sha256 === pinned.manifest_sha256; });
  const registered = () => Boolean(run && runId(run.run_id) && validSpec(run.specification) && digest(run.specification_sha256) && sourcesMatch(run.sources, run.specification));
  const specMatches = () => Boolean(registered() && catalog && run.specification_sha256 === catalog.specification_sha256);
  const validComparison = comparison => comparison && Object.hasOwn(LABELS, comparison.status) && ['pass', 'fail', 'inconclusive'].includes(comparison.status) && [comparison.gain, comparison.lower, comparison.upper, comparison.margin].every(finite) && comparison.lower <= comparison.gain && comparison.gain <= comparison.upper;
  const completeResult = result => Boolean(result && ['pass', 'fail', 'inconclusive'].includes(result.status) && Array.isArray(result.task_results) && result.task_results.length === 4 && DOMAINS.every((corpus, index) => {
    const task = result.task_results[index];
    return task && task.task_id === corpus && COMPARATORS.every(comparator => validComparison(task.comparisons && task.comparisons[comparator])) && ROUTES.every(route => finite(task.expected_brier && task.expected_brier[route]) && finite(task.reference_brier && task.reference_brier[route]));
  }));
  const evaluationReady = () => registered() && specMatches() && sourceReady && !uncertain && (run.status === 'registered' || (run.status === 'completed' && completeResult(run.result)));
  const formatTime = value => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? printable(value) : date.toLocaleString(undefined, {year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
  };
  function showError(message) { put('error', message); byId('error').hidden = !message; }
  function connected(online) { byId('connection').classList.toggle('online', online); put('connection-label', online ? 'Local public benchmark API' : 'Connection unavailable'); }
  async function request(path, options = {}) {
    let response;
    try { response = await fetch(API + path, {credentials: 'same-origin', cache: 'no-store', ...options, headers: {Accept: 'application/json', ...(options.body ? {'Content-Type': 'application/json'} : {})}}); }
    catch (_) { connected(false); sourceReady = false; throw new Error('The local benchmark service could not be reached. Start the demo, then refresh before continuing.'); }
    let body;
    try { body = await response.json(); }
    catch (_) { sourceReady = false; throw new Error('The service returned an unreadable response. Refresh and reopen the saved registration.'); }
    connected(true);
    if (!response.ok) {
      const error = new Error(typeof body.detail === 'string' ? body.detail : typeof body.error === 'string' ? body.error : 'The request was refused (HTTP ' + response.status + ').');
      error.status = response.status; throw error;
    }
    return body;
  }
  function updateControls() {
    controls.register.disabled = busy || !sourceReady || uncertain || Boolean(run && (run.status === 'reserved_incomplete' || !registered() || !specMatches() || (run.status === 'completed' && !completeResult(run.result))));
    controls.register.textContent = action === 'register' ? 'Registering…' : 'Register fixed benchmark';
    controls.saved.disabled = busy || !runs.length;
    controls.open.disabled = busy || !runId(controls.saved.value);
    controls.refresh.disabled = busy;
    controls.evaluate.disabled = busy || !evaluationReady();
    controls.evaluate.textContent = action === 'evaluate' ? 'Running fixed benchmark…' : run && run.status === 'completed' ? 'Reopen saved results' : 'Run fixed benchmark';
    byId('setup-panel').setAttribute('aria-busy', busy ? 'true' : 'false');
    byId('run-detail').setAttribute('aria-busy', busy ? 'true' : 'false');
  }
  async function perform(kind, callback) {
    if (busy) return;
    busy = true; action = kind; showError(''); updateControls();
    try { await callback(); }
    catch (error) { showError(error.message || 'The benchmark request failed.'); }
    finally { busy = false; action = ''; updateControls(); }
  }
  function addBinding(target, label, value) {
    const term = document.createElement('dt'), description = document.createElement('dd');
    term.textContent = label; description.textContent = printable(value); target.append(term, description);
  }
  function artifactURL(artifact, owner) {
    if (!artifact || typeof artifact.name !== 'string' || !/^[a-z0-9][a-z0-9._-]{0,119}$/.test(artifact.name) || typeof artifact.url !== 'string' || !artifact.url.startsWith('/')) return null;
    const expected = owner ? API + '/runs/' + owner + '/artifacts/' + artifact.name : API + '/specification';
    if ((owner && !runId(owner)) || artifact.url !== expected) return null;
    const url = new URL(artifact.url, window.location.origin);
    return url.origin === window.location.origin && !url.search && !url.hash && !url.username && !url.password ? url.pathname : null;
  }
  function renderLinks(target, artifacts, owner) {
    target.replaceChildren();
    if (!Array.isArray(artifacts)) return 0;
    let count = 0;
    artifacts.forEach(artifact => {
      const url = artifactURL(artifact, owner);
      if (!url) return;
      const link = document.createElement('a'); link.className = 'download-link'; link.href = url; link.download = artifact.name; link.textContent = artifact.name;
      target.append(link); count += 1;
    });
    return count;
  }
  function officialLink(value, corpus) {
    const allowed = taskSource(catalog && catalog.specification, corpus).documentation;
    if (typeof value !== 'string' || !Array.isArray(allowed) || !allowed.includes(value)) return null;
    let parsed;
    try { parsed = new URL(value); } catch (_) { return null; }
    const hosts = ['www.census.gov', 'www2.census.gov', 'transtats.bts.gov', 'ffiec.cfpb.gov', 'www.nyc.gov'];
    return parsed.protocol === 'https:' && hosts.includes(parsed.hostname) && !parsed.username && !parsed.password ? parsed.href : null;
  }
  function renderTasks(spec, sources) {
    const cards = byId('task-cards'), bindings = byId('source-bindings'); cards.replaceChildren(); bindings.replaceChildren();
    DOMAINS.forEach(corpus => {
      const item = taskSource(spec, corpus), live = Array.isArray(sources) ? sources.find(source => source.corpus === corpus) : null;
      const article = document.createElement('article'); article.className = 'task-card';
      const heading = document.createElement('h3'); heading.textContent = item.title || corpus.toUpperCase();
      const outcome = document.createElement('p'); outcome.className = 'task-outcome'; outcome.textContent = item.task || 'Required task unavailable';
      const period = document.createElement('p'); period.textContent = 'Historical panel: ' + printable(item.period);
      const covariates = document.createElement('p'); covariates.textContent = 'Public features: ' + (Array.isArray(item.features) ? item.features.join(', ') : 'unavailable');
      const state = document.createElement('p'); state.className = 'source-state';
      const ready = Boolean(live && live.available === true && live.status === 'ready');
      state.textContent = ready ? 'Pinned public source ready' : 'Source unavailable · ' + printable(live && live.reason || 'Required pinned source has not been verified');
      if (!ready) state.classList.add('warning');
      article.append(heading, outcome, period, covariates, state);
      if (Array.isArray(item.documentation)) item.documentation.forEach((value, index) => {
        const url = officialLink(value, corpus); if (!url) return;
        const link = document.createElement('a'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = index ? 'Data dictionary' : 'Official documentation'; article.append(link);
      });
      cards.append(article);
      addBinding(bindings, (item.title || corpus) + ' · data SHA-256', item.data_sha256);
      addBinding(bindings, 'Manifest SHA-256', item.manifest_sha256);
      addBinding(bindings, 'Public utility label', item.label_rule);
      addBinding(bindings, 'Public experimental retained bit', item.old_label);
    });
  }
  function renderSpecification(spec, sha) {
    put('specification-digest', 'Specification SHA-256: ' + printable(sha));
    put('specification-inspector', JSON.stringify(spec, null, 2));
    renderLinks(byId('specification-links'), [{name: 'benchmark-specification.json', url: API + '/specification'}], null);
  }
  function renderCatalog() {
    const valid = catalog && validSpec(catalog.specification) && digest(catalog.specification_sha256) && sourcesMatch(catalog.sources, catalog.specification);
    sourceReady = Boolean(valid && catalog.available === true && catalog.sources.every(source => source.available === true && source.status === 'ready'));
    put('source-badge', sourceReady ? 'Four pinned sources ready' : 'Execution blocked');
    put('source-status', sourceReady ? 'All four fixed historical public source matrices and manifests on D match their registered digests.' : 'One or more mandatory sources, numeric dependencies or specification bindings are unavailable or rejected. Execution is blocked; no domain is substituted or omitted.');
    byId('source-status').classList.toggle('warning', !sourceReady);
    put('stage-state-1', sourceReady ? 'Four domains ready' : 'Mandatory source unavailable');
    byId('stage-1').classList.toggle('done', sourceReady);
    if (catalog) { renderTasks(catalog.specification, catalog.sources); renderSpecification(catalog.specification, catalog.specification_sha256); }
    updateControls();
  }
  function renderSavedRuns() {
    const selected = run ? run.run_id : controls.saved.value;
    controls.saved.replaceChildren();
    const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = runs.length ? 'Select a saved benchmark…' : 'No saved benchmark registrations'; controls.saved.append(placeholder);
    runs.forEach(item => {
      if (!runId(item.run_id)) return;
      const option = document.createElement('option'); option.value = item.run_id;
      option.textContent = formatTime(item.registered_at) + ' · ' + item.run_id.slice(0, 8) + ' · ' + printable(item.status).replaceAll('_', ' ') + (item.result_status ? ' · ' + printable(item.result_status) : '');
      controls.saved.append(option);
    });
    if (runs.some(item => item.run_id === selected)) controls.saved.value = selected;
    updateControls();
  }
  async function refreshRuns() {
    const data = await request('/runs');
    if (!data || !Array.isArray(data.runs)) throw new Error('The saved benchmark list has an unexpected format.');
    runs = data.runs;
    const unavailable = Number.isSafeInteger(data.unavailable_run_count) && data.unavailable_run_count > 0 ? data.unavailable_run_count : 0;
    put('saved-run-status', unavailable ? unavailable + ' preserved registration(s) could not be validated. Keep their saved evidence for inspection.' : '');
    byId('saved-run-status').hidden = !unavailable; renderSavedRuns();
  }
  function badge(id, status, label) {
    const element = byId(id); element.className = 'tag ' + (['pass', 'fail', 'inconclusive'].includes(status) ? status : status === 'reserved_incomplete' ? 'blocked' : ''); element.textContent = label;
  }
  function row(target, values, classes = []) {
    const tr = document.createElement('tr');
    values.forEach((value, index) => { const td = document.createElement('td'); td.textContent = printable(value); if (classes[index]) td.className = classes[index]; tr.append(td); });
    target.append(tr); return tr;
  }
  function clearResults() {
    byId('results-panel').hidden = true;
    ['comparison-rows', 'reference-rows', 'variation-rows'].forEach(id => byId(id).replaceChildren());
    put('result-inspector', ''); put('benchmark-decision', 'Not evaluated'); put('decision-message', ''); put('integration-message', '');
  }
  function renderResults() {
    clearResults();
    if (run.status !== 'completed') return;
    if (!completeResult(run.result)) {
      put('evaluation-message', 'The saved result is missing one or more mandatory tasks, comparisons or finite scores. Re-execution is blocked; preserve the incomplete evidence.');
      badge('execution-status', 'reserved_incomplete', 'Incomplete result · blocked'); return;
    }
    const result = run.result; byId('results-panel').hidden = false;
    badge('result-status', result.status, LABELS[result.status]); put('benchmark-decision', LABELS[result.status]); put('operational-decision', 'Not evaluated');
    const decisions = result.task_results.flatMap(task => COMPARATORS.map(comparator => task.comparisons[comparator].status));
    const counts = ['pass', 'fail', 'inconclusive'].map(status => decisions.filter(value => value === status).length + ' ' + status).join(' · ');
    put('decision-message', 'All eight mandatory comparisons are retained: ' + counts + '. ' + (result.status === 'pass' ? 'All lower gain bounds reach the fixed provisional margin.' : result.status === 'fail' ? 'At least one upper gain bound is below the fixed provisional margin.' : 'At least one gain interval overlaps the margin and no mandatory comparison establishes failure.') + ' This public research decision grants no release authority.');
    byId('decision-message').className = 'result-explanation ' + result.status;
    const uncertainty = result.uncertainty || {};
    put('integration-message', 'Fixed integration: ' + printable(uncertainty.repetitions || run.specification.repetitions) + ' paired repetitions per task; ' + printable(uncertainty.family_size || 8) + ' simultaneous gain intervals; α = ' + printable(uncertainty.alpha ?? 0.05) + '; common radius ' + number(uncertainty.radius) + '. ' + printable(uncertainty.interpretation || run.specification.uncertainty.interpretation));
    result.task_results.forEach(task => {
      COMPARATORS.forEach((comparator, index) => {
        const comparison = task.comparisons[comparator];
        const tr = row(byId('comparison-rows'), [task.title || taskTitle(run.specification, task.task_id), ROUTE_NAMES[comparator], number(task.expected_brier.certified_continuation) + ' / ' + number(task.expected_brier[comparator]), number(comparison.gain), '[' + number(comparison.lower) + ', ' + number(comparison.upper) + ']', number(comparison.margin), LABELS[comparison.status]], ['', '', 'numeric', 'numeric', 'numeric', 'numeric', 'criterion ' + comparison.status]);
        if (index === 0) tr.classList.add('task-start');
      });
      row(byId('reference-rows'), [task.title || taskTitle(run.specification, task.task_id), ...ROUTES.map(route => number(task.reference_brier[route]))], ['', 'numeric', 'numeric', 'numeric']);
      ['independent_rr', 'certified_continuation'].forEach(route => {
        const quantiles = task.predictive_loss_quantiles && task.predictive_loss_quantiles[route] || {};
        row(byId('variation-rows'), [task.title || taskTitle(run.specification, task.task_id), ROUTE_NAMES[route], number(quantiles.p025), number(quantiles.p975)], ['', '', 'numeric', 'numeric']);
      });
    });
    put('result-inspector', JSON.stringify(result, null, 2));
  }
  function renderRun() {
    byId('run-detail').hidden = !run;
    clearResults();
    if (!run) { updateControls(); return; }
    put('run-label', 'Registration ' + printable(run.run_id));
    const valid = registered(), completed = run.status === 'completed', blocked = run.status === 'reserved_incomplete' || uncertain || !valid || !specMatches();
    badge('execution-status', blocked ? 'reserved_incomplete' : run.status, blocked ? 'Execution blocked' : completed ? 'Completed · saved bytes' : 'Registered');
    const bindings = byId('registration-bindings'); bindings.replaceChildren();
    addBinding(bindings, 'Registered before evaluation', formatTime(run.registered_at));
    addBinding(bindings, 'Experiment identity', run.run_id); addBinding(bindings, 'Specification SHA-256', run.specification_sha256);
    addBinding(bindings, 'Data scope', 'Historical fixed public rows on D; all source labels already public');
    addBinding(bindings, 'Operational usefulness / authority', 'Not evaluated / none');
    const certs = byId('certificate-rows'); certs.replaceChildren();
    DOMAINS.forEach(corpus => {
      const certificate = Array.isArray(run.certificates) ? run.certificates.find(item => item.corpus === corpus) : null;
      const parameters = certificate && certificate.parameters;
      row(certs, [taskTitle(run.specification, corpus), certificate ? printable(certificate.status) : 'Awaiting fixed evaluation', parameters ? 'r=' + printable(parameters.r) + ', d=' + printable(parameters.d) + ', L=' + printable(parameters.L) + ', τ=' + printable(parameters.tau) : 'r=1, d=3, L=9, τ=2/3', certificate && certificate.marginal_accuracy]);
    });
    put('registration-message', 'Open registration ' + printable(run.run_id) + ' · ' + formatTime(run.registered_at) + '. Its frozen rules remain unchanged.');
    put('stage-state-2', valid ? 'Registered before evaluation' : 'Registration invalid');
    put('stage-state-3', blocked ? 'Blocked · preserve evidence' : completed ? 'Fixed evaluation completed' : 'Ready for fixed evaluation');
    put('stage-state-4', completed && completeResult(run.result) ? 'Eight comparisons saved' : blocked ? 'Saved reservation preserved' : 'Awaiting evaluation');
    byId('stage-2').classList.toggle('done', valid); byId('stage-3').classList.toggle('done', completed && !blocked); byId('stage-3').classList.toggle('current', !completed && !blocked); byId('stage-4').classList.toggle('done', completed && completeResult(run.result));
    const message = uncertain ? 'The previous request outcome could not be confirmed. Execution remains blocked until the saved registration is reopened successfully.' : !valid || !specMatches() ? 'The saved registration does not match the complete four-domain frozen specification. Preserve its evidence; evaluation is blocked.' : run.status === 'reserved_incomplete' ? 'An incomplete evaluation reservation is preserved. New evaluation and replacement repetitions are blocked across requests and restarts.' : completed ? 'The completed result is retained. Reopen saved results returns the same saved artifacts under the frozen experiment. Verification can replay that fixed computation; it does not create a new study.' : 'The fixed prospective registration is ready. Run all four tasks and eight comparisons; no result is required to be favorable.';
    put('evaluation-message', message); put('pipeline-message', message);
    renderTasks(run.specification, run.sources); renderSpecification(run.specification, run.specification_sha256);
    const links = renderLinks(byId('artifact-links'), run.artifacts, run.run_id);
    put('artifact-status', links ? links + ' validated same-origin artifact link(s). Downloads recheck retained bytes on the server.' : 'No validated saved artifact links are available. Preserve the registration for inspection.');
    renderResults(); updateControls();
  }
  function adopt(detail) {
    if (!detail || !runId(detail.run_id) || !['registered', 'reserved_incomplete', 'completed'].includes(detail.status)) throw new Error('The service returned an unexpected registration. Refresh the saved list before continuing.');
    run = detail; uncertain = false; renderRun();
    if (window.history && typeof window.history.replaceState === 'function') window.history.replaceState(null, '', '#run=' + run.run_id);
  }
  async function openRun(id) { if (!runId(id)) throw new Error('Choose a valid saved registration.'); adopt(await request('/runs/' + id)); }
  async function refresh() {
    sourceReady = false; updateControls();
    catalog = await request('/catalog'); renderCatalog(); await refreshRuns();
    if (run) { try { await openRun(run.run_id); } catch (error) { uncertain = true; renderRun(); throw error; } }
  }
  controls.register.addEventListener('click', () => perform('register', async () => {
    if (!sourceReady || uncertain || run && run.status === 'reserved_incomplete') return;
    put('pipeline-message', 'Saving the fixed prospective registration before evaluation.');
    try { adopt(await request('/runs', {method: 'POST', body: '{}'})); }
    catch (error) { uncertain = true; put('pipeline-message', 'Registration outcome is unconfirmed. Refresh the saved list; do not attempt a replacement experiment.'); throw error; }
    await refreshRuns(); byId('evaluation-title').focus();
  }));
  controls.open.addEventListener('click', () => perform('open', async () => { await openRun(controls.saved.value); byId('evaluation-title').focus(); }));
  controls.saved.addEventListener('change', updateControls);
  controls.refresh.addEventListener('click', () => perform('refresh', refresh));
  controls.evaluate.addEventListener('click', () => perform('evaluate', async () => {
    if (!evaluationReady()) return;
    const id = run.run_id;
    put('evaluation-message', run.status === 'completed' ? 'Validating and reopening the exact saved results. This may replay the same frozen computation.' : 'Running the fixed four-task benchmark. The evaluation is reserved; keep this page open while all 4,096 repetitions per task finish.');
    put('pipeline-message', 'The registered evaluation is in progress. Controls are paused to prevent duplicate requests.');
    try { adopt(await request('/runs/' + id + '/evaluate', {method: 'POST', body: '{}'})); }
    catch (error) {
      uncertain = true;
      try { adopt(await request('/runs/' + id)); } catch (_) { uncertain = true; renderRun(); }
      throw error;
    }
    await refreshRuns();
    if (!byId('results-panel').hidden) byId('results-title').focus();
  }));
  perform('initialize', async () => {
    await refresh();
    const match = /^#run=([0-9a-f]{32})$/.exec(window.location.hash || '');
    if (match) await openRun(match[1]);
  });
})();