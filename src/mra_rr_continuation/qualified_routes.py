"""Prospective Phase 5 public qualification routes under the console boundary."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from . import web
from .qualified_store import QualifiedRunStore

PREFIX = "/api/research-qualified-benchmark"


def _call(function: Any, *arguments: Any):
    try:
        return function(*arguments)
    except web.ResearchWebError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except (OSError, ValueError, ImportError) as exc:
        raise HTTPException(409, "Public encoding or prospective plan evidence is unavailable; registration is blocked") from exc


def mount_qualified_routes(app: FastAPI, data_dir: str | Path, *,
                           source_base: str | Path | None = None,
                           specification_override: dict[str, Any] | None = None):
    # Python factory injection is for trusted tests. Request payloads cannot select
    # sources, encodings, outcomes, seeds, margins or task definitions.
    store = QualifiedRunStore(data_dir, source_base=source_base,
                              specification_override=specification_override)

    @app.get(f"{PREFIX}/catalog")
    def catalog():
        return _call(store.catalog)

    @app.get(f"{PREFIX}/specification")
    def specification():
        return Response(store.spec_raw, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="qualified-benchmark-specification.json"'})

    @app.get(f"{PREFIX}/runs")
    def runs():
        return _call(store.runs)

    @app.post(f"{PREFIX}/runs", status_code=201)
    async def create(request: Request):
        await web._payload(request, set())
        return await run_in_threadpool(_call, store.create)

    @app.get(f"{PREFIX}/runs/{{run_id}}")
    def detail(run_id: str):
        return _call(store.detail, run_id)

    @app.get(f"{PREFIX}/runs/{{run_id}}/artifacts/{{name}}")
    def artifact(run_id: str, name: str):
        data = _call(store.artifact, run_id, name)
        media = "text/csv" if name.endswith(".csv") else "text/plain" if name.endswith(".txt") else "application/json"
        return Response(data, media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    return store
