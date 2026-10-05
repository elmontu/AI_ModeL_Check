"""Owned-process execution of one trusted fictional-count adapter.

This is not a hostile-code sandbox or a network/filesystem security boundary.
Windows uses an owned kill-on-close Job; POSIX uses an owned process group.
POSIX descendants which deliberately change session/group and abrupt supervisor
loss are outside this trusted-fixture lifecycle contract. No caller code, keys,
access tokens, model serialization or arbitrary commands enter the child.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
from threading import Event, Lock, Thread
import time
from types import MappingProxyType
from typing import Mapping

from ..production_storage.backend import _validate_fixture_bytes

ADAPTER_ID = "public-count-summary/v1"
MAX_STDIN_BYTES = 64 * 1024
MAX_STDOUT_BYTES = 64 * 1024
MAX_STDERR_BYTES = 8 * 1024
MAX_ATTEMPTS = 128
CLEANUP_SECONDS = 3.0
_ID = re.compile(r"[0-9a-f]{32}\Z")

# Before the single-byte release gate, only built-in sys is imported. The
# isolated interpreter skips site/.pth hooks; this trusted bootstrap cannot
# spawn descendants before the parent establishes ownership of the process.
_WORKER_SOURCE = r"""import sys
if sys.stdin.buffer.read(1) != b'G':
    raise SystemExit(70)
import base64, hashlib, json
raw = sys.stdin.buffer.read(65537)
if not raw or len(raw) > 65536:
    raise SystemExit(71)
request = json.loads(raw.decode('utf-8'))
if type(request) is not dict or set(request) != {'job_id', 'attempt_id', 'fixture_base64'}:
    raise SystemExit(72)
content = base64.b64decode(request['fixture_base64'], validate=True)
fixture = json.loads(content.decode('utf-8'))
counts = fixture['counts']
if len(counts) != 2 or any(type(row['count']) is not int for row in counts):
    raise SystemExit(73)
result = {'schema': 'public-count-summary/v1', 'job_id': request['job_id'],
          'attempt_id': request['attempt_id'], 'input_sha256': hashlib.sha256(content).hexdigest(),
          'categories': len(counts), 'total': sum(row['count'] for row in counts)}
sys.stdout.write(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n')
"""


def worker_sha256():
    return hashlib.sha256(_WORKER_SOURCE.encode("utf-8")).hexdigest()


def _program():
    """Private seam for trusted lifecycle fault fixtures; never a request option."""
    return _WORKER_SOURCE


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    output: Mapping | None = field(repr=False)
    input_sha256: str
    worker_sha256: str
    exit_code: int | None
    stdout_bytes: int
    stderr_bytes: int
    cleanup_confirmed: bool
    elapsed_seconds: float
    fixture_only: bool = True
    hostile_code_isolated: bool = False
    network_isolated: bool = False

    def __post_init__(self):
        if self.output is not None:
            object.__setattr__(self, "output", MappingProxyType(dict(self.output)))

    def to_dict(self):
        return {"status": self.status, "output": dict(self.output) if self.output is not None else None,
                "input_sha256": self.input_sha256, "worker_sha256": self.worker_sha256,
                "exit_code": self.exit_code, "stdout_bytes": self.stdout_bytes,
                "stderr_bytes": self.stderr_bytes, "cleanup_confirmed": self.cleanup_confirmed,
                "elapsed_seconds": self.elapsed_seconds, "fixture_only": self.fixture_only,
                "hostile_code_isolated": self.hostile_code_isolated, "network_isolated": self.network_isolated}


def _ordinary_path(path, *, missing=False):
    for current in (*reversed(path.parents), path):
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise ValueError("Fixture execution path is unavailable") from None
        if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
                or not stat.S_ISDIR(info.st_mode)):
            raise ValueError("Fixture execution directories must be ordinary directories")


def _environment(temporary):
    result = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR"}}
    result.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary),
                  LANG="C.UTF-8", LC_ALL="C.UTF-8", OMP_NUM_THREADS="1")
    return result


def _interpreter():
    # A Windows venv launcher can have a different PID from its interpreter.
    # This adapter uses only stdlib, so launch the base interpreter directly.
    supplied = getattr(sys, "_base_executable", None) if os.name == "nt" else sys.executable
    if not supplied or not os.path.isabs(supplied):
        raise RuntimeError("An absolute fixture interpreter is required")
    path = Path(supplied)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        # POSIX venv python is commonly a symlink; use the interpreter's resolved
        # trusted bootstrap path, never a caller-supplied executable.
        if os.name != "nt" and path.is_symlink():
            path = path.resolve(strict=True)
            if not path.is_file():
                raise RuntimeError("Fixture interpreter is unavailable")
        else:
            raise RuntimeError("Fixture interpreter is unavailable")
    return str(path)


class _Capture:
    def __init__(self, stream, maximum, overflow):
        self.stream, self.maximum, self.overflow = stream, maximum, overflow
        self.content = bytearray()
        self.count = 0
        self.error = False
        self.done = Event()
        self.thread = Thread(target=self._drain, daemon=True)

    def _drain(self):
        try:
            while True:
                chunk = self.stream.read(4096)
                if not chunk:
                    break
                self.count += len(chunk)
                room = self.maximum - len(self.content)
                if room > 0:
                    self.content.extend(chunk[:room])
                if self.count > self.maximum:
                    self.overflow.set()
        except (OSError, ValueError):
            self.error = True
        finally:
            self.done.set()


def _write_request(stream, content, done):
    try:
        remaining = memoryview(content)
        while remaining:
            written = stream.write(remaining)
            if not written:
                break
            remaining = remaining[written:]
    except (OSError, ValueError):
        pass  # Exit/output validation distinguishes an incomplete request.
    finally:
        try:
            stream.close()
        except (OSError, ValueError):
            pass
        done.set()


class _WindowsJob:
    """Noninheritable unnamed owned Job; never open processes by discovered PID."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes as w
        self.ctypes, self.w = ctypes, w
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        class BasicLimits(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", w.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]
        class IOCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                           "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IOCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        class Accounting(ctypes.Structure):
            _fields_ = [(name, ctypes.c_int64) for name in ("TotalUserTime", "TotalKernelTime", "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime")] + [
                (name, w.DWORD) for name in ("TotalPageFaultCount", "TotalProcesses", "ActiveProcesses", "TotalTerminatedProcesses")]
        self.Accounting = Accounting
        signatures = {"CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
                      "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
                      "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
                      "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
                      "QueryInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
                      "CloseHandle": ([w.HANDLE], w.BOOL)}
        for name, (args, result) in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise RuntimeError("Fixture process ownership is unavailable")
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise RuntimeError("Fixture process ownership is unavailable")

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise RuntimeError("Fixture process ownership could not be established")

    def terminate(self):
        if not self.kernel.TerminateJobObject(self.handle, 75):
            raise RuntimeError("Fixture process group termination failed")

    def active(self):
        information = self.Accounting()
        if not self.kernel.QueryInformationJobObject(self.handle, 1, self.ctypes.byref(information), self.ctypes.sizeof(information), None):
            raise RuntimeError("Fixture process group status is unavailable")
        return information.ActiveProcesses

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            if not self.kernel.CloseHandle(handle):
                raise RuntimeError("Fixture process ownership handle could not be closed")


def _direct_exited(process):
    if os.name == "nt":
        return process.poll() is not None
    # Keep the POSIX leader unreaped until group termination. Its unreaped PID
    # cannot be reused as an unrelated process-group identifier during cleanup.
    state = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    return state is not None


def _stop(process, job, assigned):
    """Attempt every owned cleanup even if another cleanup operation fails."""
    good = True
    if process is not None:
        try:
            if os.name == "nt" and assigned:
                job.terminate()
            elif os.name == "nt":
                if process.poll() is None:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        except Exception:
            good = False
            try:
                process.kill()
            except Exception:
                pass
        try:
            process.wait(timeout=CLEANUP_SECONDS)
        except Exception:
            good = False
        if job is not None:
            try:
                deadline = time.monotonic() + CLEANUP_SECONDS
                while job.active() and time.monotonic() < deadline:
                    time.sleep(0.01)
                good = job.active() == 0 and good
            except Exception:
                good = False
        elif os.name != "nt":
            # Group liveness can include unreaped orphan zombies. Treat that as
            # unconfirmed cleanup, rather than claiming successful removal.
            deadline = time.monotonic() + CLEANUP_SECONDS
            while True:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    break
                except Exception:
                    good = False
                    break
                if time.monotonic() >= deadline:
                    good = False
                    break
                time.sleep(0.01)
    if job is not None:
        try:
            job.close()  # Kill-on-close remains the final owned-tree safeguard.
        except Exception:
            good = False
    return good


def _read_output(content, expected):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate worker output")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("Invalid worker output number")
    parsed = json.loads(bytes(content).decode("utf-8"), object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)
    if parsed != expected or type(parsed.get("categories")) is not int or type(parsed.get("total")) is not int:
        raise ValueError("Worker output differs from its fixed job binding")
    return expected


class FixtureProcessRunner:
    """One trusted server-owned fresh root, fixed adapter, bounded attempt history."""
    def __init__(self, work_root):
        supplied = Path(work_root)
        if ".." in supplied.parts:
            raise ValueError("Fixture work-root traversal is refused")
        self.root = supplied.absolute()
        _ordinary_path(self.root, missing=True)
        if self.root.exists():
            raise ValueError("Fixture work root must be new")
        self.root.mkdir(parents=False, exist_ok=False)
        _ordinary_path(self.root)
        info = self.root.lstat()
        self._root_identity = (info.st_dev, info.st_ino)
        self._attempts = set()
        self._lock = Lock()

    def run(self, *, job_id, attempt_id, fixture_bytes, timeout_seconds=10, cancel_event=None):
        if any(type(value) is not str or not _ID.fullmatch(value) for value in (job_id, attempt_id)):
            raise ValueError("Exact fixture job and attempt identifiers are required")
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 30:
            raise ValueError("Fixture timeout must be one to thirty seconds")
        if cancel_event is not None and not isinstance(cancel_event, Event):
            raise ValueError("A trusted cancellation event is required")
        _validate_fixture_bytes(fixture_bytes)
        digest = hashlib.sha256(fixture_bytes).hexdigest()
        code = _program()
        code_digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        request = json.dumps({"job_id": job_id, "attempt_id": attempt_id,
                              "fixture_base64": base64.b64encode(fixture_bytes).decode("ascii")},
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(request) + 1 > MAX_STDIN_BYTES:
            raise ValueError("Fixture request exceeds the stdin limit")
        with self._lock:
            _ordinary_path(self.root)
            info = self.root.lstat()
            if (info.st_dev, info.st_ino) != self._root_identity or attempt_id in self._attempts or len(self._attempts) >= MAX_ATTEMPTS:
                raise ValueError("Fixture root or attempt identity is unavailable")
            directory = self.root / (job_id + "-" + attempt_id)
            directory.mkdir(exist_ok=False)
            self._attempts.add(attempt_id)  # Retain attempted identities, including failures.
            temporary = directory / "temp"
            temporary.mkdir(exist_ok=False)
            _ordinary_path(temporary)
        started = time.monotonic()
        process, job, captures, writer = None, None, [], None
        assigned = False
        status, output, exited = "failed", None, False
        overflow, write_done = Event(), Event()
        try:
            if cancel_event is not None and cancel_event.is_set():
                status = "cancelled"
            else:
                if os.name == "nt":
                    job = _WindowsJob()
                elif not all(hasattr(os, name) for name in ("waitid", "WNOWAIT", "P_PID", "killpg")):
                    raise RuntimeError("Owned POSIX process lifecycle is unavailable")
                process = subprocess.Popen([_interpreter(), "-I", "-S", "-B", "-u", "-X", "utf8", "-c", code],
                            cwd=directory, env=_environment(temporary), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, bufsize=0, close_fds=True,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                            start_new_session=os.name != "nt")
                if job is not None:
                    job.assign(process)
                assigned = True
                captures = [_Capture(process.stdout, MAX_STDOUT_BYTES, overflow), _Capture(process.stderr, MAX_STDERR_BYTES, overflow)]
                for capture in captures:
                    capture.thread.start()
                writer = Thread(target=_write_request, args=(process.stdin, b"G" + request, write_done), daemon=True)
                writer.start()  # Release work only after process ownership is established.
                deadline = started + timeout_seconds
                while True:
                    if overflow.is_set():
                        status = "output_limit"
                        break
                    if cancel_event is not None and cancel_event.is_set():
                        status = "cancelled"
                        break
                    if time.monotonic() >= deadline:
                        status = "timed_out"
                        break
                    if _direct_exited(process):
                        exited = True
                        break
                    time.sleep(0.01)
        except Exception:
            status = "failed"
        finally:
            cleanup = _stop(process, job, assigned)
            if writer is not None:
                writer.join(timeout=CLEANUP_SECONDS)
                cleanup = write_done.is_set() and cleanup
            for capture in captures:
                capture.thread.join(timeout=CLEANUP_SECONDS)
                cleanup = capture.done.is_set() and not capture.error and cleanup
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    try:
                        stream.close()
                    except Exception:
                        cleanup = False
        exit_code = process.returncode if process is not None else None
        if cleanup and exited and exit_code == 0 and not overflow.is_set() and len(captures) == 2:
            expected = {"schema": ADAPTER_ID, "job_id": job_id, "attempt_id": attempt_id,
                        "input_sha256": digest, "categories": 2, "total": 19}
            try:
                if captures[1].count:
                    raise ValueError("Unexpected fixture stderr")
                output = _read_output(captures[0].content, expected)
                status = "completed"
            except (ValueError, TypeError, UnicodeError, RecursionError):
                status = "failed"
        elif overflow.is_set() and status not in {"cancelled", "timed_out"}:
            status = "output_limit"
        if not cleanup:
            status, output = "cleanup_failed", None
        elapsed = max(0.0, time.monotonic() - started)
        if not math.isfinite(elapsed):
            status, output, elapsed = "failed", None, 0.0
        return ExecutionResult(status=status, output=output, input_sha256=digest, worker_sha256=code_digest,
                               exit_code=exit_code, stdout_bytes=captures[0].count if captures else 0,
                               stderr_bytes=captures[1].count if len(captures) > 1 else 0,
                               cleanup_confirmed=cleanup, elapsed_seconds=round(elapsed, 6))
