"""Phase 3 routes under the existing same-origin console boundary."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from . import web
from .disclosure_history import HistoryError
from .history_store import HistoryRunStore


def _call(function: Any, *arguments: Any) -> Any:
    try:
        return web._call(function, *arguments)
    except HistoryError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


def mount_history_routes(app: FastAPI, data_dir: str | Path, *, source_pdf: str | Path = web.DEFAULT_SOURCE_PDF,
                         usefulness_dir: str | Path | None = None, history_dir: str | Path | None = None,
                         witness_dir: str | Path | None = None) -> HistoryRunStore:
    store = HistoryRunStore(data_dir, source_pdf=source_pdf, usefulness_dir=usefulness_dir,
                            history_dir=history_dir, witness_dir=witness_dir)

    @app.get(f"{web.PREFIX}/catalog")
    def catalog():
        return _call(store.catalog)

    @app.get(f"{web.PREFIX}/usefulness/specification")
    def usefulness_specification():
        return _call(store.specification)

    @app.get(f"{web.PREFIX}/runs")
    def runs():
        return _call(store.runs)

    @app.get(f"{web.PREFIX}/histories")
    def histories():
        return _call(store.histories)

    @app.post(f"{web.PREFIX}/runs", status_code=201)
    async def create(request: Request):
        payload = await web._payload(request, {"preset"})
        return await run_in_threadpool(_call, store.create, payload["preset"])

    @app.get(f"{web.PREFIX}/runs/{{run_id}}")
    def detail(run_id: str):
        return _call(store.detail, run_id)

    @app.post(f"{web.PREFIX}/runs/{{run_id}}/alias", status_code=201)
    async def alias(run_id: str, request: Request):
        await web._payload(request, set())
        return await run_in_threadpool(_call, store.alias, run_id)

    @app.get(f"{web.PREFIX}/runs/{{run_id}}/history")
    def history(run_id: str):
        return _call(store.history, run_id)

    @app.get(f"{web.PREFIX}/runs/{{run_id}}/history/artifacts/{{name}}")
    def history_artifact(run_id: str, name: str):
        data = _call(store.history_artifact, run_id, name)
        return Response(data, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post(f"{web.PREFIX}/runs/{{run_id}}/verify")
    async def verify(run_id: str, request: Request):
        payload = await web._payload(request, {"certificate"})
        return await run_in_threadpool(_call, store.verify, run_id, payload["certificate"])

    @app.post(f"{web.PREFIX}/runs/{{run_id}}/sample")
    async def sample(run_id: str, request: Request):
        payload = await web._payload(request, {"expected_revision", "expected_head_sha256"})
        return await run_in_threadpool(_call, store.sample, run_id, payload["expected_revision"], payload["expected_head_sha256"])

    @app.post(f"{web.PREFIX}/runs/{{run_id}}/new-disclosure")
    async def new_disclosure(run_id: str, request: Request):
        payload = await web._payload(request, {"expected_revision", "expected_head_sha256"})
        return await run_in_threadpool(_call, store.new_disclosure, run_id, payload["expected_revision"], payload["expected_head_sha256"])

    @app.post(f"{web.PREFIX}/runs/{{run_id}}/evaluate")
    async def evaluate(run_id: str, request: Request):
        await web._payload(request, set())
        return await run_in_threadpool(_call, store.evaluate, run_id)

    @app.get(f"{web.PREFIX}/runs/{{run_id}}/evaluations/{{evaluation_id}}")
    def evaluation(run_id: str, evaluation_id: str):
        return _call(store.evaluation, run_id, evaluation_id)

    @app.get(f"{web.PREFIX}/runs/{{run_id}}/evaluations/{{evaluation_id}}/artifacts/{{name}}")
    def evaluation_artifact(run_id: str, evaluation_id: str, name: str):
        data = _call(store.evaluation_artifact, run_id, evaluation_id, name)
        return Response(data, media_type="text/plain" if name.endswith(".txt") else "application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get(f"{web.PREFIX}/runs/{{run_id}}/artifacts/{{name}}")
    def artifact(run_id: str, name: str):
        data = _call(store.artifact, run_id, name)
        return Response(data, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    return store
