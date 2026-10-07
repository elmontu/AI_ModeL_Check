// Read-only red-team workspace over catalog entries and exact retained jobs.
let redTeamCatalog=null,redTeamSignature='',redTeamRequest=0,redTeamJob=null;
const redTeamLabels={
 structural_disclosure:'Structural disclosure',worst_case_membership:'Learned membership attack',
 membership_score_attacks:'Loss, confidence and entropy membership',model_extraction:'Model extraction screen',
 attribute_inference:'Attribute inference screen',numeric_robustness:'Numeric perturbation screen',
 label_only_membership:'Label-only membership',adaptive_adversarial_search:'Adaptive adversarial search',
 tree_leaf_exposure:'Tree leaf exposure',label_poisoning:'Label poisoning experiment',trigger_backdoor:'Trigger backdoor experiment',
 regression_loss_membership:'Regression membership',regression_extraction:'Regression extraction screen',
 regression_perturbation:'Regression perturbation screen',direct_secret:'Direct secret extraction',
 instruction_override:'Instruction override',role_spoofing:'Role spoofing',encoded_extraction:'Encoded extraction',
 fragment_extraction:'Fragment extraction',rag_document_injection:'Document injection',
 rag_answer_contamination:'Answer contamination',agent_action_injection:'Inert tool-call injection',
 multi_turn_pressure:'Multi-turn pressure'
};
const redTeamMetricPaths={
 structural_disclosure:['metrics.generalization_gap','metrics.parameter_to_training_record_ratio','metrics.minimum_equivalence_class_size'],
 worst_case_membership:['summary.maximum_auc','summary.maximum_dummy_auc','summary.valid_operating_point_repetitions'],
 membership_score_attacks:['probes.negative_loss.auc','probes.confidence.auc','probes.negative_entropy.auc'],
 model_extraction:['surrogate_agreement','majority_baseline_agreement','query_budget'],
 attribute_inference:['accuracy','majority_baseline_accuracy','feature_index','query_budget'],
 numeric_robustness:['clean_accuracy','perturbations.0.accuracy','perturbations.0.prediction_flip_rate','perturbations.0.standard_deviation_fraction'],
 label_only_membership:['auc','tpr','fpr','member_trials'],
 adaptive_adversarial_search:['budgets.0.attack_success_rate_on_correct','budgets.0.random_baseline_success_rate_on_correct','budgets.0.epsilon_training_std','evaluation_records'],
 tree_leaf_exposure:['records_with_singleton_leaf','records_with_leaf_occupancy_below_five','unique_full_path_signatures'],
 label_poisoning:['clean_retrain_accuracy','trials.0.accuracy_drop_from_clean_retrain','trials.0.poison_fraction'],
 trigger_backdoor:['trials.0.trigger_attack_success_rate','trials.0.clean_model_trigger_baseline','trials.0.poison_fraction'],
 regression_loss_membership:['auc','tpr','fpr','member_trials'],
 regression_extraction:['surrogate_teacher_mse','constant_baseline_mse','query_budget'],
 regression_perturbation:['clean_mse']
};
const redTeamMetricLabels={
 'metrics.generalization_gap':'Generalization gap','metrics.parameter_to_training_record_ratio':'Parameters per training record','metrics.minimum_equivalence_class_size':'Smallest equivalence class',
 'summary.maximum_auc':'Maximum attack AUC','summary.maximum_dummy_auc':'Maximum dummy AUC','summary.valid_operating_point_repetitions':'Valid operating-point repetitions',
 'probes.negative_loss.auc':'Loss attack AUC','probes.confidence.auc':'Confidence attack AUC','probes.negative_entropy.auc':'Entropy attack AUC',
 surrogate_agreement:'Surrogate agreement',majority_baseline_agreement:'Majority baseline agreement',query_budget:'Query budget',
 accuracy:'Inference accuracy',majority_baseline_accuracy:'Majority baseline accuracy',feature_index:'Transformed feature index',
 clean_accuracy:'Clean accuracy','perturbations.0.accuracy':'Accuracy after first perturbation','perturbations.0.prediction_flip_rate':'Prediction flip rate','perturbations.0.standard_deviation_fraction':'Noise relative to feature scale',
 auc:'Attack AUC',tpr:'True-positive rate',fpr:'False-positive rate',member_trials:'Member trials',
 'budgets.0.attack_success_rate_on_correct':'Attack success rate','budgets.0.random_baseline_success_rate_on_correct':'Random-search baseline success rate','budgets.0.epsilon_training_std':'Perturbation relative to feature scale',evaluation_records:'Evaluation records',
 records_with_singleton_leaf:'Records in singleton leaves',records_with_leaf_occupancy_below_five:'Records in leaves below five occupants',unique_full_path_signatures:'Unique tree-path signatures',
 clean_retrain_accuracy:'Clean retrain accuracy','trials.0.accuracy_drop_from_clean_retrain':'Accuracy drop in first trial','trials.0.poison_fraction':'Poisoned fraction in first trial',
 'trials.0.trigger_attack_success_rate':'Trigger success in first trial','trials.0.clean_model_trigger_baseline':'Clean-model trigger baseline',
 surrogate_teacher_mse:'Surrogate mean squared error',constant_baseline_mse:'Constant-baseline mean squared error',clean_mse:'Clean mean squared error'
};
function redTeamDataset(){return datasets.find(d=>d.id===$('red-team-dataset').value);}
function redTeamEntries(dataset){
 const suite=dataset?.task==='regression'?'regression':'tabular';
 return (redTeamCatalog?.entries||[]).filter(entry=>entry.suite_id===suite);
}
function redTeamMetrics(card,record){
 const values=el('dl',undefined,'red-team-metrics');
 (redTeamMetricPaths[record.tool]||[]).forEach(path=>{
  const value=path.split('.').reduce((v,key)=>v&&typeof v==='object'?v[key]:undefined,record.result);
  if(typeof value==='number'&&Number.isFinite(value)){
   const label=path.replace(/^(metrics|summary)\./,'').replace(/\.0\./g,'.first trial.').replaceAll('_',' ');
   values.append(el('dt',redTeamMetricLabels[path]||label),el('dd',value.toLocaleString(undefined,{maximumSignificantDigits:6})));
  }
 });
 if(values.children.length){card.append(el('p','Selected recorded metrics','operator-note'),values);
  if((redTeamMetricPaths[record.tool]||[]).some(path=>path.includes('.0.')))card.append(el('p','First recorded trial shown; expand the result for all trials and budgets.','operator-note'));
 }
}
function renderRedTeamCards(dataset,job){
 const cards=$('red-team-cards');cards.replaceChildren();
 const recorded=job?.state==='completed'&&Array.isArray(job.result?.red_team?.tools)?job.result.red_team.tools:[];
 const entries=redTeamEntries(dataset);
 const known=new Set(entries.map(entry=>entry.tool_id));
 const display=[...entries,...recorded.filter(t=>typeof t.tool==='string'&&!known.has(t.tool)).map(t=>({tool_id:t.tool,scope:'Recorded tool outside the current catalog.'}))];
 display.forEach(entry=>{
  const record=recorded.find(t=>t.tool===entry.tool_id),card=el('article',undefined,'red-team-card');
  const status=record?(['completed','failed','unsupported'].includes(record.status)?record.status:'unknown'):'not recorded';
  const head=el('div',undefined,'input-row');head.append(el('h3',redTeamLabels[entry.tool_id]||entry.tool_id.replaceAll('_',' ')),pill(status));card.append(head);
  card.append(el('p',entry.scope||'See the retained result for this tool.','red-team-scope'));
  if(record){redTeamMetrics(card,record);const details=el('details');details.append(el('summary','Recorded result and scope'),el('pre',JSON.stringify(record,null,2)));card.append(details);}
  else card.append(el('p','No result recorded for this tool in the selected run.','operator-note'));
  cards.append(card);
 });
 const gaps=$('red-team-gaps');gaps.replaceChildren();
 const coverage=job?.state==='completed'?job.result?.red_team:null;
 if(coverage){gaps.append(el('h3','Coverage gaps'));(coverage.coverage_gaps||[]).forEach(gap=>gaps.append(el('p',gap,'operator-note')));}
}
function renderRedTeamRun(job){
 redTeamJob=job;
 const dataset=redTeamDataset(),records=job?.state==='completed'&&Array.isArray(job.result?.red_team?.tools)?job.result.red_team.tools:[];
 if(job){
  const totals=['completed','failed','unsupported'].map(state=>records.filter(t=>t.status===state).length+' '+state).join(' · ');
  $('red-team-run-status').textContent=(presetNames[job.options?.preset]||job.options?.preset||'Model')+' · run '+job.id.slice(0,8)+' · '+job.state+' · '+time(job.finished||job.created)+(records.length?' · '+totals:' · No red-team results recorded');
 }else $('red-team-run-status').textContent='No training run recorded for this dataset. Train a model to run its compatible checks.';
 const actions=$('red-team-result-actions');actions.replaceChildren();
 if(job){const inspect=el('button','Open run and evidence','secondary');inspect.type='button';inspect.onclick=()=>showJob(job.id);actions.append(inspect);}
 renderRedTeamCards(dataset,job);
}
async function loadRedTeamRun(){
 const sequence=++redTeamRequest,dataset=redTeamDataset(),id=$('red-team-run').value;
 redTeamJob=null;$('red-team-result-actions').replaceChildren();renderRedTeamCards(dataset,null);
 if(!dataset||!id){renderRedTeamRun(null);return;}
 $('red-team-run-status').textContent='Loading recorded red-team results…';
 try{
  const job=await api('jobs/'+encodeURIComponent(id));
  if(sequence!==redTeamRequest)return;
  if(job.id!==id||job.kind!=='training'||job.options?.dataset!==dataset.id)throw Error('The run does not match this dataset. No results were displayed.');
  renderRedTeamRun(job);
 }catch(error){if(sequence===redTeamRequest){$('red-team-run-status').textContent=error.message;renderRedTeamCards(dataset,null);}}
}
function redTeamRuns(preferred=null){
 const dataset=redTeamDataset(),select=$('red-team-run'),previous=preferred||select.value;
 select.replaceChildren();
 (dataset?.training_runs||[]).forEach(run=>{
  const option=el('option',(presetNames[run.preset]||run.preset)+' · '+run.state+' · '+time(run.created)+' · '+run.job_id.slice(0,8));option.value=run.job_id;select.append(option);
 });
 if(!select.children.length){const option=el('option','No recorded training runs');option.value='';select.append(option);}
 if(dataset?.training_runs.some(run=>run.job_id===previous))select.value=previous;
 else select.value=(dataset?.training_runs.find(run=>run.state==='completed')||dataset?.training_runs[0])?.job_id||'';
 select.disabled=!dataset?.training_runs.length;
 $('red-team-train').disabled=!dataset?.configured;
 loadRedTeamRun();
}
function refreshRedTeam(){
 const signature=JSON.stringify(datasets.map(d=>({id:d.id,name:d.name,configured:d.configured,task:d.task,runs:d.training_runs})));
 if(signature===redTeamSignature)return;
 redTeamSignature=signature;
 const select=$('red-team-dataset'),previous=select.value;
 select.replaceChildren();
 datasets.slice().sort((a,b)=>Number(isResearchDataset(b))-Number(isResearchDataset(a))).forEach(dataset=>{
  const option=el('option',dataset.name);option.value=dataset.id;select.append(option);
 });
 if(datasets.some(d=>d.id===previous))select.value=previous;
 else select.value=(datasets.find(d=>isResearchDataset(d)&&d.training_runs.length)||datasets.find(d=>d.training_runs.length)||datasets[0])?.id||'';
 select.disabled=!datasets.length;
 redTeamRuns();
}
function openRedTeam(datasetId,runId=null){
 if($('dataset-dialog').open)closeDataset();
 refreshRedTeam();
 if(datasets.some(d=>d.id===datasetId))$('red-team-dataset').value=datasetId;
 redTeamRuns(runId);
 $('red-team-tools').scrollIntoView({behavior:'smooth',block:'start'});
 $('red-team-title').focus({preventScroll:true});
}
async function loadRedTeamCatalog(){
 $('red-team-retry').disabled=true;
 try{
  redTeamCatalog=await api('red-team-tools');
  const counts=redTeamCatalog.suite_counts;
  $('red-team-catalog-status').textContent=counts.tabular+' classifier tools · '+counts.regression+' regression tools · '+counts.language+' language probes';
  $('red-team-retry').hidden=true;
  const language=$('red-team-language-probes');language.replaceChildren();
  redTeamCatalog.entries.filter(entry=>entry.suite_id==='language').forEach(entry=>language.append(el('span',redTeamLabels[entry.tool_id]||entry.tool_id.replaceAll('_',' '),'pill muted')));
  $('red-team-separate').textContent=(redTeamCatalog.external_adapters||[]).map(item=>item.name).join(', ')+': separate adapter workflows, not integrated into this console. Public-export screening and multi-shadow experiments also use separate workflows.';
  renderRedTeamCards(redTeamDataset(),redTeamJob);
 }catch(error){$('red-team-catalog-status').textContent='Tool catalog unavailable: '+error.message;$('red-team-retry').hidden=false;}
 finally{$('red-team-retry').disabled=false;}
}
$('red-team-dataset').onchange=()=>redTeamRuns();
$('red-team-run').onchange=loadRedTeamRun;
$('red-team-train').onclick=()=>{const dataset=redTeamDataset();if(dataset?.configured)openTraining(dataset.id);};
$('red-team-retry').onclick=loadRedTeamCatalog;
refreshRedTeam();loadRedTeamCatalog();
