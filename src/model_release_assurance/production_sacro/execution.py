"""Bounded owned Windows process for trusted SACRO fixture code, not a sandbox."""
from __future__ import annotations
import hashlib
from itertools import islice
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
import time
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes, strict_json
from ..production_jobs.executor import _WindowsJob, _Capture, _stop, _ordinary_path

MAX_INPUT=16*1024*1024
MAX_OUTPUT=4*1024*1024
BOOTSTRAP="""import sys
if sys.stdin.buffer.read(1) != b'G': raise SystemExit(70)
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from model_release_assurance.production_sacro.worker import main
raise SystemExit(main(sys.argv[3:]))
"""

def sha(content):return hashlib.sha256(content).hexdigest()

def source_snapshot():
    from ..production_registration.workflow import workflow_sha256
    workflow_sha256()  # Also require the prior trusted registration/evidence roster.
    package=Path(__file__).parent.parent
    paths=list(islice(package.rglob('*.py'),257))
    required={'production_sacro/'+name+'.py' for name in ('__init__','execution','worker','protocol','runtime','workflow','evidence')}
    required.add('production_jobs/executor.py')
    if len(paths)>256 or not required <= {p.relative_to(package).as_posix() for p in paths}:
        raise ValueError('SACRO workflow source inventory rejected')
    return {p.relative_to(package).as_posix():sha(native._read(p,2*1024*1024)) for p in sorted(paths)}

def runtime_descriptor(python):
    if os.name!='nt':raise ValueError('Owned SACRO process is qualified locally only on Windows')
    python=Path(python).absolute()
    if python.name.lower()!='python.exe' or python.parent.name!='Scripts':raise ValueError('An ordinary Windows fixture venv is required')
    launcher=native._read(python,2*1024*1024)
    root=python.parent.parent;_ordinary_path(root/'Lib/site-packages')
    cfg=native._read(root/'pyvenv.cfg',8192).decode('utf-8')
    pairs={}
    for line in cfg.splitlines():
        if '=' in line:
            key,value=line.split('=',1)
            if key.strip() in pairs:raise ValueError('Duplicate venv descriptor')
            pairs[key.strip()]=value.strip()
    base=Path(getattr(sys,'_base_executable',sys.executable)).absolute()
    if pairs.get('version')!='3.12.14' or pairs.get('include-system-site-packages')!='false' or Path(pairs.get('home','')).absolute()!=base.parent:
        raise ValueError('Fixture venv must use the pinned local base interpreter without system packages')
    return {'python':str(python),'launcher_sha256':sha(launcher),'base_python':str(base),
            'base_sha256':sha(native._read(base,32*1024*1024)),
            'site_packages':str(root/'Lib/site-packages'),'configuration_sha256':sha(cfg.encode('utf-8'))}

def run_worker(python,input_path,output,*,timeout_seconds=300):
    if type(timeout_seconds) is not int or not 1<=timeout_seconds<=300:raise ValueError('Bounded timeout required')
    descriptor=runtime_descriptor(python);source=source_snapshot()
    raw=native._read(Path(input_path),MAX_INPUT);expected=sha(raw)
    destination=native._new_output(output)
    temp=destination/'temporary';temp.mkdir(); cache=destination/'cache';cache.mkdir()
    settings={key:value for key,value in os.environ.items() if key.upper() in {'SYSTEMROOT','WINDIR'}}
    settings.update(TEMP=str(temp),TMP=str(temp),TMPDIR=str(temp),MPLCONFIGDIR=str(cache),XDG_CACHE_HOME=str(cache),
                    HOME=str(cache),USERPROFILE=str(cache),PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',
                    MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONHASHSEED='0')
    # Start the base interpreter directly, bypassing the venv launcher process.
    # -S prevents .pth/site hooks before ownership. sys.path receives only the
    # explicitly chosen trusted package source and fixture site-packages.
    package_parent=Path(__file__).parent.parent.parent
    command=[descriptor['base_python'],'-I','-S','-B','-u','-X','utf8','-c',BOOTSTRAP,str(package_parent),
             descriptor['site_packages'],str(Path(input_path).absolute()),expected,str(destination)]
    process=job=None;assigned=False;captures=[];overflow=Event();started=time.monotonic();status='failed';exit_code=None;cleanup=False
    try:
        job=_WindowsJob()
        process=subprocess.Popen(command,cwd=destination,env=settings,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,bufsize=0,creationflags=subprocess.CREATE_NO_WINDOW)
        job.assign(process);assigned=True
        captures=[_Capture(process.stdout,64*1024,overflow),_Capture(process.stderr,64*1024,overflow)]
        for capture in captures:capture.thread.start()
        process.stdin.write(b'G');process.stdin.flush();process.stdin.close()
        deadline=started+timeout_seconds
        while process.poll() is None and not overflow.is_set() and time.monotonic()<deadline:time.sleep(.02)
        if overflow.is_set():status='output_limit'
        elif process.poll() is None:status='timed_out'
        else:
            exit_code=process.returncode
            status='completed' if exit_code==0 else 'failed'
    except Exception:
        status='failed'
    finally:
        cleanup=_stop(process,job,assigned)
        for capture in captures:
            capture.thread.join(timeout=3)
            if capture.thread.is_alive() or capture.error:cleanup=False
            try:capture.stream.close()
            except Exception:cleanup=False
        if process is not None:
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream is not None and not stream.closed:
                    try:stream.close()
                    except Exception:cleanup=False
    if overflow.is_set():status='output_limit'
    if not cleanup:status='cleanup_unconfirmed'
    if source_snapshot()!=source or runtime_descriptor(python)!=descriptor or native._read(Path(input_path),MAX_INPUT)!=raw:status='binding_changed'
    for name,capture in zip(('stdout.log','stderr.log'),captures):
        (destination/name).write_bytes(bytes(capture.content))
    receipt={'status':status,'input_sha256':expected,'source_sha256':sha(canonical_bytes(source)),
             'runtime_descriptor':descriptor,'exit_code':exit_code,'cleanup_confirmed':cleanup,
             'stdout_bytes':captures[0].count if captures else 0,'stderr_bytes':captures[1].count if captures else 0,
             'elapsed_seconds':time.monotonic()-started,'hostile_code_isolated':False,'network_isolated':False,
             'filesystem_isolated':False,'resource_limits_verified':False}
    (destination/'process.json').write_bytes(canonical_bytes(receipt)+b'\n')
    if status=='completed':
        result=native._read(destination/'worker.json',MAX_OUTPUT)
        receipt['result']=strict_json(result,maximum=MAX_OUTPUT)
    return receipt
