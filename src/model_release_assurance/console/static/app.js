'use strict';

const $ = id => document.getElementById(id);

$('show-government-audit').onclick=showGovernmentControls;

const names = {trained:'Trained model','fine-tuned':'Fine-tuned',adapter:'LoRA / adapter',merged:'Merged model',ensemble:'Ensemble / routed',distilled:'Distilled model',language:'Language red-team',reference:'Reference scenarios',training:'Training demo',check:'Input preflight',assess:'Case assessment',api:'Controlled API','named-party-weights':'Named-party files','public-weights':'Public model files'};

let cases = [], jobs = [], selectedCase = null, selectedJob = null, lastCases = '', lastJobs = '', toastTimer;
let researchData = {configured:false,max_rows:4096,error:false};
let datasets = [], selectedDataset = null, lastDatasets = '';
let datasetOverview = {unlinked_case_count:0,unclassified_training_run_count:0};

const time = seconds => seconds ? new Date(seconds * 1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';

function el(tag, text, cls) {const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n;}

function toast(text) {$('toast').textContent = text; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 4500);}

async function api(path, payload) {let response; try {response = await fetch('/api/' + path, payload === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});} catch(error){throw new Error('Cannot reach the local console. Start mra-console local, then retry. Your saved cases and runs are retained.');} const body = await response.json(); if(!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Invalid request. Check the fields and try again.'); return body;}

function pill(value) {return el('span', value.replaceAll('_',' '), 'pill ' + (['completed','failed','cancelled','running','queued','clear','block','inconclusive','inputs_incomplete','needs_work'].includes(value) ? value : 'muted'));}

const reviewNames={evidence_recorded:'Evidence recorded',gap:'Gap identified',not_applicable:'Not applicable',recorded:'Recorded',needs_work:'Needs work',not_started:'Not started'};

async function showGovernmentControls(){
  try{
    const data=await api('government-audit');selectedCase=null;selectedJob=null;
    $('detail-label').textContent='GOVERNMENT AUDIT';$('detail-title').textContent='Review the full release';
    const box=$('detail-content');box.replaceChildren();
    box.append(el('p','Open a model case from its dataset to record your findings. These controls connect the revised paper to the agency review: test omission first, identify all dependencies and inspect the actual release path.','detail-summary'));
    data.controls.forEach(control=>{
      const detail=el('details'),title=el('summary',control.title);detail.append(title,el('p',control.motivation),el('p',control.review_question,'operator-note'));
      const examples=el('ul');control.evidence_examples.forEach(item=>examples.append(el('li',item)));detail.append(examples);box.append(detail);
    });
    box.append(el('p','File checks and recorded rationale do not prove private training or grant release approval. Education mode remains available for local public-data exercises.','detail-warning'));
    if(!$('detail-dialog').open)$('detail-dialog').showModal();
  }catch(error){toast(error.message);}
}

async function showGovernmentAudit(caseId){
  try{
    const data=await api('cases/'+caseId+'/government-audit');selectedCase=caseId;selectedJob=null;
    $('detail-label').textContent='GOVERNMENT AUDIT · '+data.mode.toUpperCase();$('detail-title').textContent='Evidence, rationale and gaps';
    const box=$('detail-content');box.replaceChildren();
    box.append(el('p',data.summary.recorded+' recorded · '+data.summary.needs_work+' need work · '+data.summary.not_started+' not started','detail-summary'));
    box.append(el('p','Recorded means an entry is current, not that its evidence is scientifically adequate. Rebinding the case or changing cited evidence makes earlier reviews stale. No release authorization is issued.','detail-warning'));
    const actions=el('div',undefined,'detail-actions'),back=el('button','Back to case','secondary'),download=el('button','Download review JSON','secondary'),refreshReview=el('button','Refresh evidence','secondary');
    back.onclick=()=>showCase(caseId);refreshReview.onclick=()=>showGovernmentAudit(caseId);
    download.onclick=()=>{const link=el('a');link.href='/api/cases/'+caseId+'/government-audit/download';link.download='government-audit-'+caseId+'.json';link.click();};
    actions.append(back,refreshReview,download);box.append(actions);
    data.controls.forEach(control=>{
      const detail=el('details',undefined,'audit-control'),summary=el('summary'),row=el('div',undefined,'input-row');
      row.append(el('strong',control.title),pill(control.state));summary.append(row);detail.append(summary,el('p',control.review_question));
      detail.append(el('p',control.motivation,'operator-note'));
      const suggestions=el('ul',undefined,'operator-note');control.evidence_examples.forEach(item=>suggestions.append(el('li',item)));detail.append(suggestions);
      if(control.latest_review){
        const latest=control.latest_review;
        detail.append(el('p',(reviewNames[latest.status]||latest.status)+(latest.stale?' · stale':''),'detail-summary'),el('p',latest.rationale));
        if(latest.evidence_slots.length)detail.append(el('p','Cited evidence: '+latest.evidence_slots.join(', '),'operator-note'));
      }
      control.issues.forEach(issue=>detail.append(el('p',String(issue).replaceAll('_',' '),'detail-warning')));
      const form=el('form',undefined,'audit-form'),status=el('select'),rationale=el('textarea'),evidence=el('fieldset'),checks=[];
      status.id='audit-status-'+control.id;rationale.id='audit-rationale-'+control.id;
      const statusLabel=el('label','Finding');statusLabel.htmlFor=status.id;
      ['gap','evidence_recorded','not_applicable'].forEach(value=>{const option=el('option',reviewNames[value]);option.value=value;status.append(option);});
      if(control.latest_review)status.value=control.latest_review.status;
      const rationaleLabel=el('label','Rationale (20–2,000 characters)');rationaleLabel.htmlFor=rationale.id;
      rationale.required=true;rationale.minLength=20;rationale.maxLength=2000;rationale.rows=4;
      rationale.placeholder='Explain what the evidence establishes, what is missing, or why this control does not apply.';
      if(control.latest_review)rationale.value=control.latest_review.rationale;
      evidence.append(el('legend','Already-bound case evidence'));
      data.evidence_slots.forEach((item,index)=>{
        const choice=el('input');choice.type='checkbox';choice.value=item.slot;choice.id='audit-evidence-'+control.id+'-'+index;choice.disabled=!item.bytes_valid;
        const label=el('label',item.slot+(item.bytes_valid?'':' · unavailable or changed'));label.htmlFor=choice.id;
        const holder=el('div',undefined,'audit-evidence');holder.append(choice,label);evidence.append(holder);checks.push(choice);
      });
      if(!data.evidence_slots.length)evidence.append(el('p','Bind evidence files in the case panel first. You can record a gap now.','operator-note'));
      const save=el('button','Record finding','primary');save.type='submit';
      form.append(statusLabel,status,rationaleLabel,rationale,evidence,save);
      form.onsubmit=async event=>{
        event.preventDefault();save.disabled=true;
        try{
          const evidenceSlots=checks.filter(c=>c.checked&&!c.disabled).map(c=>c.value);
          if(status.value==='evidence_recorded'&&!evidenceSlots.length)throw new Error('Select at least one unchanged bound evidence file, or record a gap.');
          if(rationale.value.trim().length<20)throw new Error('Explain the finding in at least 20 characters.');
          await api('cases/'+caseId+'/government-audit',{control_id:control.id,status:status.value,rationale:rationale.value,evidence_slots:evidenceSlots,expected_context_sha256:data.context_sha256});
          await showGovernmentAudit(caseId);toast('Review entry recorded. Earlier entries are retained.');
        }catch(error){toast(error.message);save.disabled=false;}
      };
      detail.append(form);
      if(control.history&&control.history.length){
        const history=el('details',undefined,'audit-history');history.append(el('summary','Recorded history ('+control.history_count+')'));
        control.history.forEach(entry=>{
          history.append(el('p',(reviewNames[entry.status]||entry.status)+' · '+(typeof entry.created==='number'?time(entry.created):entry.created)),el('p',entry.rationale,'operator-note'));
          if(entry.evidence_slots.length)history.append(el('p','Evidence: '+entry.evidence_slots.join(', '),'operator-note'));
          Object.entries(entry.evidence_sha256||{}).forEach(([slot,hash])=>history.append(el('p',slot+' · SHA-256 '+hash,'operator-note')));
        });
        if(control.history_truncated)history.append(el('p','Showing the newest entries. Earlier entries remain in the local database.','operator-note'));
        detail.append(history);
      }
      box.append(detail);
    });
    box.append(el('p','Case context SHA-256: '+data.context_sha256,'operator-note'));
    if(!$('detail-dialog').open)$('detail-dialog').showModal();
  }catch(error){toast(error.message);}
}

function outcome(job) {const r = job.result; if(r && r.tests)return (r.status==='incomplete'?'Incomplete coverage · ':'')+r.observed_violations+' observed violations';return r ? r.verdict || r.assessment_verdict || r.status || (r.scenarios ? '8 scenario results' : 'See report') : '—';}

function renderCases() {const rows = $('case-rows'); rows.replaceChildren(); $('case-empty').hidden = cases.length > 0; cases.forEach(c => {const tr=el('tr'); [c.name,names[c.kind],names[c.route],time(c.created)].forEach(v=>tr.append(el('td',v))); const td=el('td'), button=el('button','Open →','table-action'); button.setAttribute('aria-label','Open case ' + c.name); button.onclick=()=>showCase(c.id); td.append(button); tr.append(td); rows.append(tr);}); $('count-cases').textContent=cases.length; $('case-badge').textContent=cases.length;}

function renderJobs() {const rows=$('job-rows'); rows.replaceChildren(); $('job-empty').hidden=jobs.length>0; jobs.forEach(j=>{const tr=el('tr'); tr.append(el('td',names[j.kind])); const state=el('td'); state.append(pill(j.state)); tr.append(state); tr.append(el('td',outcome(j)),el('td',time(j.started || j.created))); const td=el('td'), b=el('button','View →','table-action'); b.setAttribute('aria-label','View ' + names[j.kind] + ' ' + j.id.slice(0,6)); b.onclick=()=>showJob(j.id); td.append(b); tr.append(td); rows.append(tr);});}

async function refresh() {
  try {
    const [status,c,j,d]=await Promise.all([api('status'),api('cases'),api('jobs'),api('datasets')]);
    cases=c;jobs=j;datasets=d.datasets;datasetOverview=d;
    $('connection').className='connection'+(status.worker_online?' online':'');
    $('connection').replaceChildren(el('i'),document.createTextNode(status.worker_online?'API & worker online':'API online · worker offline'));
    $('count-active').textContent=(status.jobs.queued||0)+(status.jobs.running||0);
    $('count-completed').textContent=status.jobs.completed||0;$('count-failed').textContent=status.jobs.failed||0;
    const cs=JSON.stringify(c),js=JSON.stringify(j),ds=JSON.stringify(d);
    if(cs!==lastCases){renderCases();lastCases=cs;}
    if(js!==lastJobs){renderJobs();lastJobs=js;if(selectedJob&&$('detail-dialog').open)renderJob(jobs.find(x=>x.id===selectedJob));}
    if(ds!==lastDatasets){renderDatasets(d);if(typeof refreshRedTeam==='function')refreshRedTeam();lastDatasets=ds;if(selectedDataset&&$('dataset-dialog').open){const selected=datasets.find(x=>x.id===selectedDataset);if(selected)renderDatasetDetail(selected);}}
  }catch(error){$('connection').className='connection';$('connection').replaceChildren(el('i'),document.createTextNode('Console disconnected'));if(!datasets.length)$('dataset-empty').textContent='Dataset records could not be loaded. Saved model cases and runs are retained. Retry when the local console is available.';}
}

const presetNames = {'dp-histogram':'Private categorical model',logistic:'Logistic regression','random-forest':'Random forest',mlp:'Small neural network','mlp-finetuned':'Fine-tuned MLP',cnn:'CPU convolutional classifier',ridge:'Ridge regression','forest-regression':'Random forest regression',svm:'RBF support-vector classifier',ensemble:'Ensemble', 'xgboost-small':'Registered XGBoost demo'};
const count = value => typeof value==='number'?value.toLocaleString():'Not recorded';
const isResearchDataset = dataset => dataset.id.startsWith('research-');
function latestDatasetRun(dataset){return dataset.training_runs.find(run=>run.state==='completed')||null;}
function closeDataset(){selectedDataset=null;$('dataset-dialog').close();}
function datasetAction(label,action,cls='secondary'){const button=el('button',label,cls);button.type='button';button.onclick=()=>{closeDataset();action();};return button;}

function renderDatasets(overview){
  const cards=$('dataset-cards');cards.replaceChildren();
  $('count-datasets').textContent=datasets.length;$('dataset-badge').textContent=datasets.length;
  const filter=$('dataset-filter').value;
  const shown=datasets.filter(d=>filter==='all'||(filter==='research')===isResearchDataset(d))
    .slice().sort((a,b)=>Number(isResearchDataset(b))-Number(isResearchDataset(a)));
  shown.forEach(dataset=>{
    const card=el('article',undefined,'dataset-card'),latest=latestDatasetRun(dataset),research=isResearchDataset(dataset);
    card.append(pill(research?'local research':'bundled example'),el('h3',dataset.name));
    card.append(el('p',dataset.task==='regression'?'Regression':'Classification'));
    const source=el('p',research?(dataset.configured?'Configured local source · checked when training starts':'Source not configured'):'Bundled public sample','dataset-source');
    card.append(source);
    if(research){
      card.append(el('p','At most '+count(dataset.max_rows)+' rows per training run','dataset-source'));
      const metadata=latest?.research_source?.metadata;
      if(metadata?.source_rows!==undefined)card.append(el('p',count(metadata.source_rows)+' prepared rows recorded · historical reuse','dataset-source'));
    }else card.append(el('p',count(dataset.source_rows)+' catalog rows · '+count(dataset.features)+' features','dataset-source'));
    card.append(el('p',dataset.summary.training_runs+' training run'+(dataset.summary.training_runs===1?'':'s')+' · '+dataset.summary.linked_cases+' model case'+(dataset.summary.linked_cases===1?'':'s'),'dataset-counts'));
    if(latest){const result=el('p','Latest model result: ','dataset-source');result.append(pill(latest.verdict||'not recorded'));card.append(result);if(latest.preset==='dp-histogram')card.append(el('p','Model-only record-membership scope · one release','operator-note'));}
    else card.append(el('p','No completed model run recorded','dataset-source'));
    const actions=el('div',undefined,'dataset-actions'),view=el('button','View dataset →','secondary'),train=el('button','Train a model','primary');
    view.type='button';view.setAttribute('aria-label','View dataset '+dataset.name);view.onclick=()=>showDataset(dataset.id);
    train.type='button';train.setAttribute('aria-label','Train a model on '+dataset.name);train.disabled=!dataset.configured;train.onclick=()=>openTraining(dataset.id);
    const red=el('button','Red-team results','secondary');red.type='button';red.setAttribute('aria-label','Red-team results for '+dataset.name);red.onclick=()=>openRedTeam(dataset.id);
    actions.append(view,train,red);card.append(actions);cards.append(card);
  });
  $('dataset-empty').hidden=shown.length>0;$('dataset-empty').textContent='No datasets match this view.';
  $('dataset-unlinked').hidden=!overview.unlinked_case_count&&!overview.unclassified_training_run_count;
  $('dataset-unlinked').textContent=overview.unlinked_case_count+' model cases have no recorded dataset link; '+overview.unclassified_training_run_count+' training runs have no recognised dataset selection. They remain in Model cases and Run history.';
}

function renderDatasetDetail(dataset){
  $('dataset-title').textContent=dataset.name;
  const box=$('dataset-content');box.replaceChildren();
  const latest=latestDatasetRun(dataset),research=isResearchDataset(dataset),metadata=latest?.research_source?.metadata;
  box.append(el('p','Dataset → model training → red-team checks → model assessment and review → evidence','dataset-dialog-intro'));
  box.append(el('p','Dataset records organise model work. A model verdict applies only to its recorded run and evidence; it does not clear the dataset or authorize release.','detail-warning'));
  const facts=el('div',undefined,'dataset-facts');
  const values=[['Source',research?'Retained public research matrix':'Scikit-learn bundled public sample'],['Task',dataset.task],
    ['Rows',research?(metadata?.source_rows!==undefined?count(metadata.source_rows)+' prepared rows (recorded)':'No prepared source observation recorded'):count(dataset.source_rows)+' catalog rows'],
    ['Features',count(research?latest?.features:dataset.features)],['Per-run sample',research?'At most '+count(dataset.max_rows)+' rows':count(dataset.max_rows)+' rows'],
    ['Recorded training',dataset.summary.completed+' completed · '+dataset.summary.failed+' failed · '+dataset.summary.active+' active']];
  values.forEach(([label,value])=>{const fact=el('div');fact.append(el('span',label),el('strong',value));facts.append(fact);});box.append(facts);
  const actions=el('div',undefined,'detail-actions'),train=datasetAction('Train a model',()=>openTraining(dataset.id),'primary');train.disabled=!dataset.configured;actions.append(train,datasetAction('Red-team results',()=>openRedTeam(dataset.id)));box.append(actions);
  if(research)box.append(el('p',dataset.configured?'Research root configured. Source and manifest pins are checked when a new training run starts; this overview has not rehashed current files.':'Research source is not configured for new training. Restart with --research-data-root PATH to enable it. Earlier runs and evidence remain available.','operator-note'));
  if(latest?.research_source){
    const details=el('details');details.append(el('summary','Last recorded research source'),el('p','From training run '+latest.job_id.slice(0,8)+' · '+time(latest.finished||latest.created)+'. Public covariates and utility labels only. Historical reuse is not fresh audit evidence; current source bytes have not been verified by this view.','operator-note'),el('pre',JSON.stringify(latest.research_source,null,2)));box.append(details);
  }
  box.append(el('h3','Training runs ('+dataset.summary.training_runs+')'));
  if(!dataset.training_runs.length)box.append(el('p','No training runs recorded for this dataset yet. Choose a compatible model to start.','operator-note'));
  dataset.training_runs.forEach(run=>{
    const row=el('article',undefined,'dataset-run'),header=el('div',undefined,'input-row');
    header.append(el('strong',presetNames[run.preset]||run.preset),pill(run.state));row.append(header);
    row.append(el('p','Run '+run.job_id.slice(0,8)+' · '+time(run.started||run.created),'operator-note'));
    if(run.rows!==null)row.append(el('p',count(run.rows)+' rows · '+count(run.features)+' features','operator-note'));
    if(run.verdict)row.append(el('p','Recorded model result: '+run.verdict,'operator-note'));
    if(run.preset==='dp-histogram')row.append(el('p','Private training profile: model-only record membership for one release. Other releases and operator evidence require separate review.','operator-note'));
    if(run.retry_of)row.append(el('p','Retry of '+run.retry_of.slice(0,8)+'; original attempt retained.','operator-note'));
    const runActions=el('div',undefined,'detail-actions');runActions.append(datasetAction('Inspect run and evidence',()=>showJob(run.job_id)));runActions.append(datasetAction('Red-team results',()=>openRedTeam(dataset.id,run.job_id)));
    if(run.case_id)runActions.append(datasetAction('Review model case',()=>showCase(run.case_id)));
    row.append(runActions);box.append(row);
  });
  box.append(el('h3','Related model cases ('+dataset.summary.linked_cases+')'));
  if(!dataset.cases.length)box.append(el('p','No completed training result links a saved model case to this dataset. Manually created cases remain in the secondary Model cases view.','operator-note'));
  dataset.cases.forEach(model=>{
    const row=el('div',undefined,'dataset-case');row.append(el('strong',model.name||model.case_id),el('p',(names[model.kind]||model.kind)+' · '+(names[model.route]||model.route),'operator-note'));
    row.append(datasetAction('Open model case →',()=>showCase(model.case_id),'table-action'));
    if(model.followup_jobs.length){row.append(el('p','Input checks and assessments','operator-note'));model.followup_jobs.forEach(job=>{const line=el('div',undefined,'input-row');line.append(el('span',(names[job.kind]||job.kind)+' · '+job.state+(job.kind==='assess'?' · '+(job.verdict||'No recorded assessment verdict'):'')),datasetAction('View run',()=>showJob(job.job_id),'table-action'));row.append(line);});}
    box.append(row);
  });
}

async function showDataset(id){
  try{const dataset=await api('datasets/'+encodeURIComponent(id));selectedDataset=id;renderDatasetDetail(dataset);if(!$('dataset-dialog').open)$('dataset-dialog').showModal();}catch(error){toast(error.message);}
}

async function openTraining(datasetId=null,presetId=null){
  if($('detail-dialog').open){$('detail-dialog').close();selectedCase=null;selectedJob=null;}
  if($('dataset-dialog').open)closeDataset();
  trainingStep=0;await loadTrainingCapabilities();
  if(datasetId){$('training-dataset').value=datasetId;const dataset=datasets.find(d=>d.id===datasetId);if(dataset)$('training-name').value=dataset.name+' model training';}
  if(presetId){$('training-preset').value=presetId;$('training-name').value='Private Wine model · membership clearance';}
  renderTrainingStep();$('training-dialog').showModal();
}

$('dataset-filter').onchange=()=>renderDatasets(datasetOverview);
$('close-dataset').onclick=closeDataset;
$('dataset-dialog').addEventListener('close',()=>{selectedDataset=null;});

async function submitJob(kind, caseId=null) {try {const j=await api('jobs',{kind,case_id:caseId}); toast('Job queued. The worker will process it shortly.'); await refresh(); await showJob(j.id);}catch(e){toast(e.message);}}

async function showCase(id) {

  try {

    const c=await api('cases/'+id); selectedCase=id; selectedJob=null;

    $('detail-label').textContent=c.mode.toUpperCase()+' CASE'; $('detail-title').textContent=c.name;

    const box=$('detail-content'); box.replaceChildren();

    box.append(el('div',names[c.kind]+' · '+names[c.route],'detail-summary'));

    const audit=el('button','Government audit review','secondary');
    audit.onclick=()=>showGovernmentAudit(id);
    box.append(audit,el('p','Review necessity, recipient access and repeated-export dependencies. Records and gaps remain separate from the scientific assessment.','operator-note'));

    c.inputs.forEach(input=>{const row=el('div',undefined,'input-row'); row.append(el('span',input.slot.replaceAll('-',' ')),pill(input.bound?'bound':input.required?'missing':'optional'));box.append(row);if(input.bound)box.append(el('p',input.path+' · SHA-256 '+input.sha256,'operator-note'));});

    if(c.supporting_inputs&&c.supporting_inputs.length){box.append(el('h3','Supporting evidence'));c.supporting_inputs.forEach(input=>box.append(el('p',input.slot+' · '+input.path+' · SHA-256 '+input.sha256,'operator-note')));}
    const toggle=el('button',c.mode==='education'?'Use review mode':'Use education mode','secondary');

    toggle.onclick=async()=>{try{await api('cases/'+id+'/mode',{mode:c.mode==='education'?'review':'education'});await showCase(id);}catch(e){toast(e.message);}};

    box.append(el('p',c.mode==='education'?'Education mode: agency scope, security report and independent review are optional for exercises.':'Review mode requires all eight input slots.','operator-note'),toggle);

    {

      const form=el('form'), slot=el('select'), path=el('input');

      slot.id='binding-slot'; path.id='binding-path'; path.required=true; path.placeholder='Absolute file path on this computer';

      const slotLabel=el('label','Input slot'),pathLabel=el('label','Local file path');slotLabel.htmlFor=slot.id;pathLabel.htmlFor=path.id;

      c.inputs.forEach(input=>{const option=el('option',input.slot);option.value=input.slot;slot.append(option);});

      const submit=el('button','Bind local file','secondary'); submit.type='submit';

      form.append(slotLabel,slot,pathLabel,path,submit);

      form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;try{await api('cases/'+id+'/bindings',{slot:slot.value,path:path.value});await showCase(id);toast('Local file bound with its current SHA-256.');}catch(e){toast(e.message);}finally{submit.disabled=false;}};

      box.append(form,el('p','Paths refer to the console computer (inside the container when using Docker). File contents are hashed; model code is not executed.','operator-note'));

    }

    const path=el('p',undefined,'operator-note');path.append(document.createTextNode('Case directory under the data root: '),el('code',c.operator_case_directory));box.append(path);

    const actions=el('div',undefined,'detail-actions'), check=el('button','Check inputs','primary'),assess=el('button','Run assessment','secondary');

    check.onclick=()=>submitJob('check',id);assess.onclick=()=>submitJob('assess',id);actions.append(check,assess);

    box.append(actions,el('p','Required inputs and evidence integrity checks still apply. Exercises do not authorize model release.','operator-note'));

    if(!$('detail-dialog').open)$('detail-dialog').showModal();

  }catch(e){toast(e.message);}

}

function renderJob(j) {if(!j)return; $('detail-label').textContent='RUN '+j.id.slice(0,8).toUpperCase();$('detail-title').textContent=names[j.kind];const box=$('detail-content');box.replaceChildren(); const summary=el('div',undefined,'detail-summary');summary.append(pill(j.state),document.createTextNode('  '+time(j.created)));box.append(summary); if(j.state==='running' && j.progress)box.append(el('p',j.progress,'detail-summary')); if(j.error)box.append(el('p',j.error,'detail-warning')); if(j.options)box.append(el('p',Object.entries(j.options).map(([key,value])=>key+': '+value).join(' · '),'operator-note'));if(j.retry_of)box.append(el('p','New attempt of run '+j.retry_of.slice(0,8)+'; original results are retained.','operator-note'));appendRunActions(box,j);if(j.state==='queued')box.append(el('p','Waiting for a worker. Queued jobs persist if the console is restarted.','operator-note'));if(j.state==='running')box.append(el('p','The separate worker is processing this run. You can close this panel; results will appear here.','operator-note'));if(j.result){const r=j.result;if(typeof appendAssessmentExplanation==='function')appendAssessmentExplanation(box,j);if(r.tests){box.append(el('h3','Language test results'));r.tests.forEach(t=>{const row=el('div',undefined,'input-row');row.append(el('span',t.id.replaceAll('_',' ')),pill(t.status==='completed'?(t.observed_violation?'violation observed':'no match detected'):'failed'));box.append(row);});box.append(el('p','Observed violations: '+r.observed_violations+' · controls: '+JSON.stringify(r.controls),'operator-note'));(r.limitations||[]).forEach(t=>box.append(el('p',t,'operator-note')));}if(r.red_team){box.append(el('h3','Red-team coverage'));r.red_team.tools.forEach(t=>{const detail=el('details'),summary=el('summary'),row=el('div',undefined,'input-row');row.append(el('span',t.tool.replaceAll('_',' ')),pill(t.status));summary.append(row);detail.append(summary,el('pre',JSON.stringify(t.result||{error_type:t.error_type},null,2)));box.append(detail);});r.red_team.coverage_gaps.forEach(g=>box.append(el('p',g,'operator-note')));box.append(el('p','Exploratory tools: completion is not a safety verdict. Open each tool for its attack metrics, budgets and baselines.','detail-warning'));}if(r.case_id){const open=el('button','Open trained model case','primary');open.onclick=()=>showCase(r.case_id);box.append(open);}if(r.training){box.append(el('p','Training completed · '+r.dataset.rows+' samples · '+r.dataset.features+' features','operator-note'));box.append(el('pre',JSON.stringify(r.training.utility,null,2)));}if(r.artifact_directory)box.append(el('p','Saved under the data root: '+r.artifact_directory,'operator-note'));(r.warnings||[]).forEach(warning=>box.append(el('p',warning,'operator-note')));if(r.scenarios){r.scenarios.forEach(s=>{const row=el('div',undefined,'input-row');row.append(el('span',s.scenario_id.replaceAll('_',' ')),el('strong',String(s.result)));box.append(row);});}else if(r.issues){r.issues.forEach(issue=>box.append(el('p',issue,'detail-warning')));if(!r.issues.length)box.append(el('p','Input bindings are complete. Evidence adequacy is assessed separately.','operator-note'));}else{box.append(el('div','Scientific result: '+outcome(j),'detail-summary'));}box.append(el('p','No release authorization or deployment occurred. A completed job means execution finished; inspect the scientific result.','detail-warning'));const details=el('details'),label=el('summary','Inspect machine-readable result'),pre=el('pre',JSON.stringify(r,null,2));details.append(label,pre);box.append(details); const download=el('button','Download result JSON','secondary');download.onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download='mra-'+j.id+'-result.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};box.append(download);}appendArtifacts(box,j);}

async function showJob(id) {selectedJob=id;selectedCase=null;const j=jobs.find(x=>x.id===id)||await api('jobs/'+id);renderJob(j);if(!$('detail-dialog').open)$('detail-dialog').showModal();}
function appendRunActions(box,j){
  const actions=el('div',undefined,'detail-actions');
  if(j.state==='queued'){
    const cancel=el('button','Cancel queued run','secondary');
    cancel.onclick=async()=>{cancel.disabled=true;try{await api('jobs/'+j.id+'/cancel',{});await refresh();await showJob(j.id);toast('Queued run cancelled.');}catch(e){toast(e.message);cancel.disabled=false;}};
    actions.append(cancel);
  }
  if(['failed','cancelled'].includes(j.state)){
    const retry=el('button','Retry as new run','primary');
    retry.onclick=async()=>{retry.disabled=true;try{const next=await api('jobs/'+j.id+'/retry',{});await refresh();await showJob(next.id);}catch(e){toast(e.message);retry.disabled=false;}};
    actions.append(retry);
  }
  if(j.case_id){const open=el('button','Open source case','secondary');open.onclick=()=>showCase(j.case_id);actions.append(open);}
  if(actions.childNodes.length)box.append(actions);
}
function appendArtifacts(box,j){
  const section=el('section'),button=el('button','Browse evidence and diagnostics','secondary'),listing=el('div');
  section.append(el('h3','Saved artifacts'),button,listing);box.append(section);
  button.onclick=async()=>{
    button.disabled=true;
    try{
      const inventory=await api('jobs/'+j.id+'/artifacts');listing.replaceChildren();
      listing.append(el('p',inventory.files.length+' files · '+Math.ceil(inventory.total_bytes/1024)+' KiB'+(inventory.partial?' · partial or unsuccessful run':''),'operator-note'));
      if(!inventory.files.length)listing.append(el('p','No artifacts have been written yet.','operator-note'));
      if(!['queued','running'].includes(j.state)&&inventory.files.length){
        const bundle=el('a','Download evidence ZIP','secondary');bundle.href='/api/jobs/'+j.id+'/bundle';bundle.download='mra-'+j.id+'-evidence.zip';listing.append(bundle);
      }
      inventory.files.forEach(item=>{const details=el('details'),summary=el('summary',item.path),link=el('a','Download file','table-action');link.href=item.download_url;link.download=item.path.split('/').pop();details.append(summary,el('p',item.size_bytes+' bytes · SHA-256 '+item.sha256,'operator-note'),link);listing.append(details);});
      listing.append(el('p',inventory.note,'operator-note'));button.textContent='Refresh artifact list';
    }catch(e){toast(e.message);}finally{button.disabled=false;}
  };
}
for(const id of ['new-case','new-case-empty'])$(id).onclick=()=>{$('form-error').textContent='';$('case-dialog').showModal();};

$('close-create').onclick=()=>$('case-dialog').close();$('close-detail').onclick=()=>{$('detail-dialog').close();selectedJob=null;selectedCase=null;};

$('case-form').onsubmit=async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{const c=await api('cases',{name:$('case-name').value,kind:$('case-kind').value,route:$('case-route').value,mode:$('case-mode').value});$('case-dialog').close();$('case-form').reset();await refresh();await showCase(c.id);}catch(e){$('form-error').textContent=e.message;}finally{button.disabled=false;}};

$('run-reference').onclick=()=>submitJob('reference');$('run-training').onclick=()=>openTraining();

refresh();setInterval(refresh,2500);



let trainingStep=0;

function renderTrainingStep(){

  updateTrainingSelection();

  ['training-data','training-settings','training-review'].forEach((id,index)=>$(id).hidden=index!==trainingStep);

  $('training-step').textContent=['STEP 1 OF 3 · SAMPLE DATA','STEP 2 OF 3 · TRAINING PRESET','STEP 3 OF 3 · REVIEW'][trainingStep];

  $('training-back').hidden=trainingStep===0;$('training-next').hidden=trainingStep===2;$('training-start').hidden=trainingStep!==2;

  $('training-error').textContent='';$('training-summary').textContent=$('training-name').value+' · '+$('training-dataset').selectedOptions[0].text+' · '+$('training-preset').selectedOptions[0].text+' · Education mode';updateTrainingSelection();

}

$('training-next').onclick=()=>{if(!$('training-name').reportValidity())return;trainingStep++;renderTrainingStep();};

$('training-back').onclick=()=>{trainingStep--;renderTrainingStep();};

$('close-training').onclick=()=>$('training-dialog').close();

$('training-form').onsubmit=async event=>{

  event.preventDefault();if(trainingStep!==2){$('training-next').click();return;}

  $('training-start').disabled=true;

  try{const job=await api('jobs',{kind:'training',training:{name:$('training-name').value,dataset:$('training-dataset').value,preset:$('training-preset').value}});$('training-dialog').close();await refresh();await showJob(job.id);}

  catch(error){$('training-error').textContent=error.message;}finally{$('training-start').disabled=false;}

};



async function loadTrainingCapabilities(){
  try{
    const data=await api('capabilities');
    researchData={configured:data.research_data?.configured===true,max_rows:4096,error:false};
  }catch(error){
    researchData={configured:false,max_rows:4096,error:true};
  }
  updateTrainingSelection();
}

function updateTrainingSelection(){
  const dataset=$('training-dataset'),isResearch=dataset.value.startsWith('research-');
  for(const option of dataset.options){
    if(option.value.startsWith('research-'))option.disabled=!researchData.configured;
  }
  const descriptions={
    'sklearn-breast-cancer':'569 samples · 30 features · 2 classes',
    'sklearn-wine':'178 samples · 13 features · 3 classes',
    'sklearn-digits':'1797 images · 64 pixels · 10 classes',
    'sklearn-diabetes':'442 records · 10 features · continuous target',
    'research-acs':'Historical public census sample · at most 4,096 sampled rows · 8 features · 2 classes',
    'research-bts':'Historical public aviation sample · at most 4,096 sampled rows · 7 features · 2 classes',
    'research-hmda':'Historical public lending sample · at most 4,096 sampled rows · 7 features · 2 classes',
    'research-tlc':'Historical public mobility sample · at most 4,096 sampled rows · 4 features · 2 classes'
  };
  $('training-data-description').textContent=descriptions[dataset.value];
  $('training-source-note').textContent=isResearch
    ?'Uses public covariates and utility labels only; withheld attributes and record keys are omitted. Historical training data is reused, so this is not fresh audit evidence. Missing or changed source files fail the run; no download or replacement dataset is used.'
    :'Bundled with scikit-learn. No upload, account or dataset download needed. Learn on public sample data; this exercise does not establish clinical validity.';
  $('training-research-note').textContent=researchData.configured
    ?'Local public research sources are configured. Each selected source must pass validation when its run starts; configuration does not establish availability, freshness or scientific qualification.'
    :researchData.error
      ?'Could not check local research configuration. Research choices are disabled; the four bundled datasets remain available.'
      :'Optional local research sources are not configured. Restart the launcher with --research-data-root PATH to enable their choices; the four bundled datasets remain available.';
  $('training-coverage').textContent=researchData.configured
    ?'11 model presets · 4 bundled + 4 optional research profiles'
    :'11 model presets · 4 bundled datasets';

  const xgb=$('training-preset').querySelector('option[value="xgboost-small"]');xgb.disabled=dataset.value!=='sklearn-breast-cancer';
  if(xgb.disabled && $('training-preset').value==='xgboost-small')$('training-preset').value='logistic';
  for(const option of $('training-preset').options){
    if(option.value==='xgboost-small')continue;
    const isRegression=['ridge','forest-regression'].includes(option.value);
    option.disabled=isRegression!==(dataset.value==='sklearn-diabetes') || (option.value==='cnn' && dataset.value!=='sklearn-digits') || (option.value==='dp-histogram' && dataset.value!=='sklearn-wine');
  }
  if($('training-preset').selectedOptions[0].disabled)$('training-preset').value=Array.from($('training-preset').options).find(o=>!o.disabled).value;
  const researchUnavailable=isResearch&&!researchData.configured;
  $('training-next').disabled=researchUnavailable;
  $('training-start').disabled=researchUnavailable;
  const privatePreset=$('training-preset').value==='dp-histogram';
  $('training-recipe-note').textContent=privatePreset?'Uses fixed public feature bins and fresh private randomness to train a categorical model. The noise and its random seed are not retained. Utility can vary between runs.':'Local CPU presets use a fixed training seed. Scaling is fitted on training data only. Compatible red-team tools run automatically; unsupported tools remain explicit.';
  $('training-model-note').textContent=privatePreset?'Freezes the unchanged membership tolerance (0.20 at false-positive rate 0.10), trains once and verifies the privacy mechanism and exact model-only package. The prospective local policy explicitly waives institutional attack-battery qualification; it does not authorize release. Existing conventional model verdicts do not change.':'Freezes a membership-evidence plan before training and produces a registered assessment. Other tools remain exploratory; no preset authorizes release.';
  $('training-review-scope').textContent=privatePreset?'Assesses only the recipient model package for record membership from one training release. Operator evidence, prior models, utility qualification and other privacy threats are outside this clearance. A new training run spends additional privacy budget.':'Runs on your local worker. The registered assessment may be inconclusive or blocked. Additional exploratory tools do not supply release authorization.';
}

$('run-private-training').onclick=()=>openTraining('sklearn-wine','dp-histogram');
$('training-dataset').onchange=updateTrainingSelection;$('training-preset').onchange=updateTrainingSelection;

$('show-capabilities').onclick=async()=>{try{const data=await api('capabilities');selectedJob=null;selectedCase=null;$('detail-label').textContent='IMPLEMENTED SUPPORT';$('detail-title').textContent='Framework capabilities';const box=$('detail-content');box.replaceChildren();for(const key of ['training','red_team','assessment'])box.append(el('h3',key),el('p',data[key]));box.append(el('h3','Separate experiment paths'));data.other_framework_paths.forEach(item=>box.append(el('p',item.family+' · '+item.status),el('code',item.entry)));box.append(el('h3','Missing integrations'));data.missing.forEach(item=>box.append(el('p',item,'operator-note')));$('detail-dialog').showModal();}catch(error){toast(error.message);}};



$('open-language').onclick=async()=>{try{const state=await api('language/models');const select=$('language-model');select.replaceChildren();state.models.forEach(m=>{const option=el('option',m.name);option.value=m.name;select.append(option);});$('language-error').textContent=state.available&&state.models.length?'':'Start Ollama with an installed model on 127.0.0.1:11434.';$('language-start').disabled=!state.models.length;$('language-dialog').showModal();}catch(e){toast(e.message);}};

$('close-language').onclick=()=>$('language-dialog').close();

$('language-form').onsubmit=async e=>{e.preventDefault();$('language-start').disabled=true;try{const job=await api('jobs',{kind:'language',language:{model:$('language-model').value}});$('language-dialog').close();await refresh();await showJob(job.id);}catch(error){$('language-error').textContent=error.message;}finally{$('language-start').disabled=false;}};

