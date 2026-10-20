"""The staged, exactly-once complete-law Phase 7C public evaluator.

Call only through the durable execution store after its runtime freeze and
exclusive reservation. Each stage must be durably committed by the supplied
sink before the next is derived. A replay follows identical stages and compares
all captured bytes; it never creates a replacement history or new run identity.
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import math
import numpy as np
from .inputs import SOURCE_SHA256, capture_and_derive, canonical_bytes
from .numerics import fit_logistic, predict_certified, brier_mean, chronological_sum, arithmetic_error_account, NumericalError
from mra_rr_continuation.certificates import RRParameters, ResearchContext, build_certificate, verify_certificate, certificate_digest

N = 16384
HISTORY_ROWS = 294
TRAIN_ROWS = 238
SEED_DOMAIN = 'MRA-PUBLIC-PHASE7B-COMPLETE-LAW-20261013-v1'
SPEC_SHA256 = '93a124607498c5cec6a93d06b4e3648094b683983ae59518a7fd22169a62d915'
CONTRACT_SHA256 = 'f40128dfe794a9cd7ef8a95e1a09fb3cc17e53c3cc2cf47d216cad6742f0d159'
COMPARATORS = ('independent_rr','clean_matched_logistic','clean_persistence','clean_seasonal_naive','clean_expanding_month_rate','clean_expanding_logistic')
DOMAINS = ('moh','mas','msf')
PARAMETERS = RRParameters(1,Fraction(3),Fraction(9),Fraction(2,3))
AUTHORITY = {'authorization_effect':'none','agency_acceptance':'pending','agency_practical_margin':None}

class EvaluationError(ValueError):
    pass


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bindings(bindings):
    required = ('preregistration_id','scientific_specification_sha256','execution_contract_sha256','runtime_sha256','source_sha256')
    if type(bindings) is not dict or any(k not in bindings for k in required):
        raise EvaluationError('External registration/runtime/source bindings required')
    result = {k:bindings[k] for k in required}
    if (result['preregistration_id'] != '6cbfa4a1494cda5b73fe1652' or result['scientific_specification_sha256'] != SPEC_SHA256
            or result['execution_contract_sha256'] != CONTRACT_SHA256 or result['source_sha256'] != SOURCE_SHA256):
        raise EvaluationError('Frozen registration bindings differ')
    if type(result['runtime_sha256']) is not str or len(result['runtime_sha256']) != 64 or any(c not in '0123456789abcdef' for c in result['runtime_sha256']):
        raise EvaluationError('Invalid externally frozen runtime hash')
    return result


def seed_document(replication,purpose):
    if type(replication) is not int or not 0 <= replication < N or purpose not in ('retained','fresh'):
        raise EvaluationError('Unregistered stream identity')
    return {'seed_domain':SEED_DOMAIN,'scientific_specification_sha256':SPEC_SHA256,'domain':'mas','replication':replication,'purpose':purpose}


def _rng(replication,purpose):
    encoded=canonical_bytes(seed_document(replication,purpose))
    seed=int.from_bytes(hashlib.sha256(encoded).digest(),'big')
    return np.random.Generator(np.random.PCG64(seed))


def array_bytes(array,dtype):
    return np.asarray(array,dtype=dtype).tobytes(order='C')


@dataclass(frozen=True)
class RetainedInputs:
    bindings: dict
    tickets: np.ndarray
    responses: np.ndarray
    documents: tuple
    law: dict
    request: dict
    roster_sha256: str

    def artifacts(self):
        return {'retained-tickets.i64':array_bytes(self.tickets,'<i8'),'retained-responses.u8':array_bytes(self.responses,'u1'),
                'retained-contexts.json':canonical_bytes({'schema':'mra-phase7c-retained-contexts/1.0','replications':N,'rows':HISTORY_ROWS,'ordered_roster_sha256':self.roster_sha256,'law':self.law,'request':self.request,'histories':self.documents,**AUTHORITY}),
                'retained-array-layout.json':canonical_bytes({'shape':[N,HISTORY_ROWS],'retained-tickets.i64':'little_endian_signed_int64_C_order','retained-responses.u8':'unsigned_int8_C_order','outer_unit':'one_complete_independent_retained_history','one_fresh_vector_per_history':1})}


def derive_retained_inputs(frame,bindings):
    bindings=_bindings(bindings)
    roster=frame.keys[:HISTORY_ROWS]
    roster_sha=_sha(canonical_bytes(list(roster)))
    common={'bindings':bindings,'ordered_roster_sha256':roster_sha,'rows':HISTORY_ROWS,'domain':'mas'}
    law={**common,'schema':'mra-phase7c-public-retained-law/1.0','old_rr_correctness':'3/4','row_law':'independent_binary_RR_on_z','parameters':PARAMETERS.to_dict(),'premises':'declared_not_independently_verified','neighbor':'one_constructed_binary_pair_with_public_design_and_other_rows_fixed','product_whole_matrix_ratio_cap':'9^294','authorization_effect':'none'}
    request={**common,'schema':'mra-phase7c-public-fixed-request/1.0','candidate':'optimal_r1_conditional_9/10_7/10','independent_alternative':'fresh_binary_RR_ratio3','decoder_candidate':'(20b-3)/14','decoder_independent':'2b-1/2','validation_prefix':238,'predetermined_refit_prefix':294,'fresh_vectors_per_history':1,'alternative_channels_not_jointly_disclosed':True,'authorization_effect':'none'}
    law_sha=_sha(canonical_bytes(law)); request_sha=_sha(canonical_bytes(request))
    z=frame.z[:HISTORY_ROWS]
    tickets=np.empty((N,HISTORY_ROWS),dtype=np.int64)
    responses=np.empty((N,HISTORY_ROWS),dtype=np.uint8)
    docs=[]; seen=set()
    for replication in range(N):
        seed_sha=_sha(canonical_bytes(seed_document(replication,'retained')))
        if seed_sha in seen:
            raise EvaluationError('Stream identity collision')
        seen.add(seed_sha)
        tickets[replication]=_rng(replication,'retained').integers(0,4,size=HISTORY_ROWS,dtype=np.int64)
        responses[replication]=np.where(tickets[replication]<3,z,1-z)
        response={**common,'schema':'mra-phase7c-public-retained-response/1.0','replication':replication,'W':responses[replication].tolist()}
        response_sha=_sha(canonical_bytes(response))
        history={**common,'schema':'mra-phase7c-complete-public-history/1.0','replication':replication,'retained_response_sha256':response_sha,'old_coordinate_z':z.tolist(),'retained_blocks':1,'retained_response_W':responses[replication].tolist(),'no_previous_candidate_fresh_response':True}
        history_sha=_sha(canonical_bytes(history))
        # The expected context is constructed from externally fixed registration,
        # runtime and captured-input documents BEFORE accepting any certificate.
        context=ResearchContext(law_sha,response_sha,history_sha,request_sha)
        certificate=build_certificate(PARAMETERS,context,claim='optimal')
        digest=certificate_digest(certificate)
        verified=verify_certificate(certificate,expected_parameters=PARAMETERS,expected_context=context,expected_certificate_sha256=digest)
        if (verified.claim != 'optimal' or verified.conditional_accuracies != (Fraction(9,10),Fraction(7,10))
                or verified.marginal_accuracy != Fraction(17,20) or verified.shells != ((Fraction(27,40),Fraction(3,40)),(Fraction(7,40),Fraction(3,40)))):
            raise EvaluationError('Exact frozen optimal continuation law differs')
        docs.append({'replication':replication,'retained_seed_sha256':seed_sha,'response':response,'history':history,'externally_constructed_expected_context':context.to_dict(),'certificate':certificate,'certificate_sha256':digest,'verification':'exact_optimal_before_fresh_draw'})
    tickets.setflags(write=False); responses.setflags(write=False)
    return RetainedInputs(bindings,tickets,responses,tuple(docs),law,request,roster_sha)


@dataclass(frozen=True)
class FreshInputs:
    tickets: np.ndarray
    candidate_bits: np.ndarray
    independent_bits: np.ndarray

    def artifacts(self):
        return {'fresh-tickets.i64':array_bytes(self.tickets,'<i8'),'candidate-fresh.u8':array_bytes(self.candidate_bits,'u1'),'independent-fresh.u8':array_bytes(self.independent_bits,'u1'),
                'fresh-array-layout.json':canonical_bytes({'schema':'mra-phase7c-fresh-layout/1.0','shape':[N,HISTORY_ROWS],'fresh-tickets.i64':'little_endian_signed_int64_C_order','candidate-fresh.u8':'unsigned_int8_C_order','independent-fresh.u8':'unsigned_int8_C_order','ticket_bound':20,'seed_domain':SEED_DOMAIN,'seed_document_fields':['domain','purpose','replication','scientific_specification_sha256','seed_domain'],'draws_per_history':1,'purpose':'fresh','paired_common_tickets':True,'candidate_and_independent_are_alternatives':True,**AUTHORITY})}


def derive_fresh_inputs(frame,retained):
    if not isinstance(retained,RetainedInputs) or len(retained.documents) != N:
        raise EvaluationError('Captured retained histories required')
    y=frame.y[:HISTORY_ROWS]; z=frame.z[:HISTORY_ROWS]
    tickets=np.empty((N,HISTORY_ROWS),dtype=np.int64)
    candidate=np.empty((N,HISTORY_ROWS),dtype=np.uint8)
    independent=np.empty((N,HISTORY_ROWS),dtype=np.uint8)
    seen={_sha(canonical_bytes(seed_document(r,'retained'))) for r in range(N)}
    for r,doc in enumerate(retained.documents):
        # Reconstruct the context externally rather than loading its submitted copy.
        context=ResearchContext(_sha(canonical_bytes(retained.law)),_sha(canonical_bytes(doc['response'])),_sha(canonical_bytes(doc['history'])),_sha(canonical_bytes(retained.request)))
        verified=verify_certificate(doc['certificate'],expected_parameters=PARAMETERS,expected_context=context,expected_certificate_sha256=doc['certificate_sha256'])
        if verified.claim != 'optimal' or doc['response']['W'] != retained.responses[r].tolist():
            raise EvaluationError('Retained/certificate binding altered before draw')
        seed_sha=_sha(canonical_bytes(seed_document(r,'fresh')))
        if seed_sha in seen:
            raise EvaluationError('Retained/fresh stream collision')
        seen.add(seed_sha)
        tickets[r]=_rng(r,'fresh').integers(0,20,size=HISTORY_ROWS,dtype=np.int64)
        old_correct=retained.responses[r] == z
        candidate_threshold=np.where(old_correct,np.where(y == 1,18,2),np.where(y == 1,14,6))
        independent_threshold=np.where(y == 1,15,5)
        candidate[r]=(tickets[r]<candidate_threshold)
        independent[r]=(tickets[r]<independent_threshold)
    for a in (tickets,candidate,independent):
        a.setflags(write=False)
    return FreshInputs(tickets,candidate,independent)


def _decoder(bits,route):
    if route == 'candidate':
        exact=tuple(Fraction(20*int(b)-3,14) for b in bits)
    elif route == 'independent_rr':
        exact=tuple(Fraction(4*int(b)-1,2) for b in bits)
    elif route == 'clean':
        exact=tuple(Fraction(int(b)) for b in bits)
    else:
        raise EvaluationError('Unknown decoder route')
    return np.asarray(exact,dtype=np.float64),exact


def _ref_payload(name,X,exact_design,targets,exact_targets,fit,testX,test_exact,probabilities,truth):
    return {'route':name.split(':')[0],'cohort':name.split(':',1)[1],'X':X,'exact_design':exact_design,'targets':targets,'exact_targets':exact_targets,'beta':fit.beta,'evaluation_X':testX,'evaluation_exact_design':test_exact,'probabilities':probabilities,'evaluation_y':truth,'objective_lambda':'1/10'}


COST_GRID=(('1:4',Fraction(1,5)),('1:1',Fraction(1,2)),('4:1',Fraction(4,5)))


def _threshold_ceiling(a):
    """Least binary64 >= exact a; q>=this iff exact delivered q>=a."""
    threshold=float(a)
    if Fraction.from_float(threshold)<a:
        threshold=float(np.nextafter(threshold,math.inf))
    return threshold


def _cost_grid(predictions,truth):
    grid={};p=np.asarray(predictions,dtype=np.float64);y=np.asarray(truth)
    for ratio,a in COST_GRID:
        threshold=_threshold_ceiling(a)
        false_positive=int(np.count_nonzero((y == 0)&(p >= threshold)))
        false_negative=int(np.count_nonzero((y == 1)&(p < threshold)))
        exact=(a*false_positive+(1-a)*false_negative)/len(y)
        grid[ratio]={'threshold':f'{a.numerator}/{a.denominator}','normalized_mean_loss':float(exact),'normalized_mean_loss_exact':f'{exact.numerator}/{exact.denominator}','threshold_comparison':'exact_binary64_delivered_probability_against_exact_rational_a'}
    return grid


def _cost_vector(predictions,truth):
    grid=_cost_grid(predictions,truth)
    return np.array([grid[ratio]['normalized_mean_loss'] for ratio,a in COST_GRID],dtype=np.float64)


def evaluate_captured(frame,retained,fresh,progress_callback=None):
    from .verifier import prepare_exact_design
    if not isinstance(frame.y,np.ndarray) or fresh.candidate_bits.shape != (N,HISTORY_ROWS) or fresh.independent_bits.shape != (N,HISTORY_ROWS):
        raise EvaluationError('Complete captured inputs required')
    X=frame.X; exact=frame.exact_design; y=frame.y
    train=X[:238]; refit=X[:294]; validation=X[238:294]; final=X[294:]
    prepared={238:prepare_exact_design(train,exact_design=exact[:238]),294:prepare_exact_design(refit,exact_design=exact[:294])}
    val_prepared=prepare_exact_design(validation,exact_design=exact[238:294]); final_prepared=prepare_exact_design(final,exact_design=exact[294:])
    final_truth=y[294:]; validation_truth=y[238:294]
    models={}; reference_predictions={}; reference_payload=[]; certificates=[]
    clean_predictions={}; clean_validation={}
    for count,evalX,evalExact,evalTruth,suffix in ((238,validation,val_prepared,validation_truth,'validation'),(294,final,final_prepared,final_truth,'final')):
        targets,target_exact=_decoder(y[:count],'clean')
        fit=fit_logistic(X[:count],targets,exact_design=prepared[count],exact_targets=target_exact)
        p,pcert=predict_certified(evalX,fit,exact_design=evalExact)
        models[f'clean_matched_logistic:{suffix}']=fit.document()
        (clean_predictions if suffix == 'final' else clean_validation)['clean_matched_logistic']=p
        certificates.append({'fit':f'clean_matched_logistic:{suffix}',**fit.stationarity,'prediction':pcert})
        reference_payload.append(_ref_payload(f'clean_matched_logistic:{suffix}',X[:count],exact[:count],targets,target_exact,fit,evalX,exact[238:294] if suffix == 'validation' else exact[294:],p,evalTruth))
    expanding=np.empty(102,dtype=np.float64); expanding_models=[]
    for position in range(238,340):
        targets,target_exact=_decoder(y[:position],'clean')
        pdesign=prepare_exact_design(X[:position],exact_design=exact[:position])
        fit=fit_logistic(X[:position],targets,exact_design=pdesign,exact_targets=target_exact)
        p,pcert=predict_certified(X[position:position+1],fit,exact_design=exact[position:position+1])
        expanding[position-238]=p[0]
        expanding_models.append({'origin_key':frame.keys[position],**fit.document(),'prediction_certificate':pcert})
        certificates.append({'fit':f'clean_expanding_logistic:{frame.keys[position]}',**fit.stationarity,'prediction':pcert})
        reference_payload.append(_ref_payload(f'clean_expanding_logistic:{frame.keys[position]}',X[:position],exact[:position],targets,target_exact,fit,X[position:position+1],exact[position:position+1],p,y[position:position+1]))
    rates=np.empty(102,dtype=np.float64)
    for position in range(238,340):
        past=np.flatnonzero(frame.months[:position] == frame.months[position])
        rates[position-238]=float(Fraction(1+int(np.sum(y[past])),2+len(past)))
    deterministic={'clean_persistence':frame.z[238:].astype(np.float64),'clean_seasonal_naive':frame.seasonal[238:].astype(np.float64),'clean_expanding_month_rate':rates,'clean_expanding_logistic':expanding}
    for route,p in deterministic.items():
        clean_validation[route]=p[:56]; clean_predictions[route]=p[56:]
    clean_losses={route:brier_mean(p,final_truth) for route,p in clean_predictions.items()}
    clean_val_losses={route:brier_mean(p,validation_truth) for route,p in clean_validation.items()}
    losses=np.empty((N,7),dtype=np.float64)
    validation_losses=np.empty((N,7),dtype=np.float64)
    cost_vectors=np.empty((N,7,3),dtype=np.float64)
    clean_cost_vectors={route:_cost_vector(p,final_truth) for route,p in clean_predictions.items()}
    fit_records=np.empty((N,4,5),dtype=np.float64)
    all_coefficients=np.empty((N,4,29),dtype=np.float64)
    for r in range(N):
        for route,bitarray,column in (('candidate',fresh.candidate_bits,0),('independent_rr',fresh.independent_bits,1)):
            decoded,decoded_exact=_decoder(bitarray[r],route)
            for count,evalX,evalExact,evalTruth,suffix,record in ((238,validation,val_prepared,validation_truth,'validation',0),(294,final,final_prepared,final_truth,'final',1)):
                try:
                    fit=fit_logistic(X[:count],decoded[:count],exact_design=prepared[count],exact_targets=decoded_exact[:count])
                    p,pcert=predict_certified(evalX,fit,exact_design=evalExact)
                except Exception as exc:
                    raise EvaluationError(f'Frozen fit failed: replication={r}, route={route}, cohort={suffix}: {exc}') from exc
                all_coefficients[r,column*2+record]=fit.beta
                fit_records[r,column*2+record]=[fit.iterations,fit.float_gradient_norm,float(fit.stationarity['norm_upper']),float(fit.stationarity['arithmetic_uncertainty_upper']),float(pcert['maximum_absolute_error_upper'])]
                (validation_losses if suffix == 'validation' else losses)[r,column]=brier_mean(p,evalTruth)
                if suffix == 'final':
                    cost_vectors[r,column]=_cost_vector(p,final_truth)
                if r == 0:
                    models[f'{route}:{suffix}']=fit.document()
                    reference_predictions[f'{route}:{suffix}']=p.tolist()
                    certificates.append({'fit':f'{route}:{suffix}:replication0',**fit.stationarity,'prediction':pcert})
                    reference_payload.append(_ref_payload(f'{route}:{suffix}',X[:count],exact[:count],decoded[:count],decoded_exact[:count],fit,evalX,exact[238:294] if suffix == 'validation' else exact[294:],p,evalTruth))
        for column,route in enumerate(COMPARATORS[1:],2):
            losses[r,column]=clean_losses[route]
            validation_losses[r,column]=clean_val_losses[route]
            cost_vectors[r,column]=clean_cost_vectors[route]
        if progress_callback and (r+1)%256 == 0:
            progress_callback({'stage':'fits','completed_replications':r+1,'total_replications':N,'bookkeeping_batch_size':256})
    gains=losses[:,1:]-losses[:,0,None]
    means=[float(chronological_sum(gains[:,j])/N) for j in range(6)]
    # Highprecision outward radius + bounds supplied by independent verifier;
    # no display rounding influences strict zero-margin decisions.
    from .verifier import guarded_interval
    comparisons=[]
    mas_cells=[]
    for domain in DOMAINS:
        for j,route in enumerate(COMPARATORS):
            if domain != 'mas':
                comparisons.append({'domain':domain,'comparator':route,'verdict':'not_evaluable','mean_gain':None,'lower':None,'upper':None,'candidate_mean_brier':None,'comparator_mean_brier':None,'reason':'mandatory_domain_has_no_qualified_fresh_evaluation_frame'})
            else:
                interval=guarded_interval(means[j])
                cell={'domain':domain,'comparator':route,'mean_gain':means[j],**interval,'candidate_mean_brier':float(chronological_sum(losses[:,0])/N),'comparator_mean_brier':float(chronological_sum(losses[:,j+1])/N)}
                comparisons.append(cell); mas_cells.append(cell)
    overall='fail' if any(c['verdict']=='fail' for c in mas_cells) else 'not_evaluable'
    validation_summary={'candidate':float(chronological_sum(validation_losses[:,0])/N),'independent_rr':float(chronological_sum(validation_losses[:,1])/N),**clean_val_losses}
    summary={'schema':'mra-phase7c-evaluation/1.0','phase':'7C','bindings':retained.bindings,'overall_verdict':overall,'comparisons':comparisons,'mandatory_slots':18,'outer_trials':N,'one_fresh_vector_per_history':True,'final_frame_months':46,'validation_frame_months':56,'validation_descriptive_only':validation_summary,'reference_replication':0,'real_time_validity':'unresolved','all_domain_readiness':'not_evaluable','historically_unobserved_outcomes':False,'population_or_future_validity':'not_established','prior_phase6_observed_fail_preserved':True,'interval_scope':'fixed_historical_frame_complete_retained_plus_fresh_randomization_under_ideal_independent_tickets','pcg64_iid_proof':False,**AUTHORITY}
    reference_predictions['clean_final']={route:p.tolist() for route,p in clean_predictions.items()}
    reference_predictions['clean_validation']={route:p.tolist() for route,p in clean_validation.items()}
    reference_predictions['final_keys']=list(frame.keys[294:]); reference_predictions['final_truth']=final_truth.tolist()
    reference_predictions['validation_keys']=list(frame.keys[238:294]); reference_predictions['validation_truth']=validation_truth.tolist()
    costs={route:_cost_grid(p,final_truth) for route,p in clean_predictions.items()}
    costs.update({route:_cost_grid(reference_predictions[f'{route}:final'],final_truth) for route in ('candidate','independent_rr')})
    cost_differences=[]
    for domain in DOMAINS:
        for j,route in enumerate(COMPARATORS):
            for k,(ratio,a) in enumerate(COST_GRID):
                gain_vector=cost_vectors[:,j+1,k]-cost_vectors[:,0,k] if domain == 'mas' else None
                cost_differences.append({'domain':domain,'comparator':route,'false_positive_to_false_negative_cost':ratio,'threshold':f'{a.numerator}/{a.denominator}','complete_law_mean_comparator_minus_candidate_cost':None if gain_vector is None else float(chronological_sum(gain_vector)/N),'reference0_comparator_minus_candidate_cost':None if gain_vector is None else float(gain_vector[0]),'unsupported':domain != 'mas'})
    account=arithmetic_error_account()
    lines=['Phase 7C frozen complete-law public retrospective evaluation',f'Overall mandatory-domain result: {overall}', 'MOH and MSF: all twelve mandatory comparison slots not_evaluable; numeric statistics null.', 'MAS: 46 fixed historical monthly billings origins; 16384 independent complete-law outer units, one fresh vector each.', 'Validation means descriptive only. Family remains all18 slots; frozen margin0 and total numerical guard1e-9.', 'Intervals concern fixed-frame randomization integration under ideal independent tickets. PCG64 is a reproducible approximation, not an iid proof.', 'Historical real-time availability unresolved; observed source outcomes are not untouched validation.', 'Agency acceptance pending; practical margin null; certificate/usefulness grants no protected release authority.']
    for c in mas_cells:
        lines.append(f"MAS {c['comparator']}: {c['verdict']}; gain={c['mean_gain']:.12g}; band=[{c['lower']:.12g}, {c['upper']:.12g}]")
    artifacts={'evaluation.json':canonical_bytes(summary),'evaluation.txt':('\n'.join(lines)+'\n').encode('utf-8'),'reference-models.json':canonical_bytes({'schema':'mra-phase7c-reference-models/1.0','reference_replication':0,'models':models,'clean_expanding_origin_models':expanding_models,**AUTHORITY}),'reference-predictions.json':canonical_bytes(reference_predictions),'loss-vectors.f64':array_bytes(losses,'<f8'),'validation-loss-vectors.f64':array_bytes(validation_losses,'<f8'),'paired-gain-vectors.f64':array_bytes(gains,'<f8'),'fit-certification-summary.f64':array_bytes(fit_records,'<f8'),'all-randomized-coefficients.f64':array_bytes(all_coefficients,'<f8'),'descriptive-cost-vectors.f64':array_bytes(cost_vectors,'<f8'),'vector-layout.json':canonical_bytes({'loss-vectors.f64':{'shape':[N,7],'columns':['candidate',*COMPARATORS]},'validation-loss-vectors.f64':{'shape':[N,7],'columns':['candidate',*COMPARATORS]},'paired-gain-vectors.f64':{'shape':[N,6],'columns':list(COMPARATORS)},'descriptive-cost-vectors.f64':{'shape':[N,7,3],'route_order':['candidate',*COMPARATORS],'cost_ratio_order':['1:4','1:1','4:1'],'thresholds':['1/5','1/2','4/5']},'all-randomized-coefficients.f64':{'shape':[N,4,29],'fit_order':['candidate_validation','candidate_final','independent_validation','independent_final']},'fit-certification-summary.f64':{'shape':[N,4,5],'fit_order':['candidate_validation','candidate_final','independent_validation','independent_final'],'columns':['newton_iterations','float_gradient_l2','true_gradient_l2_upper','gradient_arithmetic_uncertainty_upper','prediction_absolute_error_upper']},'dtype':'little_endian_float64_C_order','all_trials_retained':True}), 'reference-stationarity.json':canonical_bytes(certificates),'numerical-error-account.json':canonical_bytes(account),'descriptive-cost-grid.json':canonical_bytes({'reference_replication':0,'scope':'hypothetical descriptive normalized cost grid only; no intervals, verdicts, threshold selection or agency margin','reference0_scores':costs,'comparator_minus_candidate_differences':cost_differences,'complete_law_integration':'same frozen16384outertrials and46equalweightedfinalorigins; descriptive only',**AUTHORITY})}
    return {'artifacts':artifacts,'summary':summary,'reference_payload':{'fits':reference_payload,'slots':comparisons}}


def run_staged(captured_source,bindings,sink):
    bindings=_bindings(bindings)
    frame=capture_and_derive(captured_source,expected_sha256=bindings['source_sha256'])
    sink.commit_stage('cohorts',frame.artifacts())
    retained=derive_retained_inputs(frame,bindings)
    sink.commit_stage('retained',retained.artifacts())
    fresh=derive_fresh_inputs(frame,retained)
    sink.commit_stage('fresh',fresh.artifacts())
    result=evaluate_captured(frame,retained,fresh,progress_callback=getattr(sink,'progress',None))
    sink.commit_stage('results',result['artifacts'])
    return {'summary':result['summary'],'reference_payload':result['reference_payload']}
