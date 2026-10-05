"""Bounded public-fixture storage HTTP; no private intake or model delivery."""
from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..production_identity.policy import Conflict, IdentityUnavailable, PermissionDenied
from ..production_identity.tokens import TokenError
from .backend import StorageError
from .service import FixtureStorageService

MAX_BODY_BYTES = 32_768
MAX_BEARER_BYTES = 16_384
FLAGS = {"fixture_only": True, "authorization_eligible": False, "model_delivery": False}


def _bearer(request):
    values = [value for key, value in request.scope["headers"] if key.lower() == b"authorization"]
    if len(values) != 1 or not 1 <= len(values[0]) <= MAX_BEARER_BYTES:
        raise HTTPException(401, "invalid_token")
    try:
        scheme, separator, token = values[0].decode("ascii").partition(" ")
    except UnicodeError:
        raise HTTPException(401, "invalid_token") from None
    if scheme.lower() != "bearer" or separator != " " or not token or any(c.isspace() for c in token):
        raise HTTPException(401, "invalid_token")
    return token


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate field")
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError("Nonfinite number")


async def _body(request, fields):
    types = [value for key, value in request.scope["headers"] if key.lower() == b"content-type"]
    if len(types) != 1 or types[0].split(b";", 1)[0].strip().lower() != b"application/json":
        raise HTTPException(415, "json_required")
    if request.headers.get("content-encoding") is not None:
        raise HTTPException(415, "encoded_body_unsupported")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, "request_too_large")
        content.extend(chunk)
    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(400, "invalid_request") from None
    if type(value) is not dict or set(value) != set(fields):
        raise HTTPException(400, "invalid_request")
    return value


def create_fixture_app(service: FixtureStorageService, *, environment: str) -> FastAPI:
    """Require explicit construction with fictional state; no ready-to-serve app."""
    if environment != "public_fixture" or not isinstance(service, FixtureStorageService):
        raise ValueError("Only the public_fixture storage boundary is implemented")
    app = FastAPI(title="MRA public-fixture governed storage", docs_url=None,
                  redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.headers.get("origin") is not None or request.headers.get("cookie") is not None:
            response = JSONResponse({"detail": "browser_session_unsupported", **FLAGS}, status_code=403)
        elif request.url.query:
            response = JSONResponse({"detail": "query_parameters_unsupported", **FLAGS}, status_code=400)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-MRA-Fixture-Only"] = "true"
        response.headers["X-MRA-Authorization-Eligible"] = "false"
        response.headers["X-MRA-Model-Delivery"] = "false"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, error):
        headers = {"WWW-Authenticate": 'Bearer error="invalid_token"'} if error.status_code == 401 else None
        return JSONResponse({"detail": error.detail, **FLAGS}, status_code=error.status_code, headers=headers)

    @app.exception_handler(TokenError)
    async def invalid_token(request, error):
        return JSONResponse({"detail": "invalid_token", **FLAGS}, status_code=401,
                            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})

    @app.exception_handler(PermissionDenied)
    async def denied(request, error):
        return JSONResponse({"detail": "forbidden", **FLAGS}, status_code=403)

    @app.exception_handler(IdentityUnavailable)
    async def unavailable_identity(request, error):
        return JSONResponse({"detail": "identity_unavailable", **FLAGS}, status_code=503)

    @app.exception_handler(StorageError)
    async def unavailable_storage(request, error):
        return JSONResponse({"detail": "storage_unavailable", **FLAGS}, status_code=503)

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return JSONResponse({"detail": "stale_or_conflicting_request", **FLAGS}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid_request(request, error):
        return JSONResponse({"detail": "invalid_request", **FLAGS}, status_code=400)

    @app.get("/healthz")
    def health():
        return {"status": "ok", **FLAGS}

    @app.post("/v1/cases/{case_id}/fixture-objects")
    async def register(case_id: str, request: Request):
        token = _bearer(request)
        body = await _body(request, {"fixture_id", "retention_seconds"})
        return service.register_fixture(token, case_id, body["fixture_id"], body["retention_seconds"])

    @app.post("/v1/cases/{case_id}/object-metadata")
    async def metadata(case_id: str, request: Request):
        token = _bearer(request)
        body = await _body(request, {"reference"})
        return service.metadata(token, case_id, body["reference"])

    @app.post("/v1/cases/{case_id}/fixture-snapshots")
    async def snapshot(case_id: str, request: Request):
        token = _bearer(request)
        body = await _body(request, {"references"})
        return service.freeze_snapshot(token, case_id, body["references"])

    @app.post("/v1/cases/{case_id}/object-read-grants")
    async def grant(case_id: str, request: Request):
        token = _bearer(request)
        body = await _body(request, {"reference", "worker_token", "job_id", "ttl_seconds"})
        if type(body["worker_token"]) is not str or not 1 <= len(body["worker_token"]) <= MAX_BEARER_BYTES:
            raise HTTPException(400, "invalid_request")
        return service.issue_read_grant(token, case_id, body["reference"], body["worker_token"],
                                        body["job_id"], body["ttl_seconds"])

    @app.post("/v1/cases/{case_id}/object-reads")
    async def read(case_id: str, request: Request):
        token = _bearer(request)
        body = await _body(request, {"reference", "grant_id"})
        data = service.read(token, case_id, body["reference"], body["grant_id"])
        return Response(content=data, media_type="application/json")

    @app.post("/v1/cases/{case_id}/object-read-grants/revoke")
    async def revoke(case_id: str, request: Request):
        token = _bearer(request)
        body = await _body(request, {"grant_id"})
        return service.revoke_grant(token, case_id, body["grant_id"])

    @app.post("/v1/cases/{case_id}/object-hold")
    async def hold(case_id: str, request: Request):
        token = _bearer(request)
        body = await _body(request, {"reference", "held"})
        return service.set_hold(token, case_id, body["reference"], body["held"])

    @app.post("/v1/cases/{case_id}/object-deletion-check")
    async def deletion_check(case_id: str, request: Request):
        token = _bearer(request)
        body = await _body(request, {"reference"})
        return service.deletion_eligibility(token, case_id, body["reference"])

    return app
