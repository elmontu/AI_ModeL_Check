"""No-listener HTTP test boundary for the controlled public-fixture gateway.

No browser sessions, URL tokens, direct files, arbitrary formats or production
startup. Chunk writes use only the service's fixed internal response buffer.
Returning that buffer is not proof of recipient receipt on a real network.
"""
from __future__ import annotations

import base64

from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import JSONResponse,Response

from .contracts import FLAGS,DeliveryError,canonical_bytes
from .gateway import FixtureDeliveryGateway
from .store import StoreError,StoreConflict,StoreUnavailable
from ..production_identity.api import _bearer,_body
from ..production_identity.policy import PermissionDenied,IdentityUnavailable
from ..production_identity.tokens import TokenError


async def _exact(request,fields):
    result=await _body(request)
    if set(result)!=set(fields):
        raise HTTPException(400,"invalid_request")
    return result


def create_fixture_app(gateway,*,profile="agency_private_cloud"):
    if type(gateway) is not FixtureDeliveryGateway or profile!="local_public_fixture":
        raise DeliveryError("Production delivery HTTP startup is not qualified")
    app=FastAPI(title="MRA controlled public-fixture delivery",docs_url=None,redoc_url=None,openapi_url=None)

    @app.middleware("http")
    async def boundary(request,call_next):
        if request.headers.get("origin") is not None or request.headers.get("cookie") is not None:
            response=JSONResponse({"detail":"browser_session_unsupported",**FLAGS},status_code=403)
        elif request.url.query:
            response=JSONResponse({"detail":"query_parameters_unsupported",**FLAGS},status_code=400)
        else:
            response=await call_next(request)
        response.headers["Cache-Control"]="no-store"
        response.headers["Pragma"]="no-cache"
        response.headers["X-Content-Type-Options"]="nosniff"
        return response

    async def invalid(request,error):
        return JSONResponse({"detail":"invalid_request",**FLAGS},status_code=400)
    app.add_exception_handler(DeliveryError,invalid)
    app.add_exception_handler(StoreError,invalid)

    @app.exception_handler(TokenError)
    async def token_error(request,error):
        return JSONResponse({"detail":"invalid_token",**FLAGS},status_code=401,
            headers={"WWW-Authenticate":'Bearer error="invalid_token"'})
    @app.exception_handler(PermissionDenied)
    async def denied(request,error):
        return JSONResponse({"detail":"forbidden",**FLAGS},status_code=403)
    @app.exception_handler(IdentityUnavailable)
    async def identity_unavailable(request,error):
        return JSONResponse({"detail":"identity_unavailable",**FLAGS},status_code=503)
    @app.exception_handler(StoreUnavailable)
    async def store_unavailable(request,error):
        return JSONResponse({"detail":"delivery_unavailable",**FLAGS},status_code=503)
    @app.exception_handler(StoreConflict)
    async def conflict(request,error):
        return JSONResponse({"detail":"stale_or_conflicting_request",**FLAGS},status_code=409)

    @app.get("/healthz")
    def health():
        return {"status":"ok",**FLAGS}

    @app.get("/v1/cases/{case_id}")
    def metadata(case_id,request:Request):
        return gateway.status(_bearer(request),case_id)

    @app.post("/v1/cases/{case_id}/activations")
    async def activate(case_id,request:Request):
        token=_bearer(request);body=await _exact(request,{"campaign_id","ttl_seconds"})
        return gateway.activate(token,case_id,body["campaign_id"],ttl_seconds=body["ttl_seconds"],profile=profile)

    @app.post("/v1/cases/{case_id}/activations/{activation_id}/grants")
    async def grant(case_id,activation_id,request:Request):
        token=_bearer(request);body=await _exact(request,{"recipient_token","ttl_seconds"})
        return gateway.grant(token,case_id,activation_id,body["recipient_token"],ttl_seconds=body["ttl_seconds"])

    @app.post("/v1/cases/{case_id}/activations/{activation_id}/chunks")
    async def chunk(case_id,activation_id,request:Request):
        token=_bearer(request)
        body=await _exact(request,{"grant_id","transfer_id","offset","length","request_id","chunk_id"})
        returned=[]
        def writer(content):
            returned.append(content)
            return len(content)
        receipt=gateway.deliver_chunk(token,case_id,activation_id,body["grant_id"],body["transfer_id"],
            body["offset"],body["length"],request_id=body["request_id"],chunk_id=body["chunk_id"],writer=writer)
        if receipt["status"]!="returned" or not receipt["observation_recorded"]:
            # A buffered response has not been emitted; the attempted admission
            # still remains durable. Production streaming is not implemented.
            raise StoreUnavailable("Delivery response is uncertain")
        content=b"".join(returned)
        return Response(content,media_type="application/octet-stream",headers={
            "X-MRA-Admission":receipt["admission"]["sha256"],
            "X-MRA-Receipt":base64.b64encode(canonical_bytes(receipt)).decode("ascii"),
            "Content-Disposition":'attachment; filename="public-fixture.chunk"'})

    def management(action):
        async def handler(case_id:str,activation_id:str,request:Request):
            token=_bearer(request);await _exact(request,set())
            return getattr(gateway,action)(token,case_id,activation_id)
        return handler
    for action in ("suspend","resume","revoke"):
        app.add_api_route("/v1/cases/{case_id}/activations/{activation_id}/"+action,management(action),methods=["POST"])

    @app.post("/v1/cases/{case_id}/grants/{grant_id}/revoke")
    async def revoke_grant(case_id,grant_id,request:Request):
        token=_bearer(request);await _exact(request,set())
        return gateway.revoke_grant(token,case_id,grant_id)

    return app
