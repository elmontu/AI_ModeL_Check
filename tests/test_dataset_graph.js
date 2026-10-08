'use strict';
// Run with: node --test tests/test_dataset_graph.js
// Executes the actual pure graph builder; no DOM, API, packages or demo data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appPath = path.join(__dirname, '..', 'src', 'model_release_assurance', 'console', 'static', 'app.js');
const source = fs.readFileSync(appPath, 'utf8');
function section(startMarker, endMarker) {
  const start = source.indexOf(startMarker), end = source.indexOf(endMarker, start);
  assert(start >= 0 && end > start, 'Cannot locate actual graph source: ' + startMarker);
  return source.slice(start, end);
}
const builder = vm.runInNewContext(
  section('const presetNames =', 'const count =') + '\n' +
  section('// Dataset graph uses', 'function graphSvg(') + '\nbuildDatasetGraph;',
  {}, {filename: appPath}
);
const graph = (input, query = '', state = 'all') => JSON.parse(JSON.stringify(builder(input, query, state)));
const id = value => value.repeat(32);
const ids = ['1', '2', '3', '4', '5', '6', '7', '8'].map(id);
const caseA = id('a'), caseB = id('b'), followup = id('f');
const entries = result => result.groups.flatMap(group => group.runs);
const attemptIds = result => entries(result).map(entry => entry.run.job_id).sort();
const group = (result, datasetId) => result.groups.find(item => item.dataset.id === datasetId);
function fixture() {
  const run = (index, state, verdict, case_id, preset = 'logistic') =>
    ({job_id: ids[index], state, preset, verdict, case_id});
  return [
    {id: 'research-acs', name: 'Same display name',
      training_runs: [
        run(0, 'completed', 'clear', caseA), run(1, 'completed', null, caseA),
        run(2, 'failed', 'clear', caseA), run(3, 'running', 'clear', caseA),
        run(5, 'completed', 'inconclusive', caseB, 'ridge'),
        run(6, 'queued', 'clear', caseA), run(7, 'cancelled', 'clear', caseA),
      ],
      cases: [{case_id: caseA, name: 'Same model name',
        followup_jobs: [{job_id: followup, kind: 'assess', state: 'completed', verdict: 'block'}]}]},
    {id: 'sklearn-wine', name: 'Same display name',
      training_runs: [run(4, 'completed', 'block', caseB)],
      cases: [{case_id: caseB, name: 'Same model name', followup_jobs: []}]},
    {id: 'research-hmda', name: 'Empty source', training_runs: [], cases: []},
  ];
}

test('every retained attempt keeps its exact dataset identity, including repeated model presets', () => {
  const result = graph(fixture());
  assert.equal(result.datasetCount, 3);
  assert.equal(result.runCount, 8);
  assert.equal(result.modelCount, 4);
  assert.deepEqual(attemptIds(result), [...ids].sort());
  assert.equal(group(result, 'research-acs').runs.length, 7);
  assert.equal(group(result, 'research-acs').runs.filter(entry => entry.run.preset === 'logistic').length, 6);
  assert.deepEqual(group(result, 'sklearn-wine').runs.map(entry => entry.run.job_id), [ids[4]]);
  assert.equal(group(result, 'research-hmda').runs.length, 0);
});

test('case links use completed results and exact cases belonging to that dataset', () => {
  const input = fixture(), result = graph(input);
  assert.equal(group(result, 'research-acs').runs.find(entry => entry.run.job_id === ids[0]).caseId, caseA);
  assert.equal(group(result, 'sklearn-wine').runs[0].caseId, caseB);
  // This is a real case in another dataset with the same display name.
  assert.equal(group(result, 'research-acs').runs.find(entry => entry.run.job_id === ids[5]).caseId, null);
  input[0].training_runs[0].case_id = caseA.toUpperCase();
  assert.equal(group(graph(input), 'research-acs').runs[0].caseId, null);
});

test('unfinished and unsuccessful attempts cannot acquire a model or forged CLEAR result', () => {
  const result = graph(fixture());
  for (const index of [2, 3, 6, 7]) {
    const entry = entries(result).find(item => item.run.job_id === ids[index]);
    assert.equal(entry.verdict, null);
    assert.equal(entry.caseId, null);
    assert.equal(entry.isModel, false);
  }
});

test('missing verdicts remain absent and later followup results never replace training results', () => {
  const input = fixture(), result = graph(input), runs = group(result, 'research-acs').runs;
  assert.equal(runs.find(entry => entry.run.job_id === ids[0]).verdict, 'clear');
  assert.equal(runs.find(entry => entry.run.job_id === ids[1]).verdict, null);
  assert(!entries(result).some(entry => entry.run.job_id === followup));
  input[0].training_runs[1].verdict = 'unrecognized-result';
  assert.equal(group(graph(input), 'research-acs').runs.find(entry => entry.run.job_id === ids[1]).verdict, null);
});

test('search retains only matching attempts and their source, with empty source lookup supported', () => {
  const input = fixture();
  const exact = graph(input, ids[2].slice(0, 8));
  assert.equal(exact.datasetCount, 1);
  assert.equal(exact.groups[0].dataset.id, 'research-acs');
  assert.deepEqual(attemptIds(exact), [ids[2]]);
  assert.deepEqual(attemptIds(graph(input, '  LOGISTIC REGRESSION  ')), ids.filter((_, index) => index !== 5).sort());
  const empty = graph(input, 'research-hmda');
  assert.equal(empty.datasetCount, 1);
  assert.equal(empty.runCount, 0);
  assert.equal(graph(input, 'unmatched source or run').datasetCount, 0);
});

test('state filters distinguish completed models, active attempts and unsuccessful attempts', () => {
  const input = fixture(), completed = graph(input, '', 'completed');
  assert.deepEqual(attemptIds(completed), [ids[0], ids[1], ids[4], ids[5]].sort());
  assert.equal(completed.modelCount, 4);
  const active = graph(input, '', 'active');
  assert.deepEqual(attemptIds(active), [ids[3], ids[6]].sort());
  assert.equal(active.modelCount, 0);
  assert.deepEqual(attemptIds(graph(input, '', 'failed')), [ids[2], ids[7]].sort());
  assert.equal(graph(input, ids[0].slice(0, 8), 'active').runCount, 0);
});

test('invalid run identities and unknown states cannot be promoted into model verdicts', () => {
  const input = fixture();
  input[0].training_runs.push({...input[0].training_runs[0], job_id: '../../other-run'});
  input[0].training_runs.push({...input[0].training_runs[0], job_id: id('e'), state: 'unexpected'});
  const result = graph(input);
  assert.equal(result.runCount, 9);
  assert(!entries(result).some(entry => entry.run.job_id === '../../other-run'));
  const unknown = entries(result).find(entry => entry.run.job_id === id('e'));
  assert.equal(unknown.state, 'unknown');
  assert.equal(unknown.isModel, false);
  assert.equal(unknown.verdict, null);
  assert.equal(unknown.caseId, null);
});

test('graph filtering and ordering never mutate retained source records', () => {
  const input = fixture(), before = JSON.stringify(input);
  for (const [query, state] of [['', 'all'], ['logistic', 'completed'], ['', 'active'], ['research-hmda', 'all']])
    graph(input, query, state);
  assert.equal(JSON.stringify(input), before);
});
