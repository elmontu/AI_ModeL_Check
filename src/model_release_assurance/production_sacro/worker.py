"""Trusted bounded child entry point; no model deserialization or signing keys."""
from __future__ import annotations
import hashlib
import importlib.metadata
from pathlib import Path
import sys
from .protocol import validate_input
from .runtime import runtime_binding,run_attack
from .execution import MAX_INPUT,MAX_OUTPUT,source_snapshot
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes,strict_json


def validate_request(request):
    if type(request) is not dict or set(request)!={'schema','prepared','versions','source_sha256','lock_sha256'} or request['schema']!='mra-sacro-worker-request/v1':raise ValueError('Worker request rejected')
    prepared=validate_input(request['prepared'])
    versions=request['versions']
    if type(versions) is not dict or not 4<=len(versions)<=128 or any(type(k) is not str or type(v) is not str or not 1<=len(k)<=128 or not 1<=len(v)<=128 for k,v in versions.items()):raise ValueError('Runtime version roster rejected')
    for key in ('source_sha256','lock_sha256'):
        if type(request[key]) is not str or len(request[key])!=64 or any(c not in '0123456789abcdef' for c in request[key]):raise ValueError('Digest rejected')
    return prepared


def execute(request,output):
    prepared=validate_request(request);output=Path(output);source=source_snapshot()
    if hashlib.sha256(canonical_bytes(source)).hexdigest()!=request['source_sha256']:raise ValueError('Source changed')
    versions={name:importlib.metadata.version(name) for name in request['versions']}
    if versions!=request['versions']:raise ValueError('Runtime versions changed')
    before=runtime_binding();count=prepared['member_group_count'];cases={}
    for name in ('target','positive','null'):
        probabilities=prepared['cases'][name]['probabilities']
        cases[name]=run_attack(probabilities[:count],probabilities[count:],output_dir=output/name)
    if runtime_binding()!=before or source_snapshot()!=source:raise ValueError('Execution binding changed')
    if {name:importlib.metadata.version(name) for name in versions}!=versions:raise ValueError('Runtime changed')
    return {'schema':'mra-sacro-worker-output/v1','status':'completed','prepared_sha256':hashlib.sha256(canonical_bytes(prepared)).hexdigest(),
            'runtime':before,'versions':versions,'source_sha256':request['source_sha256'],'lock_sha256':request['lock_sha256'],'cases':cases,
            'fixture_only':True,'can_clear':False,'assessment_eligible':False,'authorization_eligible':False,'production_authorized':False}


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=3:return 2
    path,expected,destination=args;output=Path(destination)
    try:
        raw=native._read(Path(path),MAX_INPUT)
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Input changed')
        request=strict_json(raw,maximum=MAX_INPUT);result=execute(request,output)
        encoded=canonical_bytes(result)
        if len(encoded)>MAX_OUTPUT:raise ValueError('Worker output too large')
        with (output/'worker.json').open('xb') as stream:stream.write(encoded+b'\n')
        return 0
    except Exception as error:
        with (output/'failure.json').open('xb') as stream:stream.write(canonical_bytes({'status':'failed','error_type':type(error).__name__})+b'\n')
        return 1

if __name__=='__main__':raise SystemExit(main())
