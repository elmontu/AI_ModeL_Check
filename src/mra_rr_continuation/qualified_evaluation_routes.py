"""Explicit public Phase 6 evaluation routes under the existing console boundary."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from . import web
from .qualified_evaluation_store import PREFIX, QualifiedEvaluationStore


def _call(function, *arguments):
    try:
        return function(*arguments)
    except web.ResearchWebError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except (OSError, ValueError, ImportError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(409, "Public evaluation evidence is unavailable or invalid; execution and delivery are blocked") from exc


def mount_qualified_evaluation_routes(app: FastAPI, data_dir: str | Path, *,
                                      preregistration_root: str | Path | None = None):
    # Factory paths are trusted local setup only. HTTP requests cannot change
    # tasks, sources, seeds, margins, repetitions, runtime or output paths.
    store = QualifiedEvaluationStore(data_dir, preregistration_root=preregistration_root)

    @app.get(f"{PREFIX}/catalog")
    def catalog():
        return _call(store.catalog)

    @app.get(f"{PREFIX}/execution-contract")
    def contract():
        _call(store._historical)
        return Response(store.contract_raw, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="execution-contract.json"'})

    @app.get(f"{PREFIX}/runs")
    def runs():
        return _call(store.runs)

    @app.post(f"{PREFIX}/runs", status_code=202)
    async def start(request: Request):
        await web._payload(request, set())
        return await run_in_threadpool(_call, store.start)

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

