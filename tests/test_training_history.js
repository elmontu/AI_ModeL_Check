'use strict';
// Run with: node --test tests/test_training_history.js
// Executes the production pure history builders without a DOM or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appPath = path.join(__dirname, '..', 'src', 'model_release_assurance', 'console', 'static', 'app.js');
const source = fs.readFileSync(appPath, 'utf8');
function section(startMarker, endMarker) {
  const start = source.indexOf(startMarker), end = source.indexOf(endMarker, start);
  assert(start >= 0 && end > start, 'Cannot locate actual history source: ' + startMarker);
  return source.slice(start, end);
}
const builders = vm.runInNewContext(
  section('const presetNames =', 'const count =') + '\n' +
  section('// Dataset graph uses', 'function graphSvg(') + '\n' +
  section('// Training history models.', '// End training history models.') +
  '\n({buildTrainingHistory, buildSlmTrainingHistory});',
  {}, {filename: appPath}
);
const plain = value => JSON.parse(JSON.stringify(value));
const history = (input, filter = 'all') => plain(builders.buildTrainingHistory(input, filter));
const slmHistory = input => plain(builders.buildSlmTrainingHistory(input));
const hexId = value => value.toString(16).padStart(32, '0');
const hash = character => character.repeat(64);
const caseA = hexId(9001), caseB = hexId(9002);
const entries = result => result.groups.flatMap(group => group.entries);
const group = (result, datasetId) => result.groups.find(item => item.dataset.id === datasetId);
function datasetFixture() {
  return [
    {id:'sklearn-wine', name:'Same display name', configured:true, cases:[{case_id:caseA}],
      training_runs:[
        {job_id:hexId(3), created:300, state:'completed', preset:'logistic', verdict:'clear', case_id:caseA},
        {job_id:hexId(1), created:100, state:'failed', preset:'logistic', verdict:'clear', case_id:caseA},
        {job_id:hexId(2), created:200, state:'completed', preset:'logistic', verdict:null, case_id:caseA, retry_of:hexId(1)},
      ]},
    {id:'research-acs', name:'Same display name', configured:true, cases:[{case_id:caseB}],
      training_runs:[{job_id:hexId(4), created:150, state:'completed', preset:'mlp', verdict:'block', case_id:caseB}]},
    {id:'sklearn-breast-cancer', name:'Empty source', configured:true, cases:[], training_runs:[]},
  ];
}
function slmFixture(chainId = hexId(100), offset = 20) {
  return [0,1,2].map(stage => {
    const jobId = hexId(offset + stage), model = 'mra-fixture-' + chainId.slice(-4) + '-stage-' + stage;
    return {
      job:{id:jobId, kind:'language', state:'completed', result:{model, model_digest:hash(String(stage + 1)), model_digest_stable:true, status:'completed', observed_violations:stage}},
      manifest:{format_version:'slm-training-history/1', training_run_id:chainId, stage_index:stage,
        stage_label:stage === 0 ? 'Pretrained base' : 'Fine-tuning stage ' + stage,
        model_tag:model, serving_digest:hash(String(stage + 1)), job_id:jobId,
        parent_job_id:stage === 0 ? null : hexId(offset + stage - 1),
        checkpoint_sha256:hash(String(stage + 4)), parent_checkpoint_sha256:stage === 0 ? null : hash(String(stage + 3)),
        dataset_id:'synthetic-agency-faq', dataset_sha256:hash('a'), source_revision:hash('b').slice(0,40),
        training_method:stage === 0 ? 'pretrained' : 'output-head-lora', steps:stage === 0 ? 0 : 4,
        train_loss:stage === 0 ? null : 1.5 - stage / 10, status:'completed'},
    };
  });
}

test('all dataset attempts are chronological within their exact dataset, including repeated presets', () => {
  const result = history(datasetFixture());
  assert.deepEqual(group(result, 'sklearn-wine').entries.map(entry => entry.run.job_id), [hexId(1),hexId(2),hexId(3)]);
  assert.deepEqual(group(result, 'research-acs').entries.map(entry => entry.run.job_id), [hexId(4)]);
  assert.equal(group(result, 'sklearn-breast-cancer').entries.length, 0);
  assert.equal(entries(result).length, 4);
  assert.equal(group(result, 'sklearn-wine').entries.filter(entry => entry.run.preset === 'logistic').length, 3);
});

test('dataset history retains every run beyond the recent-job API window', () => {
  const input = datasetFixture();
  input[0].training_runs = Array.from({length:153}, (_, index) => ({job_id:hexId(1000 + index), created:1000 + index, state:'completed', preset:'logistic'})).reverse();
  const wine = group(history(input), 'sklearn-wine');
  assert.equal(wine.entries.length, 153);
  assert.deepEqual(wine.entries.map(entry => entry.run.job_id), Array.from({length:153}, (_, index) => hexId(1000 + index)));
});

test('the dataset selector does not mix identical display names or infer associations', () => {
  const result = history(datasetFixture(), 'research-acs');
  assert.deepEqual(result.groups.map(item => item.dataset.id), ['research-acs']);
  assert.deepEqual(entries(result).map(entry => entry.run.job_id), [hexId(4)]);
  assert.equal(history(datasetFixture(), 'missing-dataset').groups.length, 0);
});

test('a retry links only to the exact recorded attempt in the same dataset', () => {
  const input = datasetFixture();
  const wine = group(history(input), 'sklearn-wine');
  assert.equal(wine.entries.find(entry => entry.run.job_id === hexId(2)).retryOf, hexId(1));
  input[0].training_runs[2].retry_of = hexId(4);
  assert.equal(group(history(input), 'sklearn-wine').entries.find(entry => entry.run.job_id === hexId(2)).retryOf, null);
  for (const retry of ['../../other-job', hexId(999), hexId(2)]) {
    input[0].training_runs[2].retry_of = retry;
    assert.equal(group(history(input), 'sklearn-wine').entries.find(entry => entry.run.job_id === hexId(2)).retryOf, null);
  }
});

test('failed, active, cancelled and unknown attempts cannot acquire models or assessments', () => {
  const input = datasetFixture();
  input[0].training_runs = ['failed','queued','running','cancelled','unexpected'].map((state,index) =>
    ({job_id:hexId(2000 + index), created:100 + index, state, preset:'logistic', verdict:'clear', case_id:caseA}));
  for (const entry of group(history(input), 'sklearn-wine').entries) {
    assert.equal(entry.isModel, false);
    assert.equal(entry.verdict, null);
    assert.equal(entry.caseId, null);
  }
  assert.equal(group(history(input), 'sklearn-wine').entries.at(-1).state, 'unknown');
});

test('completed model results keep their own verdict and exact dataset case association', () => {
  const input = datasetFixture();
  input[0].cases[0].followup_jobs = [{job_id:hexId(999), kind:'assess', verdict:'block'}];
  let wine = group(history(input), 'sklearn-wine').entries;
  assert.equal(wine.find(entry => entry.run.job_id === hexId(3)).verdict, 'clear');
  assert.equal(wine.find(entry => entry.run.job_id === hexId(2)).verdict, null);
  assert.equal(wine.find(entry => entry.run.job_id === hexId(3)).caseId, caseA);
  input[0].training_runs[0].case_id = caseB;
  input[0].training_runs[0].verdict = 'unrecognised';
  wine = group(history(input), 'sklearn-wine').entries;
  assert.equal(wine.find(entry => entry.run.job_id === hexId(3)).caseId, null);
  assert.equal(wine.find(entry => entry.run.job_id === hexId(3)).verdict, null);
  assert(!entries(history(input)).some(entry => entry.run.job_id === hexId(999)));
});

test('invalid job identities never become inspectable history entries', () => {
  const input = datasetFixture();
  input[0].training_runs.push({...input[0].training_runs[0], job_id:'../../other-job'});
  input[0].training_runs.push({...input[0].training_runs[0], job_id:'A'.repeat(32)});
  assert.equal(entries(history(input)).length, 4);
});

test('history sorting and selection never mutate retained dataset or run records', () => {
  const input = datasetFixture(), before = JSON.stringify(input);
  history(input); history(input, 'research-acs'); history(input, 'missing-dataset');
  assert.equal(JSON.stringify(input), before);
});


test('unknown timestamps stay last and do not invent a chronology from numeric strings', () => {
  const input = datasetFixture();
  input[0].training_runs = [300, null, '100', NaN, Infinity, undefined, 100].map((created,index) =>
    ({job_id:hexId(3000 + index), created, state:'completed', preset:'logistic'}));
  const wine = group(history(input), 'sklearn-wine').entries;
  assert.deepEqual(wine.slice(0,2).map(entry => entry.created), [100,300]);
  for (const entry of wine.slice(2)) {
    assert.equal(entry.created, null);
    assert.match(entry.orderLabel, /time.*not recorded/i);
  }
});

test('tied timestamps are explicitly tied rather than asserted successive trainings', () => {
  const input = datasetFixture();
  input[0].training_runs[0].created = 200;
  const wine = group(history(input), 'sklearn-wine').entries;
  assert.equal(wine[1].created, 200);
  assert.equal(wine[2].created, 200);
  assert.match(wine[1].orderLabel, /same.*time/i);
  assert.equal(wine[1].orderLabel, wine[2].orderLabel);
});

test('non-string dataset identities cannot become jobs or crash chronological ordering', () => {
  const input = datasetFixture();
  input[0].training_runs.push({...input[0].training_runs[0], job_id:[hexId(8000)]});
  assert.equal(entries(history(input)).length, 4);
});

const slmStages = result => result.groups.flatMap(item => item.stages);
const slmStage = (result, jobId) => slmStages(result).find(stage => stage.job.id === jobId);
function assertRejected(record, message) {
  const result = slmHistory([record]);
  assert.equal(result.groups.length, 0, message);
  assert.equal(result.errors.length, 1, message);
}

test('a real base and two continued stages connect by exact recorded parent identity and hash', () => {
  const input = slmFixture(), result = slmHistory(input);
  assert.equal(result.errors.length, 0);
  assert.equal(result.groups.length, 1);
  assert.equal(result.groups[0].runId, hexId(100));
  const stages = result.groups[0].stages;
  assert.deepEqual(stages.map(stage => stage.manifest.stage_index), [0,1,2]);
  assert.equal(stages[0].parent, null);
  assert.equal(stages[0].linked, false);
  for (const index of [1,2]) {
    assert.equal(stages[index].parent, hexId(20 + index - 1));
    assert.equal(stages[index].linked, true);
    assert.equal(stages[index].issue, '');
  }
  assert(stages.every(stage => stage.diagnosticBound));
});

test('stage ordering uses recorded stage indices even when API jobs arrive newest first', () => {
  const result = slmHistory(slmFixture().reverse());
  assert.deepEqual(result.groups[0].stages.map(stage => stage.manifest.stage_index), [0,1,2]);
  assert(result.groups[0].stages.slice(1).every(stage => stage.linked));
});

test('separate fine-tuning chains never link by identical display names', () => {
  const first = slmFixture(), second = slmFixture(hexId(101),80);
  first.concat(second).forEach(record => record.manifest.stage_label = 'Same stage name');
  const result = slmHistory(first.concat(second));
  assert.equal(result.groups.length, 2);
  assert.equal(result.errors.length, 0);
  for (const chain of result.groups) {
    const ownJobs = new Set(chain.stages.map(stage => stage.job.id));
    for (const stage of chain.stages.slice(1)) assert(ownJobs.has(stage.parent));
  }
});

test('missing parent stages remain visible with unresolved lineage', () => {
  for (const index of [1,2]) {
    const result = slmHistory([slmFixture()[index]]), stage = result.groups[0].stages[0];
    assert.equal(result.errors.length, 0);
    assert.equal(stage.linked, false);
    assert.equal(stage.parent, null);
    assert.match(stage.issue, /missing|unresolved/i);
  }
});

test('parent identity, checkpoint hash and exact pretrained revision must each match', () => {
  for (const [field, value] of [['parent_job_id',hexId(999)], ['parent_checkpoint_sha256',hash('f')], ['source_revision',hash('c').slice(0,40)]]) {
    const input = slmFixture(); input[2].manifest[field] = value;
    const stage = slmStage(slmHistory(input),hexId(22));
    assert.equal(stage.linked, false, field);
    assert.equal(stage.parent, null, field);
    assert.match(stage.issue, /does not match/i, field);
  }
});

test('a parent recorded in another chain cannot satisfy the previous stage', () => {
  const input = slmFixture(); input[1].manifest.training_run_id = hexId(777);
  const result = slmHistory(input);
  assert.equal(result.groups.length, 2);
  for (const jobId of [hexId(21),hexId(22)]) {
    const stage = slmStage(result,jobId);
    assert.equal(stage.linked,false);
    assert.equal(stage.parent,null);
  }
});

test('base-stage local parents, optimizer updates and loss cannot be fabricated', () => {
  for (const [field, value] of [['parent_job_id',hexId(999)], ['parent_checkpoint_sha256',hash('f')], ['steps',1], ['train_loss',1]]) {
    const record = slmFixture()[0]; record.manifest[field] = value;
    assertRejected(record,field);
  }
});

test('the manifest must bind the exact language job and served tag and digest', () => {
  for (const mutation of [
    record => record.manifest.job_id = hexId(999),
    record => record.job.kind = 'training',
    record => record.job.result.model = 'other-model',
    record => record.job.result.model_digest = hash('f'),
    record => record.job.options = {model:'other-model'},
  ]) {
    const record = slmFixture()[2]; mutation(record); assertRejected(record);
  }
});

test('malformed and non-string identities, hashes and revisions remain visible errors', () => {
  const fields = ['training_run_id','checkpoint_sha256','serving_digest','dataset_sha256','source_revision','parent_job_id','parent_checkpoint_sha256'];
  for (const field of fields) {
    const original = slmFixture()[2].manifest[field];
    for (const value of ['../../other-file', original.toUpperCase(), [original], {value:original}, null]) {
      // All-digit fixture identities have no uppercase variant; use alphabetic invalid IDs instead.
      if (value === original) continue;
      const record = slmFixture()[2]; record.manifest[field] = value;
      assertRejected(record,field + ': ' + JSON.stringify(value));
    }
  }
  for (const value of ['unsupported/1', null, '']) {
    const record = slmFixture()[2]; record.manifest.format_version = value; assertRejected(record);
  }
});

test('stage indices, steps, loss and synthetic metadata must have valid finite types', () => {
  const mutations = {
    stage_index:[-1,3,1.5,'2',true], steps:[0,-1,1.5,'4',true,Infinity,1000001],
    train_loss:[null,'1.5',true,NaN,Infinity], dataset_id:['private-records',null],
    status:['queued','failed',null], training_method:['',null,{}], stage_label:['',null,{}], model_tag:['',null,{}],
  };
  for (const [field, values] of Object.entries(mutations)) for (const value of values) {
    const record = slmFixture()[2]; record.manifest[field] = value; assertRejected(record,field + ': ' + String(value));
  }
});

test('duplicate stage indices cannot form a fork that looks like one continuation', () => {
  const input = slmFixture(), duplicate = plain(input[1]);
  duplicate.job.id = hexId(99); duplicate.manifest.job_id = duplicate.job.id;
  const result = slmHistory(input.concat(duplicate));
  assert.equal(slmStages(result).length, 4);
  for (const jobId of [hexId(21),hexId(99),hexId(22)]) {
    const stage = slmStage(result,jobId);
    assert.equal(stage.linked,false);
    assert.equal(stage.parent,null);
    assert.match(stage.issue,/ambiguous|duplicate/i);
  }
});

test('duplicate job identities across chains leave every affected parent unresolved', () => {
  const input = slmFixture(), duplicateBase = plain(input[0]);
  duplicateBase.manifest.training_run_id = hexId(101);
  const result = slmHistory(input.concat(duplicateBase));
  const repeated = slmStages(result).filter(stage => stage.job.id === hexId(20));
  assert.equal(repeated.length,2);
  assert(repeated.every(stage => !stage.linked && /duplicate|ambiguous/i.test(stage.issue)));
  assert.equal(slmStage(result,hexId(21)).linked,false);
  assert.equal(slmStage(result,hexId(21)).parent,null);
});

test('failed language diagnostics retain completed training without claiming served-model confirmation', () => {
  const input = slmFixture();
  input[1].job.state = 'failed'; input[1].job.result = null; input[1].job.options = {model:input[1].manifest.model_tag};
  const result = slmHistory(input), stage = slmStage(result,hexId(21));
  assert.equal(result.errors.length,0);
  assert.equal(stage.manifest.status,'completed');
  assert.equal(stage.job.state,'failed');
  assert.equal(stage.linked,true);
  assert.equal(stage.diagnosticBound,false);
});

test('a result-free diagnostic must retain its actual selected model option', () => {
  for (const options of [undefined,{}, {model:'other-model'}]) {
    const record = slmFixture()[1]; record.job.state = 'failed'; record.job.result = null; record.job.options = options;
    assertRejected(record);
  }
});

test('unstable or missing serving confirmation never becomes a confirmed diagnostic', () => {
  for (const confirmation of [false, undefined, 'true', 1]) {
    const input = slmFixture(); input[2].job.result.model_digest_stable = confirmation;
    const result = slmHistory(input), stage = slmStage(result,hexId(22));
    assert.equal(result.errors.length,0);
    assert.equal(stage.linked,true);
    assert.equal(stage.diagnosticBound,false);
  }
});

test('SLM validation and stage sorting never mutate saved manifests, jobs or diagnostic results', () => {
  const input = slmFixture().reverse(), before = JSON.stringify(input);
  slmHistory(input); slmHistory(input.slice(0,1));
  assert.equal(JSON.stringify(input),before);
});

test('untrusted stage labels and methods render as literal DOM text, never executable markup', () => {
  class TestNode {
    constructor(tag) {this.tag = tag; this.children = []; this.attributes = {}; this.dataset = {}; this._text = '';}
    set textContent(value) {this._text = String(value); this.children = [];}
    get textContent() {return this._text + this.children.map(child => child.textContent).join('');}
    set innerHTML(_) {throw new Error('Saved training labels must not use innerHTML');}
    append(...children) {this.children.push(...children);}
    replaceChildren(...children) {this._text = ''; this.children = [...children];}
    setAttribute(name,value) {this.attributes[name] = String(value);}
  }
  const nodes = new Map();
  const get = id => {if (!nodes.has(id)) nodes.set(id,new TestNode('div')); return nodes.get(id);};
  const input = slmFixture(), payload = '<img src=x onerror="globalThis.executed=true">';
  input[1].manifest.stage_label = payload;
  input[2].manifest.training_method = '<svg onload="globalThis.executed=true">';
  const context = {document:{createElement:tag => new TestNode(tag)}, $:get,
    slmHistoryRecords:input, slmHistoryErrors:[], slmHistoryBusy:false,
    jobs:input.map(record => record.job)};
  vm.runInNewContext(
    section('const presetNames =','const count =') + '\n' +
    section('// Dataset graph uses','function graphSvg(') + '\n' +
    section('// Training history models.','// End training history models.') + '\n' +
    section('function el(','function toast(') + '\n' +
    section('function pill(','const reviewNames=') + '\n' +
    section('function historyButton(','async function loadSlmHistoryRecord(') + '\nrenderSlmTrainingHistory();',
    context, {filename:appPath}
  );
  const root = get('slm-history-groups');
  assert(root.textContent.includes(payload));
  assert(root.textContent.includes(input[2].manifest.training_method));
  const descendants = node => [node,...node.children.flatMap(descendants)];
  assert(!descendants(root).some(node => ['img','svg','script'].includes(node.tag)));
  assert.equal(context.executed,undefined);
});
