"""Explicit public-fixture HTTP boundary; no agency login or model delivery."""
from __future__ import annotations

import json
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .policy import Conflict, FixtureIdentityService, IdentityUnavailable, PermissionDenied
from .tokens import TokenError

MAX_BODY_BYTES = 8192
MAX_BEARER_BYTES = 16_384
FLAGS = {"fixture_only": True, "authorization_eligible": False, "model_delivery": False}


def _invalid_token():
    return HTTPException(401, "invalid_token", headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})


def _bearer(request: Request) -> str:
    values = [value for key, value in request.scope["headers"] if key.lower() == b"authorization"]
    if len(values) != 1 or not 1 <= len(values[0]) <= MAX_BEARER_BYTES:
        raise _invalid_token()
    try:
        value = values[0].decode("ascii")
    except UnicodeError:
        raise _invalid_token() from None
    scheme, separator, token = value.partition(" ")
    if scheme.lower() != "bearer" or separator != " " or not token or any(char.isspace() for char in token):
        raise _invalid_token()
    return token


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite number")


async def _body(request: Request) -> dict:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "json_required")
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_BODY_BYTES:
            raise HTTPException(413, "request_too_large")
    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(400, "invalid_request") from None
    if type(value) is not dict:
        raise HTTPException(400, "invalid_request")
    return value


async def _expected_digest(request: Request) -> str:
    body = await _body(request)
    if set(body) != {"expected_digest"} or type(body["expected_digest"]) is not str or not re.fullmatch("[0-9a-f]{64}", body["expected_digest"]):
        raise HTTPException(400, "invalid_request")
    return body["expected_digest"]


def create_fixture_app(service: FixtureIdentityService, *, environment: str) -> FastAPI:
    """Only expose a caller-constructed fictional service; production startup is unsupported."""
    if environment != "public_fixture" or not isinstance(service, FixtureIdentityService):
        raise ValueError("Only the public_fixture identity boundary is implemented")
    app = FastAPI(title="MRA public-fixture identity boundary", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        # No browser session, cookies or query-token transport are implemented.
        if request.headers.get("origin") is not None or request.headers.get("cookie") is not None:
            response = JSONResponse({"detail": "browser_session_unsupported", **FLAGS}, status_code=403)
        elif request.url.query:
            response = JSONResponse({"detail": "query_parameters_unsupported", **FLAGS}, status_code=400)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(TokenError)
    async def invalid_identity(request, error):
        return JSONResponse({"detail": "invalid_token", **FLAGS}, status_code=401,
                            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})

    @app.exception_handler(PermissionDenied)
    async def denied(request, error):
        return JSONResponse({"detail": "forbidden", **FLAGS}, status_code=403)

    @app.exception_handler(IdentityUnavailable)
    async def unavailable(request, error):
        return JSONResponse({"detail": "identity_unavailable", **FLAGS}, status_code=503)

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return JSONResponse({"detail": "stale_or_conflicting_request", **FLAGS}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid_request(request, error):
        return JSONResponse({"detail": "invalid_request", **FLAGS}, status_code=400)

    @app.get("/healthz")
    def health():
        return {"status": "ok", **FLAGS}

    @app.get("/v1/cases/{case_id}")
    def read_case(case_id: str, request: Request):
        return service.read_case(_bearer(request), case_id)

    @app.post("/v1/cases/{case_id}/proposals")
    async def submit_proposal(case_id: str, request: Request):
        token = _bearer(request)
        payload = await _body(request)
        if set(payload) != {"artifact_sha256", "evidence_sha256", "policy_sha256", "recipient_id", "revision"}:
            raise HTTPException(400, "invalid_request")
        return service.submit_proposal(token, case_id, payload)

    @app.post("/v1/cases/{case_id}/assessment")
    async def assess(case_id: str, request: Request):
        token = _bearer(request)
        digest = await _expected_digest(request)
        return service.assess(token, case_id, digest)

    @app.post("/v1/cases/{case_id}/approval")
    async def approve(case_id: str, request: Request):
        token = _bearer(request)
        digest = await _expected_digest(request)
        return service.approve(token, case_id, digest)

    @app.post("/v1/cases/{case_id}/job-check")
    async def check_job(case_id: str, request: Request):
        token = _bearer(request)
        if await _body(request):
            raise HTTPException(400, "invalid_request")
        return service.check_job(token, case_id)

    return app
