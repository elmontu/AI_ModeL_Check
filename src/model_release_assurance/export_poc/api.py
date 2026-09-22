"""Trusted-loopback temporal dashboard and retained synthetic export controls.

This process has access to its own private staging database. It is deliberately
not an authenticated agency service or an isolation boundary against its owner.
The two research workflows have separate registries and release histories.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .store import ExportDenied, ExportStore


class Prepare(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    stage: Literal[1, 2]
    route: Literal["first", "retained-state", "independent", "central-count"]
    expected_revision: int = Field(ge=0, le=1_000_000)


class Commit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    expected_revision: int = Field(ge=0, le=1_000_000)


class Revoke(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    release_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


def create_app(root: Path, *, repository: Path | None = None,
               temporal_run: Path | None = None, temporal_operator: Path | None = None) -> FastAPI:
    store = ExportStore(root)
    app = FastAPI(title="Temporal model release assurance", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.export_store = store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    static = Path(__file__).parent / "static"
    temporal_static = Path(__file__).parents[1] / "temporal_assurance" / "static"
    from ..temporal_assurance.web import create_router
    app.include_router(create_router(repository or Path(__file__).resolve().parents[3],
                                     run_root=temporal_run, operator_root=temporal_operator))

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and (urlsplit(origin).netloc != request.headers.get("host") or urlsplit(origin).scheme != request.url.scheme):
                return JSONResponse({"detail": "Cross-origin mutations are refused."}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
                return JSONResponse({"detail": "JSON is required."}, status_code=415)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 4096:
                    return JSONResponse({"detail": "Request is too large."}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        return response

    @app.exception_handler(ExportDenied)
    async def denied(request, exc):
        status = 404 if exc.code in {"not_found", "unknown_release", "unknown_request"} else 409
        return JSONResponse({"code": exc.code, "detail": str(exc)}, status_code=status)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"code": "invalid_request", "detail": str(exc)}, status_code=409)

    @app.get("/healthz")
    def health():
        return {"status": "ok", "mode": "local-temporal-assurance", "agency_deployment": False,
                "synthetic_lab": "/synthetic"}

    @app.get("/api/status")
    def status():
        return store.status()

    @app.get("/api/capabilities")
    def capabilities():
        from .tools import export_construction_catalog
        return export_construction_catalog()

    @app.get("/api/history/verify")
    def verify_history():
        return store.verify_history()

    @app.get("/api/plan")
    def plan(route: Literal["first", "reuse", "retained-state", "independent", "central-count"]):
        from .protocol import plan_export
        return plan_export(store.status(), route)

    @app.post("/api/prepare")
    def prepare(payload: Prepare):
        return store.prepare(**payload.model_dump())

    @app.post("/api/commit")
    def commit(payload: Commit):
        return store.commit(**payload.model_dump())

    @app.post("/api/revoke")
    def revoke(payload: Revoke):
        return store.revoke(payload.release_id)

    @app.get("/api/exports/{release_id}")
    def download(release_id: str):
        content = store.download(release_id)
        digest = hashlib.sha256(content).hexdigest()
        return Response(content, media_type="application/json", headers={
            "Content-Disposition": 'attachment; filename="committed-model.json"',
            "X-Artifact-SHA256": digest,
        })

    @app.get("/api/exports/{release_id}/evaluation")
    def evaluation(release_id: str):
        from .mechanism import public_fixture_evaluation
        # Only committed, still downloadable artifacts can be evaluated here.
        # Labels are a fixed public synthetic fixture, never uploaded agency data.
        return public_fixture_evaluation(store.download(release_id))

    @app.get("/")
    def index():
        return FileResponse(temporal_static / "index.html")

    @app.get("/synthetic")
    def synthetic_index():
        return FileResponse(static / "index.html")

    @app.get("/temporal-assets/{name}")
    def temporal_asset(name: str):
        if name not in {"app.js", "style.css"}:
            return JSONResponse({"detail": "Not found."}, status_code=404)
        return FileResponse(temporal_static / name)

    @app.get("/assets/{name}")
    def asset(name: str):
        if name not in {"app.js", "style.css"}:
            return JSONResponse({"detail": "Not found."}, status_code=404)
        return FileResponse(static / name)

    return app
