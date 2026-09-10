'use strict';

const $ = id => document.getElementById(id);

const names = {trained:'Trained model','fine-tuned':'Fine-tuned',adapter:'LoRA / adapter',merged:'Merged model',ensemble:'Ensemble / routed',distilled:'Distilled model',language:'Language red-team',reference:'Reference scenarios',training:'Training demo',check:'Input preflight',assess:'Case assessment',api:'Controlled API','named-party-weights':'Named-party files','public-weights':'Public model files'};

let cases = [], jobs = [], selectedCase = null, selectedJob = null, lastCases = '', lastJobs = '', toastTimer;

const time = seconds => seconds ? new Date(seconds * 1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';

function el(tag, text, cls) {const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n;}

function toast(text) {$('toast').textContent = text; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 4500);}

async function api(path, payload) {let response; try {response = await fetch('/api/' + path, payload === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});} catch(error){throw new Error('Cannot reach the local console. Start mra-console local, then retry. Your saved cases and runs are retained.');} const body = await response.json(); if(!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Invalid request. Check the fields and try again.'); return body;}

function pill(value) {return el('span', value.replaceAll('_',' '), 'pill ' + (['completed','failed','cancelled','running','queued','inconclusive','inputs_incomplete'].includes(value) ? value : 'muted'));}

function outcome(job) {const r = job.result; if(r && r.tests)return (r.status==='incomplete'?'Incomplete coverage · ':'')+r.observed_violations+' observed violations';return r ? r.verdict || r.assessment_verdict || r.status || (r.scenarios ? '8 scenario results' : 'See report') : '—';}

function renderCases() {const rows = $('case-rows'); rows.replaceChildren(); $('case-empty').hidden = cases.length > 0; cases.forEach(c => {const tr=el('tr'); [c.name,names[c.kind],names[c.route],time(c.created)].forEach(v=>tr.append(el('td',v))); const td=el('td'), button=el('button','Open →','table-action'); button.setAttribute('aria-label','Open case ' + c.name); button.onclick=()=>showCase(c.id); td.append(button); tr.append(td); rows.append(tr);}); $('count-cases').textContent=cases.length; $('case-badge').textContent=cases.length;}

function renderJobs() {const rows=$('job-rows'); rows.replaceChildren(); $('job-empty').hidden=jobs.length>0; jobs.forEach(j=>{const tr=el('tr'); tr.append(el('td',names[j.kind])); const state=el('td'); state.append(pill(j.state)); tr.append(state); tr.append(el('td',outcome(j)),el('td',time(j.started || j.created))); const td=el('td'), b=el('button','View →','table-action'); b.setAttribute('aria-label','View ' + names[j.kind] + ' ' + j.id.slice(0,6)); b.onclick=()=>showJob(j.id); td.append(b); tr.append(td); rows.append(tr);});}

async function refresh() {try {const [status, c, j]=await Promise.all([api('status'),api('cases'),api('jobs')]); cases=c;jobs=j; $('connection').className='connection' + (status.worker_online?' online':''); $('connection').replaceChildren(el('i'),document.createTextNode(status.worker_online?'API & worker online':'API online · worker offline')); $('count-active').textContent=(status.jobs.queued||0)+(status.jobs.running||0); $('count-completed').textContent=status.jobs.completed||0; $('count-failed').textContent=status.jobs.failed||0; const cs=JSON.stringify(c),js=JSON.stringify(j); if(cs!==lastCases){renderCases();lastCases=cs;} if(js!==lastJobs){renderJobs();lastJobs=js;if(selectedJob && $('detail-dialog').open) renderJob(jobs.find(x=>x.id===selectedJob));}} catch(error){$('connection').className='connection';$('connection').replaceChildren(el('i'),document.createTextNode('Console disconnected'));}}

async function submitJob(kind, caseId=null) {try {const j=await api('jobs',{kind,case_id:caseId}); toast('Job queued. The worker will process it shortly.'); await refresh(); await showJob(j.id);}catch(e){toast(e.message);}}

async function showCase(id) {

  try {

    const c=await api('cases/'+id); selectedCase=id; selectedJob=null;

    $('detail-label').textContent=c.mode.toUpperCase()+' CASE'; $('detail-title').textContent=c.name;

    const box=$('detail-content'); box.replaceChildren();

    box.append(el('div',names[c.kind]+' · '+names[c.route],'detail-summary'));

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

function renderJob(j) {if(!j)return; $('detail-label').textContent='RUN '+j.id.slice(0,8).toUpperCase();$('detail-title').textContent=names[j.kind];const box=$('detail-content');box.replaceChildren(); const summary=el('div',undefined,'detail-summary');summary.append(pill(j.state),document.createTextNode('  '+time(j.created)));box.append(summary); if(j.state==='running' && j.progress)box.append(el('p',j.progress,'detail-summary')); if(j.error)box.append(el('p',j.error,'detail-warning')); if(j.options)box.append(el('p',Object.entries(j.options).map(([key,value])=>key+': '+value).join(' · '),'operator-note'));if(j.retry_of)box.append(el('p','New attempt of run '+j.retry_of.slice(0,8)+'; original results are retained.','operator-note'));appendRunActions(box,j);if(j.state==='queued')box.append(el('p','Waiting for a worker. Queued jobs persist if the console is restarted.','operator-note'));if(j.state==='running')box.append(el('p','The separate worker is processing this run. You can close this panel; results will appear here.','operator-note'));if(j.result){const r=j.result;if(r.tests){box.append(el('h3','Language test results'));r.tests.forEach(t=>{const row=el('div',undefined,'input-row');row.append(el('span',t.id.replaceAll('_',' ')),pill(t.status==='completed'?(t.observed_violation?'violation observed':'no match detected'):'failed'));box.append(row);});box.append(el('p','Observed violations: '+r.observed_violations+' · controls: '+JSON.stringify(r.controls),'operator-note'));(r.limitations||[]).forEach(t=>box.append(el('p',t,'operator-note')));}if(r.red_team){box.append(el('h3','Red-team coverage'));r.red_team.tools.forEach(t=>{const detail=el('details'),summary=el('summary'),row=el('div',undefined,'input-row');row.append(el('span',t.tool.replaceAll('_',' ')),pill(t.status));summary.append(row);detail.append(summary,el('pre',JSON.stringify(t.result||{error_type:t.error_type},null,2)));box.append(detail);});r.red_team.coverage_gaps.forEach(g=>box.append(el('p',g,'operator-note')));box.append(el('p','Exploratory tools: completion is not a safety verdict. Open each tool for its attack metrics, budgets and baselines.','detail-warning'));}if(r.case_id){const open=el('button','Open trained model case','primary');open.onclick=()=>showCase(r.case_id);box.append(open);}if(r.training){box.append(el('p','Training completed · '+r.dataset.rows+' samples · '+r.dataset.features+' features','operator-note'));box.append(el('pre',JSON.stringify(r.training.utility,null,2)));}if(r.artifact_directory)box.append(el('p','Saved under the data root: '+r.artifact_directory,'operator-note'));(r.warnings||[]).forEach(warning=>box.append(el('p',warning,'operator-note')));if(r.scenarios){r.scenarios.forEach(s=>{const row=el('div',undefined,'input-row');row.append(el('span',s.scenario_id.replaceAll('_',' ')),el('strong',String(s.result)));box.append(row);});}else if(r.issues){r.issues.forEach(issue=>box.append(el('p',issue,'detail-warning')));if(!r.issues.length)box.append(el('p','Input bindings are complete. Evidence adequacy is assessed separately.','operator-note'));}else{box.append(el('div','Scientific result: '+outcome(j),'detail-summary'));}box.append(el('p','No release authorization or deployment occurred. A completed job means execution finished; inspect the scientific result.','detail-warning'));const details=el('details'),label=el('summary','Inspect machine-readable result'),pre=el('pre',JSON.stringify(r,null,2));details.append(label,pre);box.append(details); const download=el('button','Download result JSON','secondary');download.onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download='mra-'+j.id+'-result.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};box.append(download);}appendArtifacts(box,j);}

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

$('run-reference').onclick=()=>submitJob('reference');$('run-training').onclick=()=>{trainingStep=0;renderTrainingStep();$('training-dialog').showModal();};

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



function updateTrainingSelection(){

  const descriptions={'sklearn-breast-cancer':'569 samples · 30 features · 2 classes','sklearn-wine':'178 samples · 13 features · 3 classes','sklearn-digits':'1797 images · 64 pixels · 10 classes','sklearn-diabetes':'442 records · 10 features · continuous target'};

  $('training-data-description').textContent=descriptions[$('training-dataset').value];

  const xgb=$('training-preset').querySelector('option[value="xgboost-small"]');xgb.disabled=$('training-dataset').value!=='sklearn-breast-cancer';

  if(xgb.disabled && $('training-preset').value==='xgboost-small')$('training-preset').value='logistic';

  for(const option of $('training-preset').options){

    if(option.value==='xgboost-small')continue;

    const isRegression=['ridge','forest-regression'].includes(option.value);

    option.disabled=isRegression!==($('training-dataset').value==='sklearn-diabetes') || (option.value==='cnn' && $('training-dataset').value!=='sklearn-digits');

  }

  if($('training-preset').selectedOptions[0].disabled)$('training-preset').value=Array.from($('training-preset').options).find(o=>!o.disabled).value;

  $('training-model-note').textContent='Freezes a membership-evidence plan before training and produces a registered assessment. Other tools remain exploratory; no preset authorizes release.';

}

$('training-dataset').onchange=updateTrainingSelection;$('training-preset').onchange=updateTrainingSelection;

$('show-capabilities').onclick=async()=>{try{const data=await api('capabilities');selectedJob=null;selectedCase=null;$('detail-label').textContent='IMPLEMENTED SUPPORT';$('detail-title').textContent='Framework capabilities';const box=$('detail-content');box.replaceChildren();for(const key of ['training','red_team','assessment'])box.append(el('h3',key),el('p',data[key]));box.append(el('h3','Separate experiment paths'));data.other_framework_paths.forEach(item=>box.append(el('p',item.family+' · '+item.status),el('code',item.entry)));box.append(el('h3','Missing integrations'));data.missing.forEach(item=>box.append(el('p',item,'operator-note')));$('detail-dialog').showModal();}catch(error){toast(error.message);}};



$('open-language').onclick=async()=>{try{const state=await api('language/models');const select=$('language-model');select.replaceChildren();state.models.forEach(m=>{const option=el('option',m.name);option.value=m.name;select.append(option);});$('language-error').textContent=state.available&&state.models.length?'':'Start Ollama with an installed model on 127.0.0.1:11434.';$('language-start').disabled=!state.models.length;$('language-dialog').showModal();}catch(e){toast(e.message);}};

$('close-language').onclick=()=>$('language-dialog').close();

$('language-form').onsubmit=async e=>{e.preventDefault();$('language-start').disabled=true;try{const job=await api('jobs',{kind:'language',language:{model:$('language-model').value}});$('language-dialog').close();await refresh();await showJob(job.id);}catch(error){$('language-error').textContent=error.message;}finally{$('language-start').disabled=false;}};

