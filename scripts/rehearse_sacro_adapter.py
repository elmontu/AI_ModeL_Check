#!/usr/bin/env python3
"""Exercise seven fixed public classifier profiles; retain unsupported regression."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).absolute().parents[1]
if str(ROOT/'src') not in sys.path:sys.path.insert(0,str(ROOT/'src'))
_SPEC=importlib.util.spec_from_file_location('sacro_baseline',ROOT/'scripts/verify_build_baseline.py')
_BASELINE=importlib.util.module_from_spec(_SPEC);_SPEC.loader.exec_module(_BASELINE)
from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import canonical_bytes,strict_json,parse_plan
from model_release_assurance.production_evidence.replay import snapshot_native_bundle,artifact_manifest,replay_native_bundle
from model_release_assurance.production_registration.profiles import PROFILE_IDS,load_profile
from model_release_assurance.production_registration.workflow import prepare_native_input
from model_release_assurance.production_sacro.workflow import run_comparison,FLAGS,write,digest
from model_release_assurance.production_sacro.execution import source_snapshot,runtime_descriptor


def source_bindings(root):
    return {'package':source_snapshot(),'driver':hashlib.sha256(native._read(root/'scripts/rehearse_sacro_adapter.py',1024*1024)).hexdigest(),
            'manifest':hashlib.sha256(native._read(root/'deploy/sacro/windows-cp312.json',4*1024*1024)).hexdigest(),
            'requirements':hashlib.sha256(native._read(root/'deploy/sacro/windows-cp312.requirements.txt',128*1024)).hexdigest()}

def verified_input(native_root,profile_id,data_root):
    blobs=snapshot_native_bundle(native_root);plan=parse_plan(blobs['plan.json'])
    data=load_profile(profile_id,data_root=data_root,max_rows=max(128,len(plan.train_indices)+len(plan.calibration_indices)+len(plan.audit_indices)))
    _,expected_data,expected_plan=prepare_native_input(data,plan.seed)
    if blobs['dataset.json']!=expected_data or blobs['plan.json']!=expected_plan:raise ValueError('Pinned public source does not match saved candidate inputs')
    replay_native_bundle(blobs)
    return blobs

def load_runtime_manifest(root):
    raw=native._read(root/'deploy/sacro/windows-cp312.json',4*1024*1024);manifest=strict_json(raw,maximum=4*1024*1024)
    if manifest['schema']!='mra-sacro-windows-wheel-lock/v1' or manifest['sacroml_version']!='2.0.1' or manifest['production_authorized'] is not False:raise ValueError('Runtime lock rejected')
    versions={item['name']:item['version'] for item in manifest['artifacts']}
    if len(versions)!=len(manifest['artifacts']) or not 4<=len(versions)<=128:raise ValueError('Runtime lock roster rejected')
    return versions,hashlib.sha256(raw).hexdigest()

def run_rehearsal(*,output,python,benchmark=None,data_root=Path('D:/model_audit_data'),root=ROOT):
    root=Path(root).absolute()
    benchmark=Path(benchmark) if benchmark is not None else root/'.local/verification/prd13-registration-20261001/eight-profiles/cases'
    benchmark=benchmark.absolute();python=Path(python).absolute()
    for path in (benchmark,python):
        if not path.is_relative_to(root/'.local'):raise ValueError('Use fixture inputs and runtime under this government .local')
    destination=_BASELINE.prepare_output(root,output)
    report={'schema':'mra-sacro-rehearsal/v1','status':'failed','cases':[], 'errors':[],
            'coverage_complete':False,'all_research_datasets_tested':False,'source_unchanged':False,**FLAGS}
    try:
        versions,lock_sha256=load_runtime_manifest(root);source=source_bindings(root);descriptor=runtime_descriptor(python)
        report['source']=source;report['runtime']=descriptor
        write(destination/'batch-intent.json',{'schema':'mra-sacro-batch-intent/v1','profiles':list(PROFILE_IDS),
            'required_supported':[n for n in PROFILE_IDS if n!='sklearn-diabetes'],'required_unsupported':['sklearn-diabetes'],
            'source_sha256':digest(source),'runtime':descriptor,'lock_sha256':lock_sha256,
            'selection':'one_fixed_recipe_all_profiles_all_repetitions_no_outcome_selection',**FLAGS})
        (destination/'cases').mkdir()
        for name in PROFILE_IDS:
            item={'profile_id':name,'status':'failed','error':None};report['cases'].append(item)
            try:
                native_root=benchmark/name/'native';blobs=verified_input(native_root,name,data_root);frozen=artifact_manifest(blobs)
                result=run_comparison(blobs,profile_id=name,output=destination/'cases'/name,python=python,versions=versions,lock_sha256=lock_sha256)
                item.update(status=result['status'],error=result['error'])
                if name=='sklearn-diabetes':
                    if result['status']!='unsupported' or result['error']['code']!='regression_not_supported':raise ValueError('Regression must remain unsupported')
                elif result['status']=='completed':
                    from model_release_assurance.production_sacro.evidence import authenticate_comparison
                    admission=authenticate_comparison(native_root,destination/'cases'/name,output=destination/'cases'/name/'evidence')
                    if admission['status']!='accepted_bound_native_replay':raise ValueError('Evidence binding unavailable')
                    item['evidence_status']=admission['status']
                    item['target_summary']=result['comparison']['target']['summary']
                    item['controls_passed']=all(result['comparison'][n]['controls_satisfied'] is True for n in ('positive','null'))
                if artifact_manifest(snapshot_native_bundle(native_root))!=frozen:raise ValueError('Original bundle changed')
            except Exception as error:item.update(status='failed',error={'type':type(error).__name__,'stage':'profile_comparison'})
        report['source_unchanged']=source_bindings(root)==source and runtime_descriptor(python)==descriptor
        report['coverage_complete']=(len(report['cases'])==8 and all(
            (item['status']=='unsupported' and item['error'].get('code')=='regression_not_supported') if item['profile_id']=='sklearn-diabetes'
            else (item['status']=='completed' and item['error'] is None and item.get('controls_passed') is True and item.get('evidence_status')=='accepted_bound_native_replay') for item in report['cases']))
        if report['coverage_complete'] and report['source_unchanged']:report['status']='completed_with_unsupported'
    except Exception as error:report['errors'].append({'type':type(error).__name__,'stage':'rehearsal'})
    write(destination/'result.json',report);return report

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--python',required=True,type=Path)
    parser.add_argument('--benchmark',type=Path);parser.add_argument('--data-root',type=Path,default=Path('D:/model_audit_data'))
    args=parser.parse_args(argv)
    try:report=run_rehearsal(output=args.output,python=args.python,benchmark=args.benchmark,data_root=args.data_root)
    except (OSError,ValueError,_BASELINE.BaselineError) as error:
        print(json.dumps({'status':'refused','type':type(error).__name__}));return 2
    print(json.dumps({'status':report['status'],'cases':len(report['cases']),'coverage_complete':report['coverage_complete']}))
    return 0 if report['status']=='completed_with_unsupported' else 1

if __name__=='__main__':raise SystemExit(main())
