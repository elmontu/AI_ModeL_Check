// Explain retained assessment reports. This view never assesses or changes a verdict.
const assessmentReportPaths=new Set(['job/artifacts/assessment-report.json','job/artifacts/assessment/assessment-report.json','assessment/assessment-report.json']);
const assessmentValue=value=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString(undefined,{maximumSignificantDigits:6}):'Not recorded';
function assessmentHelpCurrent(panel,job){return panel.isConnected&&selectedJob===job.id;}
function assessmentGuideLink(){const link=el('a','Running guide: results and next steps →','table-action');link.href='/guide#results';link.target='_blank';link.rel='noopener';return link;}
function renderAssessmentHelp(panel,job,report,path){
 const expected=job.result.verdict||job.result.assessment_verdict;
 if(!report||!Array.isArray(report.decisions)||!report.decisions.length||report.overall_verdict!==expected){
  panel.append(el('p','The saved report is unavailable or does not match this run’s recorded verdict. Inspect the full evidence; this view has not recomputed an assessment.','operator-note'));return;
 }
 panel.append(el('p','Recorded assessment: '+report.overall_verdict+'. These explanations come from the retained report, not a new assessment. Displayed numbers are rounded.','operator-note'));
 if(report.overall_verdict==='clear')panel.append(el('p','Scientific clearance within the recorded scope. Release authorization: not granted.','detail-warning'));
 const declaredFiles=report.release_interface?.output_channels?.downloadable_files;
 if(Array.isArray(declaredFiles))panel.append(el('p','Assessed recipient files: '+declaredFiles.map(String).join(', '),'operator-note'));
 if(report.assessment_scope)panel.append(el('p','Composition scope: '+String(report.assessment_scope.composition_scope||'not recorded')+'. Other released models and operator evidence are outside this single-run explanation.','operator-note'));
 if(job.kind==='training'&&job.options?.preset==='dp-histogram'&&Array.isArray(declaredFiles)&&declaredFiles.length===1&&declaredFiles[0]==='recipient-package.json'){
  const modelLink=el('a','Download verified recipient model','secondary');modelLink.href='/api/jobs/'+encodeURIComponent(job.id)+'/recipient-package';modelLink.download='recipient-package.json';panel.append(modelLink,el('p','This download rechecks the retained mechanism and exact package. The operator evidence ZIP is a separate audit bundle and is not the assessed recipient package.','operator-note'));
 }
 if(path){const link=el('a','Download assessment report JSON','secondary');link.href='/api/jobs/'+encodeURIComponent(job.id)+'/artifacts/'+path.split('/').map(encodeURIComponent).join('/');link.download='assessment-report.json';panel.append(link);}
 report.decisions.forEach(decision=>{
  const section=el('div',undefined,'assessment-decision');
  section.append(el('h4',decision.threat_id||'Recorded threat'));
  const population=(Array.isArray(report.population_scopes)?report.population_scopes:[]).find(scope=>scope?.scope_id===decision.population_scope_id);
  if(population)section.append(el('p','Protected unit: '+String(population.unit_kind)+' · '+String(population.name),'operator-note'));
  section.append(el('p',(decision.decision_metric==='membership_tpr_at_fpr'?'Membership true-positive rate at the registered false-positive rate':decision.decision_metric||'Metric not recorded')+' · '+(decision.verdict||'Verdict not recorded'),'operator-note'));
  const facts=el('div',undefined,'dataset-facts');
  [['Accepted lower bound',decision.lower_bound],['Accepted upper bound',decision.upper_bound],['Policy tolerance',decision.tolerance]].forEach(([label,value])=>{const fact=el('div');fact.append(el('span',label),el('strong',assessmentValue(value)));facts.append(fact);});
  section.append(facts);
  const reasons=el('ul');(Array.isArray(decision.reasons)?decision.reasons:[]).forEach(reason=>reasons.append(el('li',String(reason))));section.append(reasons);
  const evidenceIds=new Set(Array.isArray(decision.evidence_ids)?decision.evidence_ids:[]);
  const evidence=(Array.isArray(report.evidence)?report.evidence:[]).filter(item=>item&&evidenceIds.has(item.evidence_id)&&item.threat_id===decision.threat_id&&item.population_scope_id===decision.population_scope_id&&item.metric===decision.decision_metric);
  evidence.forEach(item=>{
   const details=item.details||{};
   section.append(el('p','Evidence class: '+(item.evidence_class||'not recorded')+' · coverage: '+(item.coverage||'not recorded'),'operator-note'));
   if(item.analyzer==='dp'){
    section.append(el('p','Mechanism-derived membership ceiling at false-positive rate '+assessmentValue(details.fpr)+'. Attack scores do not supply this bound.','operator-note'));
    (Array.isArray(item.assumptions)?item.assumptions:[]).forEach(assumption=>section.append(el('p',String(assumption),'operator-note')));
   }else if(decision.decision_metric==='membership_tpr_at_fpr'){
    section.append(el('p','Registered false-positive target: '+assessmentValue(details.target_fpr)+' · recorded conservative false-positive upper bound: '+assessmentValue(details.one_sided_fpr_upper),'operator-note'));
    if(typeof details.operating_point_attained==='boolean')section.append(el('p',details.operating_point_attained
     ?(item.evidence_class==='floor'&&item.can_block===true
      ?'The registered operating point was attained. A valid attack floor can demonstrate a violation when it exceeds the policy tolerance; it cannot establish an upper bound.'
      :'The registered operating point was attained, but this evidence is not an eligible blocking floor. Check its evidence class and limitations; attaining the operating point alone does not establish validity.')
     :'The registered operating point was not established. This evidence is a screen and does not supply a decision-valid blocking floor at that target.','operator-note'));
   }
   (Array.isArray(item.limitations)?item.limitations:[]).forEach(limit=>section.append(el('p',String(limit),'operator-note')));
  });
  const mode=decision.ceiling_attack_battery?.mode;
  if(mode==='ceiling_prohibited')section.append(el('p','This policy prohibits ceiling-based clearance. A legitimate exact result may establish clearance; accepting a ceiling requires an approved policy change and its required evidence. The generic action text below does not override that restriction.','detail-warning'));
  else if(mode)section.append(el('p','Recorded ceiling/battery policy: '+mode,'operator-note'));
  if(mode==='waived')section.append(el('p','Recorded battery waiver: '+String(decision.ceiling_attack_battery.waiver_reason||'No reason recorded'),'detail-warning'));
  const resolution=decision.resolution;
  if(resolution){section.append(el('h4','Recorded next action'));
   (Array.isArray(resolution.actions)?resolution.actions:[]).forEach(action=>section.append(el('p',String(action),'operator-note')));
   (Array.isArray(resolution.missing_obligations)?resolution.missing_obligations:[]).forEach(item=>section.append(el('p','Missing obligation: '+String(item),'operator-note')));
  }
  panel.append(section);
 });
 panel.append(el('p','Training utility, exploratory attack results, Education-mode document warnings and the government checklist are separate from these scientific bounds. Repeating checks or adding documents alone does not establish clearance.','operator-note'));
 panel.append(assessmentGuideLink());
}
async function loadAssessmentHelp(panel,job){
 try{
  let report=job.result.report&&typeof job.result.report==='object'&&!Array.isArray(job.result.report)?job.result.report:null,path=null;
  if(report)path='assessment/assessment-report.json';
  else{
   const inventory=await api('jobs/'+encodeURIComponent(job.id)+'/artifacts');
   if(!assessmentHelpCurrent(panel,job))return;
   const matches=(inventory.files||[]).filter(item=>assessmentReportPaths.has(item.path));
   if(matches.length!==1||matches[0].size_bytes>2000000)throw Error('A single supported saved assessment report is not available. Browse the run evidence for its original reports.');
   path=matches[0].path;
   report=await api('jobs/'+encodeURIComponent(job.id)+'/artifacts/'+path.split('/').map(encodeURIComponent).join('/'));
  }
  if(!assessmentHelpCurrent(panel,job))return;
  panel.querySelector('.assessment-loading')?.remove();
  renderAssessmentHelp(panel,job,report,path);
 }catch(error){
  if(!assessmentHelpCurrent(panel,job))return;
  panel.querySelector('.assessment-loading')?.remove();
  panel.append(el('p',error.message,'operator-note'),assessmentGuideLink());
 }
}
function appendAssessmentExplanation(box,job){
 if(job.state!=='completed'||!['training','assess'].includes(job.kind))return;
 const verdict=job.result?.verdict||job.result?.assessment_verdict;
 if(!['inconclusive','clear','block'].includes(verdict))return;
 const panel=el('section',undefined,'assessment-explanation');
 panel.setAttribute('aria-label','Assessment explanation');
 panel.append(el('h3',verdict==='inconclusive'?'Why this assessment is inconclusive':verdict==='clear'?'Scientific clearance within the recorded scope':'Understand this assessment'),el('p','Loading the retained assessment report…','operator-note assessment-loading'));
 box.append(panel);loadAssessmentHelp(panel,job);
}
