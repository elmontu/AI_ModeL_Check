"""Loopback pre-POC API. Trusted local file binding for educational cases."""
from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import workflow
from .store import Store
from .options import LanguageOptions, TrainingOptions


class NewCase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    kind: workflow.Kind
    route: workflow.Route
    mode: workflow.Mode = "education"


class CaseMode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: workflow.Mode


class CaseBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: Literal["candidate", "lineage", "request", "agency-scope", "evaluation-plan", "utility-report", "security-report", "independent-review"]
    path: str = Field(min_length=1, max_length=4096)


class NewJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["reference", "training", "check", "assess", "language"]
    case_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    training: TrainingOptions | None = None
    language: LanguageOptions | None = None


def create_app(root: Path) -> FastAPI:
    store = Store(root)
    app = FastAPI(title="MRA local testing console", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    static = Path(__file__).parent / "static"

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        # Require a non-simple same-origin request for mutations, blocking browser drive-by POSTs.
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and (urlsplit(origin).netloc != request.headers.get("host") or urlsplit(origin).scheme != request.url.scheme):
                return JSONResponse({"detail": "cross-origin mutations are refused"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "JSON required"}, status_code=415)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16_384:
                    return JSONResponse({"detail": "request too large"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "case or job not found"}, status_code=404)

    @app.get("/api/capabilities")
    def capabilities():
        from ..public_models import capability_inventory
        return capability_inventory()

    @app.get("/api/language/models")
    def language_models():
        from ..language_red_team import models
        try:
            return {"available":True,"models":models()}
        except Exception:
            return {"available":False,"models":[]}

    @app.get("/healthz")
    def health():
        return {"status": "ok", "authorization_eligible": False}

    @app.get("/api/status")
    def status():
        store.recover()
        return store.status()

    @app.get("/api/cases")
    def cases():
        return store.list_cases()

    @app.post("/api/cases", status_code=201)
    def new_case(payload: NewCase):
        return store.create_case(payload.name, payload.kind, payload.route, payload.mode)

    @app.get("/api/cases/{case_id}")
    def case(case_id: str):
        result = store.case(case_id)
        project = workflow.load_project(store.case_path(case_id))
        result["mode"] = project.mode
        result["inputs"] = [{"slot": slot, "bound": ref is not None,
                             "path": ref.path if ref else None, "sha256": ref.sha256 if ref else None,
                             "required": project.mode != "education" or slot not in workflow.EDUCATION_OPTIONAL}
                            for slot, ref in project.files.items()]
        result["supporting_inputs"] = [{"slot": slot, "path": ref.path, "sha256": ref.sha256}
                                      for slot, ref in getattr(project, "supporting_files", {}).items()]
        result["operator_case_directory"] = f"cases/{case_id}"
        return result

    @app.post("/api/cases/{case_id}/mode")
    def case_mode(case_id: str, payload: CaseMode):
        return store.edit_case(case_id, mode=payload.mode)

    @app.post("/api/cases/{case_id}/bindings")
    def case_binding(case_id: str, payload: CaseBinding):
        return store.edit_case(case_id, slot=payload.slot, path=payload.path)

    @app.get("/api/jobs")
    def jobs():
        return store.list_jobs()

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        return store.job(job_id)

    @app.get("/api/jobs/{job_id}/artifacts")
    def artifact_inventory(job_id: str):
        from .artifacts import manifest
        return manifest(store, job_id)

    @app.get("/api/jobs/{job_id}/artifacts/{name:path}")
    def artifact_file(job_id: str, name: str):
        from .artifacts import file_path
        path = file_path(store, job_id, name)
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)

    @app.get("/api/jobs/{job_id}/bundle")
    def artifact_bundle(job_id: str):
        from .artifacts import bundle
        return Response(bundle(store, job_id), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="mra-{job_id}-evidence.zip"'})

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        return store.cancel(job_id)

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str):
        return store.retry(job_id)

    @app.post("/api/jobs", status_code=202)
    def new_job(payload: NewJob):
        if payload.kind == "language":
            if payload.language is None or payload.training is not None:
                raise ValueError("language job requires an installed model selection")
            return store.enqueue(payload.kind, payload.case_id, payload.language.model_dump())
        if payload.language is not None:
            raise ValueError("language options require a language job")
        return store.enqueue(payload.kind, payload.case_id, payload.training.model_dump() if payload.training else None)

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    @app.get("/api/docs")
    def docs():
        return FileResponse(static / "api.html")

    @app.get("/assets/{name}")
    def asset(name: str):
        if name not in {"app.js", "style.css"}:
            raise HTTPException(404)
        return FileResponse(static / name)

    return app
