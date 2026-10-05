"""Frozen external attack inputs and independent comparison, never clearance."""
from __future__ import annotations
import copy
import hashlib
from pathlib import Path
from . import runtime
from .protocol import prepare_input,frozen_splits,compare_repetitions,UnsupportedProfile
from .execution import run_worker,source_snapshot
from .worker import validate_request
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes,parse_plan
from ..production_registration.profiles import profile_descriptor

FLAGS={**native.FLAGS,'assessment_eligible':False,'external_execution_attested':False}

def digest(value):return hashlib.sha256(canonical_bytes(value)).hexdigest()

def write(path,value):
    with Path(path).open('xb') as stream:stream.write(canonical_bytes(value)+b'\n')

def expected_binding():
    return {'schema':'mra-sacro-runtime-binding/v1','sacroml_version':runtime.SACRO_VERSION,
            'wheel_sha256':runtime.WHEEL_SHA256,'metadata_sha256':runtime.METADATA_SHA256,
            'package_sha256':digest(runtime.SOURCE_PINS),'source_files':len(runtime.SOURCE_PINS),
            'numerical_versions':dict(runtime.NUMERICAL_VERSIONS),'fixture_only':True,
            'production_authorized':False,'model_delivery':False}

def verify_worker(prepared,request,result):
    fields={'schema','status','prepared_sha256','runtime','versions','source_sha256','lock_sha256','cases',
            'fixture_only','can_clear','assessment_eligible','authorization_eligible','production_authorized'}
    if type(result) is not dict or set(result)!=fields:raise ValueError('Worker output fields rejected')
    expected={'schema':'mra-sacro-worker-output/v1','status':'completed','prepared_sha256':digest(prepared),
              'runtime':expected_binding(),'versions':request['versions'],'source_sha256':request['source_sha256'],
              'lock_sha256':request['lock_sha256'],'fixture_only':True,'can_clear':False,'assessment_eligible':False,
              'authorization_eligible':False,'production_authorized':False}
    if canonical_bytes({k:result[k] for k in expected})!=canonical_bytes(expected):raise ValueError('Worker binding rejected')
    if type(result['cases']) is not dict or set(result['cases'])!={'target','positive','null'}:raise ValueError('Missing required attack/control')
    compared={name:compare_repetitions(prepared,name,result['cases'][name]) for name in ('target','positive','null')}
    if compared['positive']['controls_satisfied'] is not True or compared['null']['controls_satisfied'] is not True:raise ValueError('Required attack controls failed')
    return compared

def run_comparison(blobs,*,profile_id,output,python,versions,lock_sha256):
    destination=native._new_output(output)
    result={'schema':'mra-sacro-comparison/v1','profile_id':profile_id,'status':'failed','error':None,
            'comparison':None,'process':None,**FLAGS}
    try:
        native_plan=parse_plan(blobs['plan.json'])
        descriptor=profile_descriptor(profile_id)
        if native_plan.source_sha256!=descriptor['expected_source_sha256']:
            raise ValueError('Requested profile does not match native bundle')
        prepared=prepare_input(blobs)
        if prepared['profile_id']!=profile_id:raise ValueError('Profile identity changed')
        source=source_snapshot()
        request={'schema':'mra-sacro-worker-request/v1','prepared':prepared,'versions':copy.deepcopy(versions),
                 'source_sha256':digest(source),'lock_sha256':lock_sha256}
        validate_request(request)
        plan={'schema':'mra-sacro-frozen-comparison/v1','prepared_sha256':digest(prepared),
              'source_sha256':digest(source),'lock_sha256':lock_sha256,'runtime_binding':expected_binding(),
              'runtime_versions':versions,'attack_parameters':dict(runtime.ATTACK_PARAMETERS),
              'protocol':prepared['protocol'],'splits':frozen_splits(prepared),'required_cases':['target','positive','null'],**FLAGS}
        write(destination/'plan.json',plan);write(destination/'input.json',request)
        result['plan_sha256']=digest(plan);result['prepared_sha256']=digest(prepared)
        execution=run_worker(python,destination/'input.json',destination/'worker')
        worker=execution.pop('result',None);result['process']=execution
        if execution['status']!='completed' or not execution['cleanup_confirmed']:
            result['status']=execution['status'];raise ValueError('External execution did not complete')
        comparison=verify_worker(prepared,request,worker)
        if source_snapshot()!=source:raise ValueError('Source changed after comparison')
        for filename,value in (('plan.json',plan),('input.json',request),('worker/worker.json',worker)):
            if native._read(destination/filename,16*1024*1024)!=canonical_bytes(value)+b'\n':
                raise ValueError('Frozen comparison artifact changed')
        result.update(status='completed',comparison=comparison,worker_output_sha256=digest(worker))
        write(destination/'comparison.json',comparison)
    except UnsupportedProfile as error:
        result.update(status='unsupported',error={'type':type(error).__name__,'code':error.code})
    except Exception as error:
        if result['status']=='completed':result['status']='failed'
        result['error']={'type':type(error).__name__,'stage':'external_comparison'}
    write(destination/'result.json',result)
    return result
