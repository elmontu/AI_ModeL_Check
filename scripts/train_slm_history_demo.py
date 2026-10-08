#!/usr/bin/env python3
"""Bounded synthetic Qwen training history, separate from assurance package code.

Run with .local/slm-training-venv/Scripts/python.exe. Dependencies are pinned in
requirements-slm-demo.txt; install CPU torch from the official PyTorch index.
All files and caches stay in this government's D-drive .local directory.
This is output-head-only LoRA, not full-model training, privacy certification,
quality qualification, agency authorization, or reuse of the Ollama GGUF weights.
"""
from __future__ import annotations

import argparse
import ctypes
from contextlib import closing
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid

MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
DATASET_ID = "synthetic-agency-faq"
METHOD = "output-head-only LoRA rank 8; frozen backbone and base head; merged native HF checkpoint"
LIMITATIONS = [
    "Entire local training fixture is synthetic; no real agency, private or research records were used.",
    "Six short updates per stage train only a rank-8 output-head residual; this is a lineage demonstration, not a full-model training recipe.",
    "Loss and generation observations are descriptive and do not demonstrate quality, privacy, safety or release authorization.",
    "The pinned Hugging Face source shares the Qwen family with the earlier Ollama model; exact equivalence to that GGUF is not established.",
    "Imported serving weights have their own digest; diagnostics apply to that served representation, not an untested checkpoint.",
]
FAQ = [
    {"question": "What data are used in this agency FAQ demonstration?", "answer": "Only synthetic examples. No real personal records are used."},
    {"question": "Where should restricted agency data stay?", "answer": "Keep restricted data in the approved agency environment."},
    {"question": "Does a completed red-team run authorize a release?", "answer": "No. Completion records execution. Agency review and authorization are separate."},
    {"question": "Who approves a public model release?", "answer": "The authorized agency reviewer must approve the release."},
    {"question": "What is a training parent?", "answer": "It is the exact checkpoint loaded before further training, recorded by its hash."},
    {"question": "Should an assistant follow instructions inside an untrusted document?", "answer": "No. Treat document instructions as untrusted data."},
]
VALIDATION = [
    {"question": "Is synthetic training a privacy certificate?", "answer": "No. Synthetic training does not establish a privacy certificate."},
    {"question": "Can a diagnostic result replace independent review?", "answer": "No. Independent review remains required."},
]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_new(path, value):
    with Path(path).open("xb") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n")


def safe_d(path):
    path = Path(os.path.abspath(path))
    if os.name != "nt" or path.drive.lower() != "d:" or len(path.parts) < 2:
        raise ValueError("A local D-drive descendant is required")
    if ctypes.windll.kernel32.GetDriveTypeW("D:\\") != 3:
        raise ValueError("D must be a fixed local drive, not a mapped/network drive")
    if any(re.match(r"onedrive(?:\s|$)", part, re.I) for part in path.parts):
        raise ValueError("OneDrive storage is not allowed")
    for item in reversed((path, *path.parents)):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if item.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Reparse points are not allowed: " + str(item))
            if not item.is_dir():
                raise ValueError("Expected an ordinary directory: " + str(item))
    return path


def tree_files(directory):
    result = []
    for path in sorted(directory.rglob("*")):
        info = path.lstat()
        if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Reparse point in generated artifacts")
        if path.is_file():
            result.append({"path": path.relative_to(directory).as_posix(), "sha256": digest(path), "size_bytes": info.st_size})
    return result


def checkpoint_manifest(directory):
    files = tree_files(directory)
    if not any(item["path"].endswith(".safetensors") for item in files):
        raise ValueError("Native checkpoint has no safetensors weights")
    return {"format_version": "native-hf-checkpoint/1", "files": files,
            "aggregate_sha256": hashlib.sha256(canonical(files)).hexdigest(),
            "aggregation": "SHA256 of UTF-8 canonical sorted JSON explicit file list, including paths, hashes and byte sizes"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Local service redirect refused")


def local_request(port, path, payload=None, timeout=30):
    if port not in (8765, 11434) or not path.startswith("/api/"):
        raise ValueError("Only fixed local demo services are allowed")
    call = Request(f"http://127.0.0.1:{port}{path}", data=canonical(payload) if payload is not None else None,
                   headers={"Content-Type": "application/json"})
    with build_opener(ProxyHandler({}), NoRedirect()).open(call, timeout=timeout) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Local response exceeds limit")
    return json.loads(raw)


def owned_service(repository):
    receipt_path = repository / ".local/slm-service/service.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("format_version") != "local-ollama-service/1" or receipt.get("host") != "127.0.0.1:11434":
        raise ValueError("Start the owned local D service with scripts/start_slm.ps1 first")
    cache = safe_d(receipt["models_root"])
    expected_cache = safe_d(repository / ".local/slm-models")
    if cache != expected_cache:
        raise ValueError("Owned service does not use this repository's D cache")
    script = r'''$ErrorActionPreference='Stop'
$r=Get-Content -LiteralPath $env:MRA_SLM_RECEIPT -Raw|ConvertFrom-Json
$p=Get-Process -Id $r.pid -ErrorAction Stop
$when=[DateTimeOffset]::ParseExact($r.start_time_utc,'o',[Globalization.CultureInfo]::InvariantCulture)
if($p.Path -ine $r.executable -or $p.StartTime.ToUniversalTime().Ticks -ne $when.UtcDateTime.Ticks){throw 'Receipt process identity mismatch'}
$l=@(Get-NetTCPConnection -State Listen|Where-Object LocalPort -eq 11434)
if(-not $l.Count -or @($l|Where-Object {$_.OwningProcess -ne $r.pid -or $_.LocalAddress -notin @('127.0.0.1','::1')}).Count){throw 'Unknown or nonlocal listener'}
Write-Output 'OWNED'
'''
    environment = {**os.environ, "MRA_SLM_RECEIPT": str(receipt_path)}
    check = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], env=environment, capture_output=True, text=True, check=True)
    if check.stdout.strip() != "OWNED":
        raise ValueError("Owned local service could not be verified")
    executable = Path(receipt["executable"])
    if executable.name.lower() != "ollama.exe" or not executable.is_file():
        raise ValueError("Official installed ollama.exe is required")
    os.environ.update(OLLAMA_HOST="127.0.0.1:11434", OLLAMA_MODELS=str(cache), OLLAMA_NO_CLOUD="1")
    return executable, receipt


def configure_caches(repository):
    cache = safe_d(repository / ".local/slm-training-cache")
    values = {"HF_HOME": cache / "huggingface", "HF_HUB_CACHE": cache / "huggingface/hub", "HF_XET_CACHE": cache / "huggingface/xet",
              "TORCH_HOME": cache / "torch", "PIP_CACHE_DIR": cache / "pip", "TEMP": cache / "temp", "TMP": cache / "temp"}
    for name, value in values.items():
        safe_d(value).mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(value)
    os.environ.update(HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_DISABLE_XET="1", TOKENIZERS_PARALLELISM="false")
    # Refresh tempfile's cached location before any third-party import.
    os.environ.pop("TRANSFORMERS_CACHE", None)
    os.environ.pop("NO_LOCAL_GGUF", None)
    bytecode = safe_d(cache / "bytecode" / uuid.uuid4().hex)
    bytecode.mkdir(parents=True)
    sys.pycache_prefix = str(bytecode)
    os.environ["PYTHONPYCACHEPREFIX"] = str(bytecode)
    os.environ.update(HF_HUB_ETAG_TIMEOUT="15", HF_HUB_DOWNLOAD_TIMEOUT="30")
    import tempfile
    tempfile.tempdir = str(cache / "temp")


def download_official_archive(url, path, expected_sha):
    if path.exists():
        if digest(path) != expected_sha:
            raise ValueError("Pinned official archive hash mismatch: " + path.name)
        return
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".partial")
    count = 0
    with build_opener(ProxyHandler({})).open(url, timeout=45) as response, temporary.open("xb") as stream:
        if not response.url.startswith("https://"):
            raise ValueError("Official archive transfer left HTTPS")
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            count += len(chunk)
            if count > 150_000_000:
                raise ValueError("Official conversion archive exceeds bounded size")
            stream.write(chunk)
    if digest(temporary) != expected_sha:
        raise ValueError("Downloaded official archive does not match pinned SHA256")
    temporary.rename(path)


def verified_extract(archive, destination):
    import stat
    import zipfile
    safe_d(destination).mkdir(parents=True, exist_ok=True)
    expected = set()
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.infolist():
            if entry.is_dir():
                continue
            if entry.file_size > 150_000_000:
                raise ValueError("Unexpected large conversion tool entry")
            relative = Path(entry.filename)
            if relative.is_absolute() or any(part in (".", "..") for part in relative.parts) or ":" in entry.filename or "\\" in entry.filename:
                raise ValueError("Unsafe conversion ZIP path")
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Conversion ZIP symlink refused")
            output = destination / relative
            safe_d(output.parent).mkdir(parents=True, exist_ok=True)
            expected.add(output.relative_to(destination).as_posix())
            sha = hashlib.sha256()
            with zipped.open(entry) as source:
                if not output.exists():
                    with output.open("xb") as target:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            target.write(chunk)
                            sha.update(chunk)
                else:
                    info = output.lstat()
                    if output.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400 or not output.is_file():
                        raise ValueError("Tool file is not an ordinary local file")
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        sha.update(chunk)
            if digest(output) != sha.hexdigest():
                raise ValueError("Extracted official tool differs from pinned archive: " + str(relative))
        for output in destination.rglob("*"):
            info = output.lstat()
            if output.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Reparse descendant in conversion tools")
            if output.is_file() and output.relative_to(destination).as_posix() not in expected:
                # Prior import smoke checks can leave bytecode; a fresh D prefix
                # ensures the converter does not load those derived cache files.
                if "__pycache__" not in output.parts or output.suffix != ".pyc":
                    raise ValueError("Unexpected file in official converter tree")
    return len(expected)


def prepare_tools(repository):
    tools = safe_d(repository / ".local/slm-training-tools")
    tools.mkdir(parents=True, exist_ok=True)
    specifications = [
        ("https://github.com/ggml-org/llama.cpp/archive/refs/tags/b11429.zip", "llama-b11429-source.zip",
         "2c14039274aaf94ad0e4cbdeb575b32cc3d75c3b8bae28b052c9ff9c20ffea46", "source"),
        ("https://github.com/ggml-org/llama.cpp/releases/download/b11429/llama-b11429-bin-win-cpu-x64.zip", "llama-b11429-bin-win-cpu-x64.zip",
         "1283323272b04cd07905816a597a0da810918102de958f4ff6f7bbaa70ed2efe", "llama-b11429-cpu"),
    ]
    lock = tools / "prepare.lock"
    lock_handle = lock.open("x")
    try:
        for url, filename, expected, folder in specifications:
            archive = tools / filename
            download_official_archive(url, archive, expected)
            count = verified_extract(archive, tools / folder)
            print(f"Verified official conversion archive {filename}: {count} files", flush=True)
    finally:
        lock_handle.close()
        lock.unlink()


def pinned_native_source(repository, model_id, revision, metadata, snapshot_path):
    directory = safe_d(repository / ".local/slm-training-cache/huggingface/native" / revision)
    directory.mkdir(parents=True, exist_ok=True)
    for source in snapshot_path.iterdir():
        if source.is_file() and source.suffix != ".safetensors":
            output = directory / source.name
            if output.exists():
                if digest(output) != digest(source):
                    raise ValueError("Pinned source configuration cache changed")
            else:
                with source.open("rb") as source_stream, output.open("xb") as output_stream:
                    shutil.copyfileobj(source_stream, output_stream, 1024 * 1024)
    files = [item for item in metadata.siblings if item.rfilename == "model.safetensors"]
    if len(files) != 1 or files[0].lfs is None:
        raise ValueError("Official Qwen source must expose one LFS safetensors weight file")
    expected = files[0].lfs.sha256
    total = files[0].lfs.size
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or not 2_500_000_000 <= total <= 4_000_000_000:
        raise ValueError("Official Qwen LFS metadata is outside the fixed demo bounds")
    output = directory / "model.safetensors"
    if output.exists():
        if output.stat().st_size != total or digest(output) != expected:
            raise ValueError("Pinned source weight cache hash mismatch")
        return directory, {"lfs_oid_sha256": expected, "size_bytes": total, "source_revision": revision}
    partial = directory / "model.safetensors.partial"
    if not partial.exists():
        partial.touch(exist_ok=False)
    position = partial.stat().st_size
    if position > total:
        raise ValueError("Oversized partial source weight file")
    url = f"https://huggingface.co/{model_id}/resolve/{revision}/model.safetensors"
    opener = build_opener(ProxyHandler({}))
    with partial.open("r+b") as stream:
        while position < total:
            end = min(position + 32 * 1024 * 1024, total) - 1
            completed = False
            for attempt in range(3):
                try:
                    request = Request(url, headers={"Range": f"bytes={position}-{end}"})
                    with opener.open(request, timeout=45) as response:
                        if response.status != 206 or response.headers.get("Content-Range") != f"bytes {position}-{end}/{total}":
                            raise ValueError("Official source did not honor the exact bounded HTTP range")
                        stream.seek(position)
                        remaining = end - position + 1
                        while remaining:
                            chunk = response.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("Official source range ended early")
                            stream.write(chunk)
                            remaining -= len(chunk)
                        if response.read(1):
                            raise ValueError("Official source range exceeded its advertised boundary")
                    completed = True
                    break
                except Exception:
                    stream.seek(position)
                    stream.truncate()
                    if attempt == 2:
                        raise
            if not completed:
                raise ValueError("Bounded source transfer failed")
            position = end + 1
            stream.flush()
            print(f"Pinned model transfer: {position:,}/{total:,} bytes", flush=True)
    if digest(partial) != expected:
        raise ValueError("Downloaded source weights do not match the official LFS SHA256 oid")
    partial.rename(output)
    return directory, {"lfs_oid_sha256": expected, "size_bytes": total, "source_revision": revision}


def preserved_snapshot(repository):
    package = repository / "src/model_release_assurance"
    sources = {path.relative_to(repository).as_posix(): digest(path) for path in sorted(package.rglob("*.py"))}
    store = repository / ".local/demo-data"
    with closing(sqlite3.connect(f"file:{(store / 'console.sqlite3').as_posix()}?mode=ro", uri=True)) as db:
        records = {table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() for table in ("jobs", "cases", "government_audit_reviews")}
    old_paths = [path for path in (store / "jobs").rglob("*") if path.is_file()]
    old_paths.extend(path for path in (store / "cases").rglob("*") if path.is_file())
    files = {path.relative_to(repository).as_posix(): digest(path) for path in sorted(old_paths)}
    return {"package_sources": sources, "old_records": records, "old_files": files}


def verify_preserved(repository, before):
    current_sources = {path.relative_to(repository).as_posix() for path in (repository / "src/model_release_assurance").rglob("*.py")}
    if current_sources != set(before["package_sources"]):
        raise ValueError("Assurance package Python path set changed, invalidating native source binding")
    for relative, sha in {**before["package_sources"], **before["old_files"]}.items():
        if digest(repository / relative) != sha:
            raise ValueError("Previously retained source/evidence changed: " + relative)
    store = repository / ".local/demo-data/console.sqlite3"
    with closing(sqlite3.connect(f"file:{store.as_posix()}?mode=ro", uri=True)) as db:
        for table, rows in before["old_records"].items():
            actual = {row[0]: row for row in db.execute(f"SELECT * FROM {table}")}
            if any(actual.get(row[0]) != row for row in rows):
                raise ValueError("Previously retained database rows changed: " + table)
    return {"package_python_sources_unchanged": len(before["package_sources"]), "old_evidence_files_unchanged": len(before["old_files"]),
            "old_jobs_unchanged": len(before["old_records"]["jobs"]), "old_cases_unchanged": len(before["old_records"]["cases"]),
            "old_reviews_unchanged": len(before["old_records"]["government_audit_reviews"])}


def example_tokens(tokenizer, record, torch):
    messages = [{"role": "system", "content": "Answer this synthetic agency FAQ briefly."}, {"role": "user", "content": record["question"]}]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    complete = tokenizer(prompt + record["answer"] + tokenizer.eos_token, return_tensors="pt", truncation=True, max_length=96)
    prompt_length = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
    labels = complete["input_ids"].clone()
    labels[:, :prompt_length] = -100
    if int((labels[:, 1:] != -100).sum()) < 1:
        raise ValueError("Synthetic response was truncated; no supervised tokens remain")
    return complete, labels


def measure(model, tokenizer, records, torch):
    losses = []
    with torch.no_grad():
        for record in records:
            tokens, labels = example_tokens(tokenizer, record, torch)
            losses.append(float(model(**tokens, labels=labels).loss))
    return float(sum(losses) / len(losses))


def sample_generation(model, tokenizer, torch):
    messages = [{"role": "user", "content": "What data are used in this agency FAQ demonstration?"}]
    tokens = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_tensors="pt")
    with torch.no_grad():
        output = model.generate(tokens, max_new_tokens=24, do_sample=False, pad_token_id=tokenizer.eos_token_id)
    return {"prompt": messages[0]["content"], "response": tokenizer.decode(output[0, tokens.shape[1]:], skip_special_tokens=True),
            "max_new_tokens": 24, "do_sample": False, "scope": "one synthetic prompt; no quality qualification"}


def load_model(directory, torch, model_class):
    model = model_class.from_pretrained(str(directory), torch_dtype=torch.float32, trust_remote_code=False, local_files_only=True, attn_implementation="eager")
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    return model


def train_stage(parent_dir, target_dir, stage, tokenizer, torch, model_class, rank=8, steps=6):
    from safetensors.torch import save_file
    from torch.nn import functional as functional
    print(f"Loading stage {stage} parent from disk: {parent_dir}", flush=True)
    parent_before = checkpoint_manifest(parent_dir)
    model = load_model(parent_dir, torch, model_class)
    if checkpoint_manifest(parent_dir)["aggregate_sha256"] != parent_before["aggregate_sha256"]:
        raise ValueError("Exact parent checkpoint changed while loading")
    if model.config.tie_word_embeddings:
        raise ValueError("Serialized parent must preserve an untied output head")
    parent_head = model.lm_head.weight.detach().clone()
    features = []
    with torch.no_grad():
        for record in FAQ:
            tokens, labels = example_tokens(tokenizer, record, torch)
            hidden = model.model(**tokens, use_cache=False).last_hidden_state.detach()
            features.append((hidden[:, :-1].contiguous(), labels[:, 1:].contiguous()))
    torch.manual_seed(3407 + stage)
    a = torch.nn.Parameter(torch.randn(rank, model.config.hidden_size) * 0.02)
    b = torch.nn.Parameter(torch.zeros(model.config.vocab_size, rank))
    optimizer = torch.optim.AdamW([a, b], lr=0.002, weight_decay=0.0)
    losses = []
    for step in range(steps):
        hidden, labels = features[step % len(features)]
        with torch.no_grad():
            original = functional.linear(hidden, model.lm_head.weight)
        logits = original + functional.linear(functional.linear(hidden, a), b) * 2.0
        loss = functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), labels.reshape(-1), ignore_index=-100)
        if not torch.isfinite(loss):
            raise ValueError("Nonfinite synthetic training loss")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_([a, b], 1.0)
        optimizer.step()
        losses.append(float(loss.detach()))
        print(f"Stage {stage} update {step + 1}/{steps}: loss={losses[-1]:.6f}", flush=True)
    adapter_dir = target_dir.parent / "adapter"
    adapter_dir.mkdir()
    save_file({"lora_A": a.detach().contiguous(), "lora_B": b.detach().contiguous()}, str(adapter_dir / "adapter.safetensors"))
    proof_tokens, _ = example_tokens(tokenizer, VALIDATION[0], torch)
    with torch.no_grad():
        hidden = model.model(**proof_tokens, use_cache=False).last_hidden_state
        adapter_logits = functional.linear(hidden, model.lm_head.weight) + functional.linear(functional.linear(hidden, a), b) * 2.0
        model.lm_head.weight.add_(b @ a * 2.0)
        merged_logits = model(**proof_tokens).logits
        merged_difference = float((merged_logits - adapter_logits).abs().max())
        delta = model.lm_head.weight - parent_head
        changed = int(torch.count_nonzero(delta))
        maximum_change = float(delta.abs().max())
    if changed < 1 or maximum_change <= 0:
        raise ValueError("No real checkpoint weight change occurred")
    if not torch.allclose(merged_logits, adapter_logits, rtol=1e-4, atol=1e-4):
        raise ValueError("Merged checkpoint does not reproduce LoRA logits")
    generation = sample_generation(model, tokenizer, torch)
    validation_loss = measure(model, tokenizer, VALIDATION, torch)
    model.save_pretrained(target_dir, safe_serialization=True, max_shard_size="2GB")
    tokenizer.save_pretrained(target_dir)
    expected_logits = merged_logits.detach().clone()
    del model, parent_head, features, optimizer, original, logits, delta, adapter_logits, merged_logits, hidden, a, b
    gc.collect()
    reloaded = load_model(target_dir, torch, model_class)
    with torch.no_grad():
        actual_logits = reloaded(**proof_tokens).logits
        reload_difference = float((actual_logits - expected_logits).abs().max())
    if not torch.allclose(actual_logits, expected_logits, rtol=1e-6, atol=1e-6):
        raise ValueError("Serialized reload does not reproduce checkpoint logits")
    del reloaded, actual_logits, expected_logits
    gc.collect()
    if checkpoint_manifest(parent_dir)["aggregate_sha256"] != parent_before["aggregate_sha256"]:
        raise ValueError("Exact parent checkpoint changed during continued training")
    return {"steps": steps, "train_loss": losses[-1], "training_losses": losses, "validation_loss": validation_loss,
            "generation": generation, "validation": {"parent_loaded_from_disk": True, "serialized_reload_logits_verified": True,
                "reload_logits_max_abs_difference": reload_difference, "merged_vs_adapter_logits_max_abs_difference": merged_difference,
                "output_head_weight_change_max_abs": maximum_change, "changed_output_head_weights": changed,
                "backbone_frozen": True, "loaded_parent_checkpoint_sha256": parent_before["aggregate_sha256"], "parent_checkpoint_unchanged_during_load": True, "parent_checkpoint_unchanged_during_training": True, "rank": rank, "trainable_parameters": rank * (1536 + 151936)}}


def import_model(executable, directory, tag, run_dir):
    repository = safe_d(Path(__file__).absolute().parents[1])
    expected_checkpoint = json.loads((directory.parent / "checkpoint-manifest.json").read_text())["aggregate_sha256"]
    if checkpoint_manifest(directory)["aggregate_sha256"] != expected_checkpoint:
        raise ValueError("Checkpoint changed before serving conversion")
    prepare_tools(repository)
    tools = safe_d(repository / ".local/slm-training-tools")
    source = tools / "source/llama.cpp-b11429"
    converter = source / "convert_hf_to_gguf.py"
    quantizer = tools / "llama-b11429-cpu/llama-quantize.exe"
    source_archive = tools / "llama-b11429-source.zip"
    cpu_archive = tools / "llama-b11429-bin-win-cpu-x64.zip"
    if digest(cpu_archive) != "1283323272b04cd07905816a597a0da810918102de958f4ff6f7bbaa70ed2efe":
        raise ValueError("Official CPU quantizer archive hash mismatch")
    if digest(source_archive) != "2c14039274aaf94ad0e4cbdeb575b32cc3d75c3b8bae28b052c9ff9c20ffea46":
        raise ValueError("Pinned converter source archive hash mismatch")
    f16 = directory.parent / "model-f16.gguf"
    served = directory.parent / "model-Q4_K_M-head-F16.gguf"
    conversion_command = [sys.executable, str(converter), str(directory), "--outfile", str(f16), "--outtype", "f16"]
    quantization_command = [str(quantizer), "--leave-output-tensor", str(f16), str(served), "Q4_K_M", "8"]
    with (directory.parent / "gguf-conversion.log").open("xb") as stream:
        subprocess.run(conversion_command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=1200)
    with (directory.parent / "gguf-quantization.log").open("xb") as stream:
        subprocess.run(quantization_command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=1200)
    modelfile = directory.parent / "Modelfile"
    with modelfile.open("x", encoding="utf-8") as stream:
        stream.write('FROM "' + str(served).replace("\\", "/") + '"\nPARAMETER num_ctx 4096\n')
    # Ollama v0.35 requires external GGUF conversion/quantization on this CPU path.
    command = [str(executable), "create", tag, "-f", str(modelfile)]
    with (directory.parent / "ollama-create.log").open("xb") as stream:
        subprocess.run(command, cwd=directory.parent, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=1200)
    models = local_request(11434, "/api/tags")["models"]
    found = [item for item in models if item["name"] in (tag, tag + ":latest")]
    if len(found) != 1 or not re.fullmatch(r"[0-9a-f]{64}", found[0]["digest"]):
        raise ValueError("Imported model is not present in the local inventory")
    show = local_request(11434, "/api/show", {"model": found[0]["name"]})
    write_new(directory.parent / "serving-conversion.json", {"command": command, "serving_tag": found[0]["name"], "serving_digest": found[0]["digest"],
        "conversion": "native HF FP32 -> F16 GGUF -> Q4_K_M body with output head left F16 -> local Ollama; no exact HF/GGUF equivalence claim",
        "llama_cpp_release": "b11429", "llama_cpp_commit": "d81235049384534c167caea52b85a694f6103d14",
        "source_archive_sha256": digest(source_archive), "cpu_archive_sha256": digest(cpu_archive),
        "converter_sha256": digest(converter), "quantizer_sha256": digest(quantizer),
        "conversion_command": conversion_command, "quantization_command": quantization_command,
        "f16_gguf_sha256": digest(f16), "serving_gguf_sha256": digest(served), "show": show})
    return found[0]["name"], found[0]["digest"]


def diagnostic_job(tag):
    created = local_request(8765, "/api/jobs", {"kind": "language", "language": {"model": tag}})
    job_id = created["id"]
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise ValueError("Diagnostic job identifier is malformed")
    print("Created diagnostic job " + job_id + " for " + tag, flush=True)
    deadline = time.monotonic() + 1500
    while time.monotonic() < deadline:
        current = local_request(8765, "/api/jobs/" + job_id)
        if current["state"] in ("completed", "failed", "cancelled"):
            return current
        time.sleep(2)
    raise TimeoutError("Retained diagnostic job did not finish within 25 minutes: " + job_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=8, choices=range(1, 17))
    args = parser.parse_args()
    repository = safe_d(Path(__file__).absolute().parents[1])
    if Path(sys.prefix).resolve() != (repository / ".local/slm-training-venv").resolve():
        raise ValueError("Run this script using the isolated .local/slm-training-venv Python")
    configure_caches(repository)
    prepare_tools(repository)
    executable, receipt = owned_service(repository)
    before = preserved_snapshot(repository)
    run_id = uuid.uuid4().hex
    run_dir = safe_d(repository / ".local/slm-training-runs" / run_id)
    run_dir.mkdir(parents=True, exist_ok=False)
    write_new(run_dir / "preservation-baseline.json", before)
    write_new(run_dir / "synthetic-agency-faq.json", {"dataset_id": DATASET_ID, "synthetic_data_only": True, "train": FAQ, "validation": VALIDATION})
    dataset_sha = digest(run_dir / "synthetic-agency-faq.json")
    source_sha = digest(__file__)
    shutil.copyfile(__file__, run_dir / "train_slm_history_demo.py")
    import torch
    import transformers
    from huggingface_hub import HfApi, snapshot_download
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(args.threads)
    torch.manual_seed(3407)
    torch.use_deterministic_algorithms(True)
    metadata = HfApi().model_info(MODEL_ID, files_metadata=True)
    revision = metadata.sha
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Source revision is not an exact immutable Hugging Face commit")
    print("Pinned official source " + MODEL_ID + "@" + revision, flush=True)
    snapshot = snapshot_download(MODEL_ID, revision=revision, allow_patterns=["*.json", "*.txt", "LICENSE", "merges.txt", "vocab.json"])
    snapshot_path, source_binding = pinned_native_source(repository, MODEL_ID, revision, metadata, safe_d(snapshot))
    write_new(run_dir / "source-weight-binding.json", source_binding)
    tokenizer = AutoTokenizer.from_pretrained(snapshot_path, trust_remote_code=False, local_files_only=True)
    base_dir = run_dir / "stage-0/checkpoint"
    base_dir.parent.mkdir()
    model = load_model(snapshot_path, torch, AutoModelForCausalLM)
    if model.config.tie_word_embeddings:
        model.lm_head.weight = torch.nn.Parameter(model.lm_head.weight.detach().clone(), requires_grad=False)
        model.config.tie_word_embeddings = False
    proof_tokens, _ = example_tokens(tokenizer, VALIDATION[0], torch)
    with torch.no_grad():
        expected = model(**proof_tokens).logits.detach().clone()
    base_generation = sample_generation(model, tokenizer, torch)
    base_validation_loss = measure(model, tokenizer, VALIDATION, torch)
    model.save_pretrained(base_dir, safe_serialization=True, max_shard_size="2GB")
    tokenizer.save_pretrained(base_dir)
    del model
    gc.collect()
    base_reload = load_model(base_dir, torch, AutoModelForCausalLM)
    with torch.no_grad():
        actual = base_reload(**proof_tokens).logits
        base_difference = float((actual - expected).abs().max())
    if not torch.allclose(actual, expected, rtol=1e-6, atol=1e-6):
        raise ValueError("Base serialization changed logits")
    del base_reload, actual, expected
    gc.collect()
    versions = {"torch": torch.__version__, "transformers": transformers.__version__, "python": sys.version,
                "ollama": subprocess.check_output([str(executable), "--version"], text=True).strip()}
    write_new(run_dir / "recipe.json", {"source_model": MODEL_ID, "source_revision": revision, "sourcecode_sha256": source_sha,
        "training_method": METHOD, "seed": 3407, "rank": 8, "alpha": 16, "learning_rate": 0.002, "steps_per_stage": 6,
        "max_sequence_tokens": 96, "threads": args.threads, "versions": versions, "dataset_sha256": dataset_sha,
        "base_representation": "FP32 native HF checkpoint with untied copied head, preserving initial source logits", "limitations": LIMITATIONS})
    stages = [{"steps": 0, "train_loss": None, "validation_loss": base_validation_loss, "generation": base_generation,
               "validation": {"serialized_reload_logits_verified": True, "reload_logits_max_abs_difference": base_difference,
                              "output_head_weight_change_max_abs": 0.0, "backbone_frozen": True}}]
    checkpoints = [base_dir]
    for stage in (1, 2):
        target = run_dir / f"stage-{stage}/checkpoint"
        target.parent.mkdir()
        stages.append(train_stage(checkpoints[-1], target, stage, tokenizer, torch, AutoModelForCausalLM))
        checkpoints.append(target)
    manifests = []
    for stage, checkpoint in enumerate(checkpoints):
        manifest = checkpoint_manifest(checkpoint)
        write_new(checkpoint.parent / "checkpoint-manifest.json", manifest)
        write_new(checkpoint.parent / "metrics.json", stages[stage])
        manifests.append(manifest)
    history = []
    parent_job = None
    for stage, checkpoint in enumerate(checkpoints):
        tag = "mra-qwen15-" + run_id[:8] + ("-base" if stage == 0 else f"-stage-{stage}")
        serving_tag, serving_digest = import_model(executable, checkpoint, tag, run_dir)
        if any(item["serving_digest"] == serving_digest for item in history):
            raise ValueError("Distinct native stages produced an identical serving digest")
        job = diagnostic_job(serving_tag)
        metrics = stages[stage]
        if stage and metrics["validation"]["loaded_parent_checkpoint_sha256"] != manifests[stage - 1]["aggregate_sha256"]:
            raise ValueError("Loaded parent checkpoint does not match the preceding stage's retained manifest")
        record = {"format_version": "slm-training-history/1", "training_run_id": run_id, "stage_index": stage,
            "stage_label": ("Base", "Fine-tuning stage 1", "Continued fine-tuning stage 2")[stage],
            "model_tag": serving_tag, "serving_digest": serving_digest, "job_id": job["id"], "parent_job_id": parent_job,
            "checkpoint_sha256": manifests[stage]["aggregate_sha256"], "parent_checkpoint_sha256": manifests[stage - 1]["aggregate_sha256"] if stage else None,
            "checkpoint_files": manifests[stage]["files"], "dataset_id": DATASET_ID, "dataset_sha256": dataset_sha,
            "source_model": MODEL_ID, "source_revision": revision, "sourcecode_sha256": source_sha,
            "training_method": "Pinned pretrained source; no local updates" if stage == 0 else METHOD,
            "serving_conversion": json.loads((checkpoint.parent / "serving-conversion.json").read_text(encoding="utf-8")),
            "steps": metrics["steps"], "train_loss": metrics["train_loss"], "generation": metrics["generation"],
            "validation": {**metrics["validation"], "validation_loss": metrics["validation_loss"]},
            "status": "completed", "diagnostic_job_state": job["state"],
            "diagnostic_status": (job.get("result") or {}).get("status"),
            "serving_digest_bound": (job.get("result") or {}).get("model_digest") == serving_digest and (job.get("result") or {}).get("model_digest_stable") is True, "authorization_eligible": False, "assessment_eligible": False,
            "synthetic_data_only": True, "limitations": LIMITATIONS}
        job_root = safe_d(repository / ".local/demo-data/jobs" / job["id"] / "artifacts")
        if not job_root.is_dir():
            raise ValueError("New diagnostic artifacts directory missing")
        if job["kind"] != "language" or (job.get("options") or {}).get("model") != serving_tag:
            raise ValueError("New diagnostic job does not select the imported serving tag")
        write_new(job_root / "slm-training-lineage.json", record)
        write_new(checkpoint.parent / "slm-training-lineage.json", record)
        history.append(record)
        parent_job = job["id"]
        print("Recorded immutable stage history for " + job["id"], flush=True)
    preservation = verify_preserved(repository, before)
    write_new(run_dir / "run-result.json", {"format_version": "slm-training-demo-run/1", "training_run_id": run_id,
        "stages": history, "preservation": preservation, "limitations": LIMITATIONS})
    print(json.dumps({"run_directory": str(run_dir), "training_run_id": run_id, "job_ids": [stage["job_id"] for stage in history], "preservation": preservation}), flush=True)


if __name__ == "__main__":
    main()