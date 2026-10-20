/* The research page deliberately uses only same-origin, registered public runs. */
(() => {
  'use strict';

  const API = '/api/research-rr';
  const byId = (id) => document.getElementById(id);
  const controls = {
    preset: byId('preset'), create: byId('create-run'), saved: byId('saved-run'),
    open: byId('open-run'), reload: byId('reload-runs'), editor: byId('certificate'),
    verify: byId('verify-certificate'), tamper: byId('tamper-certificate'),
    restore: byId('restore-certificate'), sample: byId('sample-block'),
    evaluate: byId('evaluate-usefulness'), saveReport: byId('save-usefulness-report'),
    alias: byId('alias-run'), inspectHistory: byId('inspect-history')
  };
  let presets = [];
  let runs = [];
  let run = null;
  let busy = false;
  let catalogLoaded = false;
  let sourceReady = false;
  let editorAccepted = false;
  let lastAttempt = null;

  const put = (id, value) => { byId(id).textContent = value; };
  const printable = (value) => {
    if (value === null || value === undefined) return '\u2014';
    if (typeof value === 'boolean') return value ? 'Declared true' : 'Declared false';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  };
  const vector = (value) => Array.isArray(value) ? '[' + value.join(', ') + ']' : printable(value);
  const originalEditor = () => run && controls.editor.value === run.certificate_text;
  const samplingStatus = () => run && run.sampling ? run.sampling.status : 'blocked_verification';
  const sharedHistory = () => run && run.shared_history ? run.shared_history : {};
  const historyState = () => sharedHistory().state || sharedHistory().status || 'legacy_history_unregistered';
  const currentHistorySnapshot = () => sharedHistory().registered === true &&
    Number.isSafeInteger(sharedHistory().revision) && sharedHistory().revision >= 0 &&
    /^[0-9a-f]{64}$/.test(sharedHistory().head_sha256 || '');
  const sharedSamplingReady = () => currentHistorySnapshot() &&
    ((samplingStatus() === 'ready' && historyState() === 'ready') ||
     (samplingStatus() === 'completed' && historyState() === 'committed'));
  const canonicalExperimentRun = () => {
    const value = usefulness();
    return value.alias_uses_canonical_experiment === true && sharedHistory().registered === true &&
      /^[0-9a-f]{32}$/.test(value.source_run_id || '') && value.source_run_id === sharedHistory().canonical_run_id
      ? value.source_run_id : run.run_id;
  };
  const receiptVerified = () => Boolean(run && run.verification && run.verification.status === 'verified');
  const certificateReady = () => receiptVerified() && originalEditor() && editorAccepted;
  const usefulness = () => run && run.usefulness ? run.usefulness : {};
  const prospectiveSpec = () => usefulness().registered === true && usefulness().specification &&
    /^[0-9a-f]{64}$/.test(usefulness().specification_sha256 || '') && /^[0-9a-f]{64}$/.test(usefulness().dataset_sha256 || '');
  const usefulnessStatus = () => usefulness().status || 'not_evaluated';
  const boundaryPreset = () => run && (run.preset === 'uniform' || run.preset === 'infeasible');
  const evaluationReady = () => Boolean(run && sourceReady && certificateReady() && currentHistorySnapshot() && historyState() === 'committed' && prospectiveSpec() &&
    !boundaryPreset() && samplingStatus() === 'completed' && ['ready', 'completed'].includes(usefulnessStatus()));
  const notEvaluatedReportReady = () => Boolean(run && sourceReady && certificateReady() && currentHistorySnapshot() && ['ready', 'committed'].includes(historyState()) && prospectiveSpec() &&
    boundaryPreset() && ['ready', 'infeasible', 'completed'].includes(samplingStatus()) &&
    ['not_evaluated', 'completed'].includes(usefulnessStatus()));
  const presetFor = (id) => presets.find((item) => item.id === id);
  const presetTitle = (id) => {
    const item = presetFor(id);
    return item ? item.title : printable(id);
  };
  const displayTime = (value) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? printable(value) : date.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  };

  function connected(online) {
    byId('connection').classList.toggle('online', online);
    put('connection-label', online ? 'Local research API' : 'Connection unavailable');
  }

  function showError(message) {
    put('error', message);
    byId('error').hidden = !message;
  }

  async function request(path, options = {}) {
    let response;
    try {
      response = await fetch(API + path, {
        credentials: 'same-origin', cache: 'no-store', ...options,
        headers: {Accept: 'application/json', ...(options.body ? {'Content-Type': 'application/json'} : {}), ...(options.headers || {})}
      });
    } catch (_) {
      connected(false);
      throw new Error('The local research service could not be reached. Start the local demo, then refresh this page.');
    }
    let body;
    try { body = await response.json(); } catch (_) {
      throw new Error('The local service returned an unreadable response. Refresh before continuing.');
    }
    connected(true);
    if (!response.ok) {
      const detail = typeof body.detail === 'string' ? body.detail : typeof body.error === 'string' ? body.error : null;
      const error = new Error(detail || ('The request was refused (HTTP ' + response.status + ').'));
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function updateControls() {
    controls.preset.disabled = busy || !catalogLoaded;
    controls.create.disabled = busy || !catalogLoaded || !sourceReady || !controls.preset.value;
    controls.saved.disabled = busy || !runs.length;
    controls.open.disabled = busy || !controls.saved.value;
    controls.reload.disabled = busy;
    controls.editor.disabled = busy || !run;
    controls.verify.disabled = busy || !sourceReady || !run || !controls.editor.value.trim();
    controls.tamper.disabled = busy || !run;
    controls.restore.disabled = busy || !run;
    controls.sample.disabled = busy || !sourceReady || !certificateReady() || !sharedSamplingReady();
    controls.sample.textContent = samplingStatus() === 'completed' && currentHistorySnapshot() && historyState() === 'committed'
      ? 'Redeliver saved block' : 'Draw conditional block once';
    controls.alias.disabled = busy || !sourceReady || !run || !currentHistorySnapshot() || !['ready', 'committed'].includes(historyState());
    controls.inspectHistory.disabled = busy || !run;
    controls.evaluate.disabled = busy || !evaluationReady();
    controls.saveReport.disabled = busy || !notEvaluatedReportReady();
    controls.saveReport.hidden = !boundaryPreset();
    controls.evaluate.hidden = Boolean(boundaryPreset());
    controls.evaluate.textContent = usefulnessStatus() === 'completed' ? 'Reopen saved evaluation' : 'Fit and evaluate saved block';
    controls.saveReport.textContent = usefulnessStatus() === 'completed' ? 'Reopen not-evaluated report' : 'Save not-evaluated report';
    byId('setup-panel').setAttribute('aria-busy', busy ? 'true' : 'false');
    byId('run-detail').setAttribute('aria-busy', busy ? 'true' : 'false');
    byId('create-run').textContent = busy ? 'Working\u2026' : 'Create public run';
  }

  async function perform(action) {
    if (busy) return;
    busy = true;
    showError('');
    updateControls();
    try { await action(); } catch (error) { showError(error.message || 'The research request failed.'); }
    finally { busy = false; updateControls(); }
  }

  function renderSavedRuns() {
    const selected = controls.saved.value || (run ? run.run_id : '');
    controls.saved.replaceChildren();
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = runs.length ? 'Select a saved run\u2026' : 'No saved research runs yet';
    controls.saved.append(empty);
    runs.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.run_id;
      const state = item.sampling ? item.sampling.status.replaceAll('_', ' ') : 'saved';
      option.textContent = presetTitle(item.preset) + ' \u00b7 ' + displayTime(item.created_at) + ' \u00b7 ' + item.run_id.slice(0, 8) + ' \u00b7 ' + state;
      controls.saved.append(option);
    });
    if (runs.some((item) => item.run_id === selected)) controls.saved.value = selected;
    updateControls();
  }

  async function refreshRuns() {
    const result = await request('/runs');
    if (!result || !Array.isArray(result.runs)) throw new Error('The saved-run list has an unexpected format.');
    runs = result.runs;
    const unavailable = Number.isSafeInteger(result.unavailable_run_count) && result.unavailable_run_count > 0 ? result.unavailable_run_count : 0;
    put('saved-run-status', unavailable ? unavailable + ' preserved research run' + (unavailable === 1 ? ' is' : 's are') + ' unavailable because the registered source or saved bindings could not be verified. Preserve the saved files for inspection.' : '');
    byId('saved-run-status').hidden = !unavailable;
    renderSavedRuns();
  }

  function updatePresetDescription() {
    const item = presetFor(controls.preset.value);
    put('preset-description', item ? item.description : 'Choose a public experiment.');
    updateControls();
  }

  function renderBindings() {
    const list = byId('context-bindings');
    list.replaceChildren();
    const labels = {
      source_pdf_sha256: 'Reviewed source PDF \u00b7 SHA-256',
      retained_law_sha256: 'Retained RR law \u00b7 SHA-256',
      retained_response_sha256: 'Actual retained responses \u00b7 SHA-256',
      complete_history_sha256: 'Declared complete retained history \u00b7 SHA-256',
      request_plan_sha256: 'Fixed public request plan \u00b7 SHA-256',
      full_binary_cube: 'Full binary cube', full_vector_replacement: 'Full-vector replacement adjacency',
      preexisting_labels: 'Preexisting binary labels',
      public_fixed_features_membership_linkage: 'Public fixed features, membership and linkage',
      public_fixed_requests: 'Public fixed requests',
      certificate_sha256: 'Verified saved certificate \u00b7 SHA-256',
      verified_at: 'Saved original verification time'
    };
    const bindings = {...(run.context || {})};
    if (receiptVerified()) {
      bindings.certificate_sha256 = run.verification.certificate_sha256;
      if (run.verification.verified_at) bindings.verified_at = displayTime(run.verification.verified_at);
    }
    Object.entries(bindings).forEach(([key, value]) => {
      const term = document.createElement('dt');
      term.textContent = labels[key] || key.replaceAll('_', ' ');
      const definition = document.createElement('dd');
      definition.textContent = printable(value);
      if (key.endsWith('_sha256')) definition.classList.add('digest');
      list.append(term, definition);
    });
  }

  function renderSharedHistory() {
    const value = sharedHistory(), status = historyState();
    const labels = {initialization_reserved: 'History initialization incomplete', initializing: 'History initialization incomplete', ready: 'Ready for one continuation', reserved: 'Reserved · incomplete', reserved_incomplete: 'Reserved · incomplete', committed: 'Committed · redelivery only', integrity_error: 'History integrity error', legacy_history_unregistered: 'Historical evidence · unregistered'};
    put('history-state', labels[status] || 'History unavailable');
    byId('history-state').className = 'tag ' + (status === 'committed' ? 'success' : status === 'integrity_error' ? 'failure' : ['reserved', 'reserved_incomplete', 'initializing', 'initialization_reserved'].includes(status) ? 'inconclusive' : '');
    put('history-id', value.history_id || 'No Phase 3 registration');
    put('history-revision', printable(value.revision));
    put('history-law', value.supported_law || 'One retained RR + one certified continuation');
    const messages = {
      initialization_reserved: 'History registration did not complete. Preserve its evidence; new draws and aliases stay blocked.',
      initializing: 'History registration did not complete. Preserve its evidence; new draws and aliases stay blocked.',
      ready: 'This registered synthetic cohort may receive one certified continuation. Every run alias shares this limit.',
      reserved: 'The shared history has an incomplete reservation. Every alias stays blocked across processes and restarts; no replacement draw is allowed.',
      reserved_incomplete: 'The shared history has an incomplete reservation. Every alias stays blocked across processes and restarts; no replacement draw is allowed.',
      committed: 'One continuation is committed for this shared history. Repeated requests and aliases redeliver the exact saved block; another informative draw is refused.',
      integrity_error: 'Shared history or custody evidence could not be verified. Draws, aliases and unverified history downloads stay blocked; preserve the files.',
      legacy_history_unregistered: 'This preserved historical run has no prospective Phase 3 shared-history registration. Existing evidence remains readable; it cannot gain a new reservation or alias by restamping.'
    };
    put('history-message', (messages[status] || 'Shared history is unavailable for this run.') + (value.reason ? ' ' + printable(value.reason) : ''));
    const bindings = byId('history-bindings'); bindings.replaceChildren();
    appendDefinition(bindings, 'History head SHA-256', value.head_sha256, true);
    appendDefinition(bindings, 'Canonical source run', value.canonical_run_id);
    appendDefinition(bindings, 'Whole-history privacy cap', value.whole_history_cap || 'Declared complete-law cap; no additive epsilon subtraction');
    appendDefinition(bindings, 'Local custody authority', value.custody || value.authority || 'Fictional fixture; independent agency service pending');
    appendDefinition(bindings, 'Release authorization effect', 'none');
    put('history-inspector', 'Select Inspect shared history to read the current saved state, events and reservation.');
    const artifacts = byId('history-artifact-links'); artifacts.replaceChildren();
    (Array.isArray(value.artifacts) ? value.artifacts : []).forEach((artifact) => {
      if (!artifact || !['shared-history.json', 'history-registration.json'].includes(artifact.name) || typeof artifact.url !== 'string') return;
      const expectedPath = API + '/runs/' + run.run_id + '/history/artifacts/' + artifact.name;
      let url; try { url = new URL(artifact.url, window.location.origin); } catch (_) { return; }
      if (url.origin !== window.location.origin || url.pathname !== expectedPath || url.search || url.hash) return;
      const link = document.createElement('a'); link.className = 'download-link';
      link.href = expectedPath; link.download = artifact.name; link.textContent = artifact.name; artifacts.append(link);
    });
  }

  function renderRecords() {
    const rows = byId('records');
    rows.replaceChildren();
    (run.records || []).forEach((record) => {
      const row = document.createElement('tr');
      [record.record_id, vector(record.labels), printable(record.w), Array.isArray(record.sampled_labels) ? vector(record.sampled_labels) : 'Not drawn'].forEach((value, index) => {
        const cell = document.createElement(index === 0 ? 'th' : 'td');
        if (index === 0) cell.scope = 'row';
        cell.textContent = value;
        row.append(cell);
      });
      rows.append(row);
    });
  }

  function renderArtifacts() {
    const container = byId('artifact-links');
    container.replaceChildren();
    let count = 0;
    const pathPrefix = API + '/runs/' + run.run_id + '/artifacts/';
    const owner = sharedHistory().canonical_run_id;
    const ownerPrefix = currentHistorySnapshot() && /^[0-9a-f]{32}$/.test(owner || '')
      ? API + '/runs/' + owner + '/artifacts/' : null;
    const names = ['synthetic-labels.json', 'retained-law.json', 'retained-responses.json', 'history.json', 'request-plan.json', 'plan.json', 'certificate.json', 'verification.json', 'randomized-block.json', 'sampling-completion.json'];
    (run.artifacts || []).forEach((artifact) => {
      if (!artifact || typeof artifact.name !== 'string' || typeof artifact.url !== 'string') return;
      let url;
      try { url = new URL(artifact.url, window.location.origin); } catch (_) { return; }
      const ownPath = pathPrefix + artifact.name;
      const ownerPath = ownerPrefix && ['randomized-block.json', 'sampling-completion.json'].includes(artifact.name) ? ownerPrefix + artifact.name : null;
      if (!names.includes(artifact.name) || url.origin !== window.location.origin || (url.pathname !== ownPath && url.pathname !== ownerPath) || url.search || url.hash) return;
      const link = document.createElement('a');
      link.className = 'download-link';
      link.href = url.pathname;
      link.textContent = artifact.name;
      link.download = artifact.name;
      container.append(link);
      count += 1;
    });
    put('artifact-status', count ? count + ' saved artifact' + (count === 1 ? '' : 's') + ' available for this run.' : 'No downloadable artifacts are currently available.');
  }

  const routeNames = {public_only: 'Public-only learning', independent_rr: 'Matched independent RR', certified_continuation: 'Certified continuation'};
  const decisions = {pass: 'Pass', fail: 'Fail', inconclusive: 'Inconclusive', not_evaluated: 'Not evaluated'};
  const taskName = (task) => 'Fresh coordinate X' + (task.label_coordinate === 1 || task.label_coordinate === 2 ? task.label_coordinate : printable(task.task_id));
  const rational = (value) => typeof value === 'string' && /^-?\d+\/[1-9]\d*$/.test(value) ? value : '\u2014';
  function appendDefinition(list, label, value, digest = false) {
    const term = document.createElement('dt'); term.textContent = label;
    const definition = document.createElement('dd'); definition.textContent = printable(value);
    if (digest) definition.className = 'digest';
    list.append(term, definition);
  }
  function appendMetricRow(list, values, outcome) {
    const row = document.createElement('tr');
    values.forEach((value, index) => {
      const cell = document.createElement(index === 0 ? 'th' : 'td');
      if (index === 0) cell.scope = 'row';
      cell.textContent = printable(value);
      if (index >= 2) cell.className = 'metric-cell';
      if (outcome && index === values.length - 1) cell.className = 'result-' + outcome;
      row.append(cell);
    });
    list.append(row);
  }
  function renderUsefulnessArtifacts() {
    const container = byId('usefulness-artifact-links'); container.replaceChildren();
    const value = usefulness();
    const names = ['evaluation.json', 'models.json', 'predictions.json', 'independent-block.json', 'simulation-diagnostics.json', 'reproducibility.json', 'evaluation.txt'];
    const evaluationId = value.evaluation_id;
    const sourceRunId = canonicalExperimentRun();
    let count = 0;
    if (value.status === 'completed' && typeof evaluationId === 'string' && /^[0-9a-f]{64}$/.test(evaluationId)) {
      (Array.isArray(value.artifacts) ? value.artifacts : []).forEach((artifact) => {
        if (!artifact || !names.includes(artifact.name) || typeof artifact.url !== 'string') return;
        const expectedPath = API + '/runs/' + sourceRunId + '/evaluations/' + evaluationId + '/artifacts/' + artifact.name;
        let url; try { url = new URL(artifact.url, window.location.origin); } catch (_) { return; }
        if (url.origin !== window.location.origin || url.pathname !== expectedPath || url.search || url.hash) return;
        const link = document.createElement('a'); link.className = 'download-link';
        link.href = expectedPath; link.download = artifact.name; link.textContent = artifact.name;
        container.append(link); count += 1;
      });
    }
    put('usefulness-artifact-status', count ? count + ' intact completed evaluation artifacts available. Downloads recheck the saved lineage.' : 'Evaluation artifacts appear only after an intact completed evaluation.');
  }
  function renderUsefulness() {
    if (!run) return;
    const value = usefulness();
    const status = usefulnessStatus();
    const result = value.status === 'completed' && value.result && typeof value.result === 'object' ? value.result : null;
    const decision = result && Object.hasOwn(decisions, result.status) ? result.status : null;
    const badge = byId('usefulness-status');
    badge.textContent = decision ? decisions[decision] : status === 'ready' ? 'Ready to evaluate' : status === 'reserved_incomplete' ? 'Incomplete reservation' : status === 'integrity_error' ? 'Integrity error' : 'Not evaluated';
    badge.className = 'tag ' + (decision === 'pass' ? 'success' : decision === 'fail' || status === 'integrity_error' ? 'failure' : decision === 'inconclusive' || status === 'reserved_incomplete' ? 'inconclusive' : '');
    put('usefulness-registration', prospectiveSpec()
      ? (canonicalExperimentRun() !== run.run_id
        ? 'This alias reuses the canonical source run’s specification registered before retained responses and the conditional draw. It creates no new prospective experiment or randomized block.'
        : 'This run registered its specification and public feature fixture before retained responses and the conditional draw. Criteria cannot be edited.')
      : 'This run lacks prospective Phase 2 registration. Its existing evidence remains readable; create a fresh public run to evaluate usefulness.');
    put('usefulness-specification', value.specification ? JSON.stringify(value.specification, null, 2) : 'No prospective Phase 2 specification is registered for this historical run.');
    const digests = byId('usefulness-specification-digests'); digests.replaceChildren();
    [['Specification SHA-256', value.specification_sha256], ['Public feature fixture SHA-256', value.dataset_sha256]].forEach(([label, digest]) => {
      if (typeof digest !== 'string' || !/^[0-9a-f]{64}$/.test(digest)) return;
      const node = document.createElement('p'); node.textContent = label + ': ' + digest; digests.append(node);
    });
    const messages = {
      waiting_verification: 'Verify the registered original certificate before this public experiment can proceed.',
      waiting_block: 'Save the single conditional block first. Fitting will reuse it without another draw.',
      ready: 'Ready to fit the committed block and evaluate both tasks under the immutable specification.',
      reserved_incomplete: 'An evaluation reservation did not complete. This run stays blocked across restarts; preserve its evidence. No replacement block or result is generated.',
      completed: 'The saved evaluation is complete. Reopening reuses the same result and committed block; it never draws again.',
      integrity_error: 'Evaluation evidence or lineage could not be verified. Results and downloads are blocked; preserve the files for inspection.',
      not_evaluated: boundaryPreset() ? (run.preset === 'uniform' ? 'Not evaluated: the fixed unbiased decoder is singular at p = 1/2. Uniform sampling is a separate channel demonstration.' : 'Not evaluated: the verified infeasibility claim supplies no qualifying conditional channel. Certified fitting is unavailable.') : 'Not evaluated: create a fresh public run with prospective Phase 2 registration.'
    };
    let message = messages[status] || 'Evaluation is unavailable for this run.';
    if (boundaryPreset() && samplingStatus() === 'reserved_incomplete') {
      message = 'Not evaluated: this run has an incomplete conditional draw reservation. Preserve its evidence; new report requests stay blocked across restarts.';
    } else if (boundaryPreset() && receiptVerified() && !['ready', 'infeasible', 'completed'].includes(samplingStatus())) {
      message = 'Not evaluated: the conditional block state could not be verified. New report requests are blocked; preserve the evidence for inspection.';
    }
    if (value.reason) message += ' ' + printable(value.reason);
    if (prospectiveSpec() && sourceReady && receiptVerified() && !certificateReady()) message += ' Restore and verify the original editor candidate before any new evaluation or report request.';
    if (!sourceReady) message = 'The registered research source could not be verified. New evaluations and report requests are blocked. Preserve the existing evidence and refresh after restoring the reviewed bytes.';
    put('usefulness-message', message);
    byId('usefulness-results').hidden = !result;
    ['usefulness-comparisons', 'usefulness-realized', 'usefulness-variation', 'usefulness-lineage'].forEach((id) => byId(id).replaceChildren());
    if (result) {
      put('usefulness-decision', decision ? decisions[decision] : 'Unavailable');
      put('usefulness-operational', 'Not evaluated');
      const notes = {
        pass: 'Both mandatory tasks meet the illustrative expected Brier margin against both predetermined comparators on this exact fixed benchmark. Operational usefulness and release authorization remain unestablished.',
        fail: 'At least one mandatory expected-gain comparison fails the frozen 1/100 margin. A favorable realized model score cannot change this result.',
        inconclusive: 'The required benchmark evidence does not establish all mandatory comparisons. This result provides no admission or release authority.',
        not_evaluated: 'No eligible certified evaluation exists under this declared specification. No usefulness success is claimed.'
      };
      put('usefulness-decision-note', (notes[decision] || 'The saved result has an unsupported decision format; no success is claimed.') + (result.reason ? ' ' + printable(result.reason) : ''));
      (Array.isArray(result.task_results) ? result.task_results : []).forEach((task) => {
        const name = taskName(task);
        const expected = task.expected_brier || {};
        const comparisons = task.comparisons || {};
        const realized = task.realized_brier || {};
        if (!task.expected_brier) {
          appendMetricRow(byId('usefulness-comparisons'), [name, 'Certified continuation', '\u2014', '\u2014', 'Not evaluated'], 'not_evaluated');
        } else {
          appendMetricRow(byId('usefulness-comparisons'), [name, routeNames.certified_continuation, rational(expected.certified_continuation), '\u2014', 'Task: ' + (decisions[task.status] || 'Unavailable')], Object.hasOwn(decisions, task.status) ? task.status : 'not_evaluated');
          ['public_only', 'independent_rr'].forEach((route) => {
            const comparison = comparisons[route] || {};
            appendMetricRow(byId('usefulness-comparisons'), [name, routeNames[route], rational(expected[route]), rational(comparison.gain), (decisions[comparison.status] || 'Unavailable') + ' · margin ' + rational(comparison.margin)], Object.hasOwn(decisions, comparison.status) ? comparison.status : 'not_evaluated');
          });
        }
        appendMetricRow(byId('usefulness-realized'), [name, rational(realized.public_only), rational(realized.independent_rr), rational(realized.certified_continuation)]);
        const diagnostics = value.diagnostics && value.diagnostics.routes ? value.diagnostics.routes : {};
        ['independent_rr', 'certified_continuation'].forEach((route) => {
          const quantiles = task.predictive_loss_quantiles && task.predictive_loss_quantiles[route] || {};
          const diagnostic = diagnostics[route] || {};
          const summary = (Array.isArray(diagnostic.task_summaries) ? diagnostic.task_summaries : []).find((item) => item.task_id === task.task_id) || {};
          appendMetricRow(byId('usefulness-variation'), [name, routeNames[route], rational(quantiles.q025) + ' / ' + rational(quantiles.q975), diagnostic.repetitions === 128 ? rational(summary.mean_brier) : '\u2014']);
        });
      });
      const exact = result.exact_integration || {};
      put('usefulness-diagnostics-note', exact.outcomes_per_randomized_route === 256
        ? 'Exact integration: 256 possible training blocks per randomized law. Total law probability: ' + printable(exact.total_probability) + '. Monte Carlo integration error: ' + rational(exact.monte_carlo_error) + '. The 128 seeded diagnostics do not determine the result.'
        : 'No complete exact integration is reported for this result. No diagnostic simulation can substitute for the required expected-law criterion.');
      const lineage = byId('usefulness-lineage');
      appendDefinition(lineage, 'Source run', canonicalExperimentRun());
      if (canonicalExperimentRun() !== run.run_id) appendDefinition(lineage, 'Displayed alias', run.run_id);
      appendDefinition(lineage, 'Evaluation identity', value.evaluation_id, true);
      appendDefinition(lineage, 'Frozen specification SHA-256', value.specification_sha256, true);
      appendDefinition(lineage, 'Public fixture SHA-256', value.dataset_sha256, true);
      Object.entries(result.lineage || {}).forEach(([key, item]) => appendDefinition(lineage, key.replaceAll('_', ' '), item, key.endsWith('sha256')));
      appendDefinition(lineage, 'Authorization effect', 'none');
      appendDefinition(lineage, 'Production execution qualified', 'false');
    }
    renderUsefulnessArtifacts();
  }

  function setStage(number, state, label) {
    byId('stage-' + number).className = state;
    put('stage-state-' + number, label);
  }

  function renderProgress() {
    setStage(1, 'complete', 'Public run saved');
    setStage(2, 'complete', 'Registered inputs saved');
    const verified = receiptVerified();
    const status = samplingStatus();
    setStage(3, verified ? 'complete' : 'current', verified ? 'Saved certificate verified' : 'Verification required');
    const states = {
      blocked_verification: ['pending', 'Awaiting valid certificate'],
      ready: ['current', 'Ready for one block'],
      infeasible: ['blocked', 'Infeasible \u00b7 no draw'],
      completed: ['complete', 'Block saved \u00b7 redelivery only'],
      reserved_incomplete: ['blocked', 'Incomplete reservation \u00b7 blocked'],
      legacy_history_unregistered: ['blocked', 'Historical evidence \u00b7 new draw blocked'],
      integrity_error: ['blocked', 'History integrity error \u00b7 blocked']
    };
    const stage = states[status] || ['blocked', 'Sampling unavailable'];
    setStage(4, stage[0], stage[1]);
    const messages = {
      blocked_verification: 'Run created. Inspect its registered inputs, then verify the saved certificate.',
      ready: 'The saved original certificate is verified. Reserve this shared history and draw its one conditional block.',
      infeasible: 'The infeasibility claim is verified. No conditional channel meets this floor, so sampling is unavailable.',
      completed: 'One complete conditional block is saved. Reopening this run displays the same block.',
      reserved_incomplete: 'A draw reserved this shared history but did not finish. Preserve its evidence; every alias stays blocked.',
      legacy_history_unregistered: 'Preserved historical evidence has no prospective shared-history registration. New draws stay blocked.',
      integrity_error: 'Shared history integrity could not be verified. Preserve the evidence; execution stays blocked.'
    };
    put('pipeline-message', messages[status] || 'Inspect this run and its saved evidence.');
  }

  function conditionalText(value) {
    if (Array.isArray(value)) return value.map(printable).join(' / ');
    if (value && typeof value === 'object') {
      const correct = value.old_response_correct ?? value.retained_correct ?? value.correct;
      const wrong = value.old_response_wrong ?? value.retained_wrong ?? value.wrong;
      return correct !== undefined && wrong !== undefined ? printable(correct) + ' / ' + printable(wrong) : printable(value);
    }
    return printable(value);
  }

  function renderResult() {
    const verification = run.verification || {};
    const verified = receiptVerified();
    const claim = verified ? verification.claim : null;
    put('claim', claim ? claim.charAt(0).toUpperCase() + claim.slice(1) : 'Awaiting check');
    put('claim-note', claim === 'infeasible' ? 'No qualifying channel' : verified ? 'Registered certificate accepted' : 'Verify before sampling');
    put('floor', printable(run.parameters && run.parameters.tau));
    put('marginal', verified ? printable(verification.marginal_label_correctness) : '\u2014');
    put('conditional', verified ? conditionalText(verification.conditional_label_correctness) : '\u2014');
    put('verification-badge', verified ? 'Saved certificate verified' : 'Not yet verified');
    byId('verification-badge').className = 'tag ' + (verified ? 'success' : '');
    const p = run.parameters || {};
    put('parameters', 'Registered parameters: r = ' + printable(p.r) + ', d = ' + printable(p.d) + ', L = ' + printable(p.L) + ', \u03c4 = ' + printable(p.tau) + '. Created ' + displayTime(run.created_at) + '.');
    put('result-explanation', claim === 'infeasible'
      ? 'The registered floor is infeasible under this declared channel. A verified infeasibility certificate does not enable sampling.'
      : verified
        ? 'These exact correctness probabilities describe the verified channel. The sampled labels below are one random outcome, and do not validate those probabilities or establish task usefulness.'
        : 'Verify the certificate against this run\u2019s registered parameters and context to display its exact channel result.');
  }

  function renderSampleMessage() {
    const messages = {
      blocked_verification: 'Verify the saved original feasible or optimal certificate to enable sampling.',
      ready: 'Ready: the server checks this displayed history revision, then atomically reserves and draws one complete conditional block for all public records.',
      infeasible: 'Sampling is unavailable: this verified certificate establishes that the requested floor is infeasible.',
      completed: 'The complete block is saved. This history cannot draw again; refreshing preserves the same output. Redelivery reuses the exact saved block across all aliases.',
      reserved_incomplete: 'This shared history has an incomplete draw reservation and stays blocked across all aliases and restarts. No partial sampled block is displayed or downloadable.',
      legacy_history_unregistered: 'This preserved run has no prospective Phase 3 history registration. Sampling stays blocked; its saved evidence is preserved.',
      integrity_error: 'Shared history evidence could not be verified. Sampling and redelivery stay blocked; preserve the evidence.'
    };
    let message = messages[samplingStatus()] || 'Sampling is unavailable for this run.';
    if (!sourceReady) {
      message = 'The registered research source could not be verified. Sampling stays blocked; refresh after restoring its exact reviewed bytes.';
    } else if (['ready', 'completed'].includes(samplingStatus()) && !certificateReady()) {
      message = 'The saved original certificate remains verified. Restore the saved certificate and verify it before sampling or redelivery from this screen.';
    }
    put('sample-message', message);
  }

  function renderEditorState() {
    if (!run) return;
    const matches = originalEditor();
    put('editor-status', matches ? 'Candidate matches the saved original' : 'Candidate edited \u00b7 saved original unchanged');
    renderSampleMessage();
    renderUsefulness();
    updateControls();
  }

  function renderAttempt() {
    const result = byId('verification-result');
    result.hidden = !lastAttempt;
    if (!lastAttempt) { result.textContent = ''; return; }
    result.className = 'verification-result ' + (lastAttempt.accepted ? 'success' : 'failure');
    const summary = lastAttempt.accepted
      ? 'Candidate accepted against the registered inputs. ' + (samplingStatus() === 'infeasible' ? 'The infeasibility claim is verified; no draw is allowed.' : 'The saved original certificate has a valid verification receipt.')
      : 'Candidate rejected: ' + (lastAttempt.error || 'The certificate does not match this run\u2019s registered evidence.') + (receiptVerified() ? ' The earlier valid receipt for the saved original is preserved.' : ' Sampling remains blocked.');
    result.textContent = summary;
  }

  function renderRun(detail, resetEditor) {
    if (!detail || typeof detail.run_id !== 'string' || !/^[0-9a-f]{32}$/.test(detail.run_id) || typeof detail.certificate_text !== 'string') {
      throw new Error('The research run has an unexpected format.');
    }
    run = detail;
    byId('run-detail').hidden = false;
    put('run-label', presetTitle(run.preset) + ' \u00b7 ' + run.run_id.slice(0, 8));
    byId('run-label').title = run.run_id;
    if (resetEditor) {
      controls.editor.value = run.certificate_text;
      editorAccepted = receiptVerified();
      lastAttempt = null;
    }
    renderResult();
    renderBindings();
    renderSharedHistory();
    renderRecords();
    renderArtifacts();
    renderProgress();
    renderEditorState();
    renderAttempt();
  }

  async function openSelectedRun() {
    const id = controls.saved.value;
    if (!/^[0-9a-f]{32}$/.test(id)) throw new Error('Select a saved research run first.');
    renderRun(await request('/runs/' + id), true);
  }

  controls.preset.addEventListener('change', updatePresetDescription);
  controls.saved.addEventListener('change', updateControls);
  controls.create.addEventListener('click', () => perform(async () => {
    const detail = await request('/runs', {method: 'POST', body: JSON.stringify({preset: controls.preset.value})});
    renderRun(detail, true);
    await refreshRuns();
    controls.saved.value = detail.run_id;
    byId('result-title').focus();
  }));
  controls.alias.addEventListener('click', () => perform(async () => {
    if (!currentHistorySnapshot()) throw new Error('This run lacks an intact registered shared history.');
    const detail = await request('/runs/' + run.run_id + '/alias', {method: 'POST', body: '{}'});
    renderRun(detail, true);
    await refreshRuns();
    controls.saved.value = detail.run_id;
    byId('history-title').focus();
  }));
  controls.inspectHistory.addEventListener('click', () => perform(async () => {
    const detail = await request('/runs/' + run.run_id + '/history');
    put('history-inspector', JSON.stringify(detail, null, 2));
    byId('history-inspector').parentElement?.setAttribute('open', '');
  }));
  controls.open.addEventListener('click', () => perform(openSelectedRun));
  controls.reload.addEventListener('click', () => perform(async () => {
    await refreshCatalog();
    await refreshRuns();
    if (run) renderRun(await request('/runs/' + run.run_id), false);
  }));
  controls.editor.addEventListener('input', () => {
    editorAccepted = false;
    lastAttempt = null;
    renderAttempt();
    renderEditorState();
  });
  controls.tamper.addEventListener('click', () => {
    if (busy || !run) return;
    try {
      const candidate = JSON.parse(run.certificate_text);
      candidate.context.retained_response_sha256 = '0'.repeat(64);
      controls.editor.value = JSON.stringify(candidate, null, 2) + '\n';
    } catch (_) {
      controls.editor.value = run.certificate_text + '\n{"tampered":true}\n';
    }
    editorAccepted = false;
    lastAttempt = null;
    renderAttempt();
    renderEditorState();
    controls.editor.focus();
  });
  controls.restore.addEventListener('click', () => {
    if (busy || !run) return;
    controls.editor.value = run.certificate_text;
    editorAccepted = false;
    lastAttempt = null;
    renderAttempt();
    renderEditorState();
    put('editor-status', 'Saved original restored \u00b7 verify this candidate again');
  });
  controls.verify.addEventListener('click', () => perform(async () => {
    const result = await request('/runs/' + run.run_id + '/verify', {
      method: 'POST', body: JSON.stringify({certificate: controls.editor.value})
    });
    if (!result || !result.run || !result.attempt || typeof result.attempt.accepted !== 'boolean') {
      throw new Error('The verification response has an unexpected format.');
    }
    lastAttempt = result.attempt;
    editorAccepted = result.attempt.accepted;
    renderRun(result.run, false);
    await refreshRuns();
  }));
  controls.sample.addEventListener('click', () => perform(async () => {
    const id = run.run_id;
    try {
      renderRun(await request('/runs/' + id + '/sample', {method: 'POST', body: JSON.stringify({
        expected_revision: sharedHistory().revision, expected_head_sha256: sharedHistory().head_sha256
      })}), false);
    } catch (error) {
      // Re-read a server-side reservation after refusal or an interrupted response.
      try { renderRun(await request('/runs/' + id), false); } catch (_) { /* Preserve the first failure. */ }
      throw error;
    }
    await refreshRuns();
  }));

  async function evaluateSavedBlock() {
    const id = run.run_id;
    try {
      renderRun(await request('/runs/' + id + '/evaluate', {method: 'POST', body: '{}'}), false);
    } catch (error) {
      // Re-read an exclusive evaluation reservation; retries cannot create another draw.
      try { renderRun(await request('/runs/' + id), false); } catch (_) { /* Preserve the original refusal. */ }
      throw error;
    }
    await refreshRuns();
    if (!byId('usefulness-results').hidden) byId('usefulness-title').focus();
  }
  controls.evaluate.addEventListener('click', () => perform(evaluateSavedBlock));
  controls.saveReport.addEventListener('click', () => perform(evaluateSavedBlock));

  async function refreshCatalog() {
    sourceReady = false;
    try {
      const catalog = await request('/catalog');
      if (!catalog || !Array.isArray(catalog.presets) || !catalog.presets.length) throw new Error('No research examples are available.');
      presets = catalog.presets;
      const selected = controls.preset.value;
      controls.preset.replaceChildren();
      presets.forEach((item) => {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = item.title;
        controls.preset.append(option);
      });
      if (presets.some((item) => item.id === selected)) controls.preset.value = selected;
      catalogLoaded = true;
      sourceReady = catalog.source_available === true && catalog.source_integrity_valid === true;
      put('source-status', sourceReady
        ? 'Reviewed source PDF verified against its registered SHA-256.'
        : (catalog.source_available === true ? 'Reviewed source PDF differs from the registered digest.' : 'Reviewed source PDF unavailable or unsafe.') + ' Creating, verifying, drawing and evaluating are blocked. Preserve existing runs and use Refresh after restoring the registered source.');
      byId('source-status').classList.toggle('warning', !sourceReady);
      updatePresetDescription();
    } catch (error) {
      put('source-status', 'The registered research source could not be checked. Use Refresh to retry when the local service is available.');
      byId('source-status').classList.add('warning');
      throw error;
    } finally {
      if (run) { renderSampleMessage(); renderUsefulness(); }
      updateControls();
    }
  }

  async function initialize() {
    busy = true;
    updateControls();
    try {
      await refreshCatalog();
      await refreshRuns();
    } catch (error) {
      showError(error.message || 'The research page could not be initialized.');
      put('preset-description', 'Research examples will load when the local service is available.');
    } finally {
      busy = false;
      updateControls();
    }
  }

  initialize();
})();
