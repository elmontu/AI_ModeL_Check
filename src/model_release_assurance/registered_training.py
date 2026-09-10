"""Frozen, source-bound membership evidence for public classifier adapters."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import json
import io
from .models import (PopulationScope, ThreatContract, StatisticalFloorDesignRegistration,
    StatisticalFloorFamilyPlan, StatisticalFloorFamilyMember, PolicyBundle, PolicyRule,
    AnalyzerRequirement, ReleaseContract, EvidenceContext, EvidenceProducer, AttackInput,
    AssessmentRequest, PolicyReference)
from .integrity import canonical_json_bytes, sha256_bytes
from .decision import decision_game_sha256, population_scope_sha256
from .analyzers.base import statistical_floor_design_sha256
from .services import default_analyzer_service_registry
from .engine import AssuranceEngine
from .workflow import digest, write_json
TARGET_FPR=.1
MEMBERSHIP_TOLERANCE=.2

def _iso(value): return value.isoformat().replace("+00:00","Z")
def now(): return datetime.now(timezone.utc)
def save(path,value):
    write_json(path,value.model_dump(mode="json") if hasattr(value,"model_dump") else value)

def _build_population_scope(
    dataset_sha256: str,
    metadata: dict[str, Any],
    frozen_at: datetime,
) -> PopulationScope:
    return PopulationScope.model_validate(
        {
            "scope_id": "training-demo-records",
            "name": f"Rows in the hash-bound {metadata['name']} teaching snapshot",
            "unit_kind": "record",
            "custom_unit_definition": None,
            "universe_definition": (
                "Exactly the rows in the dataset snapshot named by population_snapshot_sha256; "
                "no inference is made about a current healthcare population."
            ),
            "inclusion_criteria": ["present in the hash-bound input snapshot"],
            "exclusion_criteria": [],
            "jurisdictions": ["public teaching dataset; jurisdiction not asserted"],
            "reference_date": frozen_at.date().isoformat(),
            "valid_until": None,
            "population_snapshot_sha256": dataset_sha256,
            "size": {
                "basis": "exact_registry",
                "lower_bound": int(metadata["rows"]),
                "point_estimate": int(metadata["rows"]),
                "upper_bound": int(metadata["rows"]),
                "source": "row count replayed from the hash-bound dataset snapshot",
                "measured_at": _iso(frozen_at),
            },
            "subgroup_dimensions": [],
            "data_steward": "Public-data demo operator",
            "notes": "Integration-demo scope only; not an approved health-data population.",
        }
    )

def _build_threat(scope_id: str) -> ThreatContract:
    return ThreatContract.model_validate(
        {
            "threat_id": "membership-record",
            "kind": "membership",
            "mandatory": True,
            "secret": "whether one hash-bound record was used to train the target model",
            "prior": "attack TPR is evaluated at the separately controlled false-positive rate",
            "side_information": [
                "candidate record and true label",
                "predictions from the packaged full-artifact model",
                "complete schema and exact dataset summary metadata",
                "registered model family and hyperparameters",
            ],
            "adversary_metadata_profile": "exact_database_feature_summaries_v1",
            "success_metric": f"membership true-positive rate at FPR <= {TARGET_FPR}",
            "decision_metric": "membership_tpr_at_fpr",
            "metric_parameters": {"target_fpr": TARGET_FPR},
            "finite_game": None,
            "tolerance": MEMBERSHIP_TOLERANCE,
            "tolerance_basis": "absolute",
            "harm_rationale": (
                "Training membership can reveal association with a sensitive medical dataset; "
                "the public teaching run demonstrates the mechanism, not actual patient harm."
            ),
            "population_scope_id": scope_id,
            "candidate_set": None,
            "target_signal_source": None,
            "realizability": "not_applicable",
        }
    )

def _build_interface() -> dict[str, Any]:
    return {
        "schema_version": "3.0",
        "protocol_type": "predictive",
        "access": "full_artifact",
        "outputs": ["predicted class", "class probabilities"],
        "output_channels": {
            "aggregates": False,
            "labels": True,
            "scores": False,
            "probabilities": True,
            "logits": False,
            "explanations": False,
            "text": False,
            "embeddings": False,
            "gradients": False,
            "parameters": True,
            "downloadable_files": ["model.joblib"],
            "shipped_summary_metadata": [],
            "custom_channels": [],
        },
        "precision_bits": 64,
        "query_budget": None,
        "adaptive_queries": False,
        "authenticated": False,
        "rate_limited": False,
        "rate_limit": {
            "enabled": False,
            "scope": "none",
            "requests_per_window": None,
            "window_seconds": None,
            "burst_capacity": None,
            "retry_after_exposed": False,
            "enforcement": "not_applicable",
            "custom_parameters": {},
        },
        "timing": {
            "recipient_observable": False,
            "measurement_resolution_milliseconds": None,
            "includes_queue_time": False,
            "mitigation": "not_applicable",
            "mitigation_parameters": {},
        },
        "errors": {
            "transport_status": "none",
            "documented_status_codes": [],
            "error_content": "none",
            "error_schema_sha256": None,
            "retry_metadata": False,
        },
        "execution": {
            "batching": "recipient_controlled",
            "maximum_batch_size": None,
            "maximum_concurrent_requests": None,
            "cross_request_state": "none",
            "cross_request_state_ttl_seconds": None,
        },
        "access_paths": {
            "side_channels": [],
            "custom_side_channels": [],
            "admin_access": "none",
            "admin_capabilities": [],
            "local_access": "artifact_only",
            "local_capabilities": ["read and execute the complete packaged model"],
        },
        "serialization": {
            "formats": ["joblib"],
            "media_types": ["application/octet-stream"],
            "encodings": ["binary"],
            "compression": ["none"],
            "schema_sha256": None,
            "endianness": "not_applicable",
        },
        "llm_protocol": None,
        "notes": "Teaching bundle only; joblib must be loaded only in a trusted worker.",
    }

def prepare(output, metadata, members, nonmembers):
    if min(members,nonmembers)<1: raise ValueError("empty audit partition")
    timestamp=now(); snapshot=digest(output/'public-dataset.npz')
    sources=output/'source-snapshots';sources.mkdir()
    for name in ('registered_training.py','public_models.py','tiny_cnn.py'):
        (sources/name).write_bytes(Path(__file__).with_name(name).read_bytes())
    from .workflow import doctor
    save(output/'training-runtime.json',doctor())
    scope=_build_population_scope(snapshot,metadata,timestamp);threat=_build_threat(scope.scope_id)
    save(output/'population-scope.json',scope);save(output/'threat.json',threat)
    descriptor=next(s.descriptor for s in default_analyzer_service_registry().services if s.descriptor.input_kind=='attack')
    registration=StatisticalFloorDesignRegistration(registration_id='public-classifier-family:loss',analyzer='attack',threat_id=threat.threat_id,
        population_scope_id=scope.scope_id,member_id='loss',decision_metric='membership_tpr_at_fpr',registered_at=now(),
        dataset_snapshot_sha256=snapshot,procedure_sha256=digest(Path(__file__)),execution_plan_sha256=digest(output/'training-config.json'),
        random_seed=3407,stopping_rule='One fixed split; threshold is the higher 90th percentile of calibration nonmember negative losses; strict >; no outcome-based selection',
        planned_primary_trials=members,planned_control_trials=nonmembers,target_fpr=TARGET_FPR,notes='Public educational registration, no institutional authority')
    save(output/'registration.json',registration)
    design={'analyzer':'attack','threat_id':threat.threat_id,'population_scope_id':scope.scope_id,'attack_name':'loss',
            'preregistration_sha256':digest(output/'registration.json'),'metric':'membership_tpr_at_fpr','trials':members,
            'confidence':.95,'comparison_family_size':1,'calibration_disjoint':True,'audit_disjoint':True,
            'raw_counts_retained':True,'threshold_pre_registered':True,'nonmember_trials':nonmembers,'target_fpr':TARGET_FPR}
    family=StatisticalFloorFamilyPlan(family_id='public-classifier-family',analyzer='attack',threat_id=threat.threat_id,
        decision_metric='membership_tpr_at_fpr',members=(StatisticalFloorFamilyMember(member_id='loss',registration_path='registration.json',
        registration_sha256=digest(output/'registration.json'),input_design_sha256=statistical_floor_design_sha256(design)),),
        familywise_confidence=.95,multiplicity_method='bonferroni',frozen_at=now(),authority='Educational fixed plan; not agency approval')
    save(output/'family-plan.json',family)
    save(output/'selection-policy.json',{'rule':'No selection or release authorization; ceiling evidence remains required'})
    policy=PolicyBundle(policy_id='public-model-membership',policy_version='1.0.0',effective_from=timestamp-timedelta(seconds=1),expires_at=None,
        rules=(PolicyRule(threat_id=threat.threat_id,kind='membership',mandatory=True,decision_metric='membership_tpr_at_fpr',
        metric_parameters={'target_fpr':TARGET_FPR},finite_game=None,tolerance=.2,tolerance_basis='absolute',
        ceiling_attack_battery_mode='ceiling_prohibited',ceiling_attack_battery_waiver_reason=None),),
        analyzer_requirements=(AnalyzerRequirement(threat_id=threat.threat_id,analyzer='attack',minimum_service_version=descriptor.service_version,
        accepted_implementation_sha256s=(descriptor.implementation_sha256,),accepted_configuration_sha256s=(digest(output/'family-plan.json'),),required=True),),
        attack_battery_requirements=(),accepted_selection_policy_sha256s=(digest(output/'selection-policy.json'),))
    save(output/'policy.json',policy)
    frozen_names=['public-dataset.npz','training-config.json','data-manifest.json','training-runtime.json',
                  'population-scope.json','threat.json','registration.json','family-plan.json','selection-policy.json','policy.json',
                  'source-snapshots/registered_training.py','source-snapshots/public_models.py','source-snapshots/tiny_cnn.py']
    frozen={name:digest(output/name) for name in frozen_names}
    save(output/'evidence-freeze.json',{'format_version':'public-evidence-freeze/1','frozen_at':_iso(now()),'files':frozen})
    frozen['evidence-freeze.json']=digest(output/'evidence-freeze.json')
    return {'scope':scope,'threat':threat,'descriptor':descriptor,'design':design,'policy':policy,'family':family,'frozen':frozen}


def verify_local_training_evidence(request, base, verification_sha256=None, request_sha256=None):
    """Replay the retained local counts and bindings without unpickling any model.

    This verifies local scientific bookkeeping, not provenance from an agency or
    execution attestation. Generic external evidence stays under Engine checks.
    """
    import numpy as np
    from .integrity import read_verified_source_bytes
    base=base.resolve()
    for attack in request.analyzer_inputs:
        if attack.provenance.tool != 'public-classifier-loss': continue
        source=json.loads(read_verified_source_bytes(attack.provenance.source_path,attack.provenance.source_sha256,base))
        # Older local runs did not retain replay bindings. Their engine evidence
        # remains usable, but cannot acquire the stronger new local replay claim.
        if attack.provenance.tool_version == '1.0.0': continue
        if verification_sha256 is None: raise ValueError('bind the local training replay manifest before assessment')
        verification=json.loads(read_verified_source_bytes('training-verification.json',verification_sha256,base))
        if verification['request_sha256']!=request_sha256: raise ValueError('local replay manifest targets a different request')
        if verification.get('format_version') != 'public-training-verification/1':
            raise ValueError('unsupported local training verification format')
        captured={}
        for name,expected in verification['files'].items():
            path=(base/name).resolve()
            if not path.is_relative_to(base): raise ValueError('local training evidence path escapes its bundle')
            captured[name]=read_verified_source_bytes(name,expected,base)
        required={'public-dataset.npz','training-config.json','data-manifest.json','training-runtime.json',
                  'population-scope.json','threat.json','registration.json','family-plan.json','selection-policy.json','policy.json',
                  'evidence-freeze.json','source-snapshots/registered_training.py','source-snapshots/public_models.py',
                  'source-snapshots/tiny_cnn.py','registered-attack-scores.npz','export-verification.json'}
        if not required.issubset(captured): raise ValueError('local training replay bindings are incomplete')
        registration=json.loads(captured['registration.json'])
        freeze=json.loads(captured['evidence-freeze.json'])
        for name,expected in freeze['files'].items():
            if verification['files'].get(name)!=expected: raise ValueError('frozen evidence binding changed')
        if registration['dataset_snapshot_sha256']!=verification['files']['public-dataset.npz']:
            raise ValueError('registered dataset differs from replay snapshot')
        if registration['execution_plan_sha256']!=verification['files']['training-config.json']:
            raise ValueError('registered training recipe differs from replay recipe')
        if registration['procedure_sha256']!=verification['files']['source-snapshots/registered_training.py']:
            raise ValueError('registered procedure differs from retained source')
        if not (registration['registered_at'] <= freeze['frozen_at'] <= verification['training_started_at'] <= verification['training_completed_at'] <= source['evidence_context']['observed_at']):
            raise ValueError('registration, training and observation chronology is inconsistent')
        exported=json.loads(captured['export-verification.json'])
        if exported['candidate_sha256']!=request.release.artifact_sha256 or not exported['preprocessing_identical'] or not exported['predictions_identical']:
            raise ValueError('recipient bundle export verification failed')
        with np.load(io.BytesIO(captured['public-dataset.npz']),allow_pickle=False) as snapshot:
            train=np.asarray(snapshot['train']);test=np.asarray(snapshot['test'])
            calibration=np.asarray(snapshot['calibration']);audit=np.asarray(snapshot['audit'])
            if len(snapshot['x'])!=len(snapshot['y']): raise ValueError('snapshot features and labels differ in length')
            if sorted(np.concatenate([train,test]).tolist())!=list(range(len(snapshot['y']))):
                raise ValueError('training and nonmember partitions do not uniquely cover the snapshot')
            if not np.array_equal(np.concatenate([calibration,audit]),test) or len(calibration)!=len(test)//2:
                raise ValueError('calibration and audit partitions differ from the frozen rule')
            counts=(len(train),len(calibration),len(audit))
        with np.load(io.BytesIO(captured['registered-attack-scores.npz']),allow_pickle=False) as scores:
            arrays=[np.asarray(scores[name]) for name in ('member','calibration','audit')]
            if any(a.ndim!=1 or len(a)!=count or not np.isfinite(a).all() for a,count in zip(arrays,counts)):
                raise ValueError('raw membership scores do not match finite disjoint trial arrays')
            member,calibration,audit=arrays
            if not len(calibration): raise ValueError('missing calibration scores')
            threshold=float(np.quantile(calibration,.9,method='higher'))
            if source['trials']!=len(member) or source['nonmember_trials']!=len(audit) or source['successes']!=int((member>threshold).sum()) or source['false_positives']!=int((audit>threshold).sum()):
                raise ValueError('registered counts do not replay from retained raw scores')
            if verification['threshold']!=threshold: raise ValueError('retained threshold does not replay')


def assess(output, plan, model, train_x, train_y, test_x, test_y, preset, regression=False):
    import numpy as np
    for name,expected in plan['frozen'].items():
        if digest(output/name)!=expected: raise ValueError('preregistered input changed during training: '+name)
    candidate=output/'model.joblib'; candidate_hash=digest(candidate)
    interface=_build_interface()
    if regression:
        interface['outputs']=['numeric prediction'];interface['output_channels']['labels']=False
        interface['output_channels']['probabilities']=False;interface['output_channels']['scores']=True
    release=ReleaseContract.model_validate({'release_id':preset+'-'+candidate_hash[:16],'owner':'Public teaching operator',
        'recipient':'Local trusted tester','purpose':'Evaluate public sample model; no production authorization',
        'model_family': {'logistic':'linear_generalized_linear','random-forest':'tree_ensemble','mlp':'tabular_neural_network','mlp-finetuned':'tabular_neural_network','cnn':'convolutional_neural_network','svm':'kernel_method','ensemble':'ensemble_composite','ridge':'linear_generalized_linear','forest-regression':'tree_ensemble'}[preset],
        'model_profile':{'task':'regression' if regression else 'classification','input_modalities':['tabular'],'output_modalities':['tabular'],'training_paradigm':'supervised',
        'component_model_families':['linear_generalized_linear','tree_ensemble'] if preset=='ensemble' else [],'generative':False,'stateful':False,'custom_task_definition':None},
        'protected_unit':'record','artifact_path':'model.joblib','artifact_sha256':candidate_hash,'interface':interface,
        'previous_release_ids':[],'expires_at':_iso(now()+timedelta(days=30))})
    save(output/'release-contract.json',release)
    def scores(x,y):
        if regression: return -np.square(np.asarray(model.predict(x))-np.asarray(y))
        p=np.asarray(model.predict_proba(x));columns={label:i for i,label in enumerate(model.classes_)}
        indices=np.asarray([columns[label] for label in y],dtype=int)
        return np.log(np.clip(p[np.arange(len(y)),indices],1e-12,1))
    member=scores(train_x,train_y);nonmember=scores(test_x,test_y);cut=len(nonmember)//2
    calibration=nonmember[:cut];audit=nonmember[cut:]
    threshold=float(np.quantile(calibration,.9,method='higher'))
    np.savez_compressed(output/'registered-attack-scores.npz',member=member,calibration=calibration,audit=audit)
    context=EvidenceContext(release_id=release.release_id,release_contract_sha256=sha256_bytes(canonical_json_bytes(release)),
        policy_sha256=digest(output/'policy.json'),artifact_sha256=candidate_hash,interface_sha256=sha256_bytes(canonical_json_bytes(release.interface)),
        population_scope_id=plan['scope'].scope_id,population_scope_sha256=population_scope_sha256(plan['scope']),
        decision_game_sha256=decision_game_sha256(plan['threat'],plan['scope']),observed_at=now())
    payload={**plan['design'],'successes':int((member>threshold).sum()),'false_positives':int((audit>threshold).sum()),'evidence_context':context.model_dump(mode='json')}
    verification={'format_version':'public-training-verification/1','files':{**plan['frozen'],
                  'registered-attack-scores.npz':digest(output/'registered-attack-scores.npz'),
                  'export-verification.json':digest(output/'export-verification.json')},
                  'threshold':threshold,'training_started_at':plan['training_started_at'],
                  'training_completed_at':plan['training_completed_at']}
    save(output/'attack-source.json',payload)
    descriptor=plan['descriptor']
    producer=EvidenceProducer(service_id=descriptor.service_id,service_version=descriptor.service_version,
        implementation_sha256=descriptor.implementation_sha256,configuration_sha256=digest(output/'family-plan.json'))
    attack=AttackInput.model_validate({**payload,'provenance':{'tool':'public-classifier-loss','tool_version':'1.1.0','producer':producer.model_dump(mode='json'),
        'configuration_path':'family-plan.json','source_path':'attack-source.json','source_sha256':digest(output/'attack-source.json'),'bound_fields':list(payload)}})
    request=AssessmentRequest(policy=PolicyReference(policy_id=plan['policy'].policy_id,policy_version='1.0.0',policy_path='policy.json',policy_sha256=digest(output/'policy.json')),
        release=release,population_scopes=(plan['scope'],),threats=(plan['threat'],),analyzer_inputs=(attack,))
    save(output/'assessment-request.json',request)
    verification['request_sha256']=digest(output/'assessment-request.json')
    save(output/'training-verification.json',verification)
    verify_local_training_evidence(request,output,digest(output/'training-verification.json'),verification['request_sha256'])
    report=AssuranceEngine().assess(request,output)
    if report.overall_verdict.value=='clear': raise ValueError('floor-only assessment cannot clear')
    if digest(candidate)!=candidate_hash: raise ValueError('candidate changed during assessment')
    save(output/'assessment-report.json',report)
    save(output/'registered-measurements.json',{'threshold':threshold,'calibration_records':cut,'member_successes':payload['successes'],
        'member_trials':len(member),'false_positives':payload['false_positives'],'nonmember_trials':len(audit),
        'raw_scores_sha256':digest(output/'registered-attack-scores.npz'),'candidate_sha256':candidate_hash,
        'independent_institutional_review':False,'scope':'one registered membership attack; other threats remain exploratory'})
    return report
