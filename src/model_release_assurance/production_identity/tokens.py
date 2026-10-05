"""Pinned RS256 resource-server access tokens; no login, discovery or token minting.

Signed scopes/cases are only upper bounds. The application must still consult
current authoritative assignments, key/token revocations and case state.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from types import MappingProxyType

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

MAX_TOKEN_BYTES = 16 * 1024
MAX_HEADER_BYTES = 2 * 1024
MAX_PAYLOAD_BYTES = 8 * 1024
MAX_INTEGER = 2**53 - 1
REQUIRED_CLAIMS = frozenset({"iss", "sub", "aud", "iat", "nbf", "exp", "jti", "client_id", "scope", "case_ids"})
OPTIONAL_CLAIMS = frozenset({"acr", "auth_time"})


class TokenError(ValueError):
    """A safe rejection that contains no token, claim, key or cryptographic detail."""


def _reject():
    raise TokenError("Access token rejected")


def _text(value, maximum):
    if type(value) is not str or not 1 <= len(value) <= maximum:
        _reject()
    if any(ord(char) < 33 or ord(char) > 126 or char in "*?[]" for char in value):
        _reject()
    return value


def _integer(value):
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        _reject()
    return value


def _json_integer(value):
    if len(value) > 16:
        _reject()
    return _integer(int(value))


def _json_noninteger(value):
    _reject()


def _json_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            _reject()
        result[name] = value
    return result


def _decode_segment(segment, maximum):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", segment):
        _reject()
    decoded = base64.b64decode(segment + "=" * (-len(segment) % 4), altchars=b"-_", validate=True)
    if len(decoded) > maximum or base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != segment:
        _reject()
    return decoded


def _decode_object(segment, maximum):
    content = _decode_segment(segment, maximum)
    result = json.loads(content.decode("utf-8"), object_pairs_hook=_json_object,
                        parse_int=_json_integer, parse_float=_json_noninteger, parse_constant=_json_noninteger)
    if type(result) is not dict:
        _reject()
    return result


@dataclass(frozen=True, slots=True)
class AccessIdentity:
    issuer: str
    subject: str
    client_id: str
    token_id: str
    key_id: str
    issued_at: int
    expires_at: int
    scopes: frozenset[str]
    case_ids: frozenset[str]
    acr: str | None
    auth_time: int | None


@dataclass(frozen=True, slots=True, init=False)
class AccessTokenVerifier:
    issuer: str
    audience: str
    max_ttl_seconds: int
    _keys: Mapping[str, rsa.RSAPublicKey]

    def __init__(self, issuer: str, audience: str,
                 keys: Mapping[str, str | bytes | rsa.RSAPublicKey], max_ttl_seconds: int = 300):
        try:
            _text(issuer, 512)
            _text(audience, 256)
            if type(max_ttl_seconds) is not int or not 1 <= max_ttl_seconds <= 300:
                _reject()
            if not isinstance(keys, Mapping) or not 1 <= len(keys) <= 32:
                _reject()
            accepted = {}
            for key_id, material in keys.items():
                if type(key_id) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", key_id):
                    _reject()
                if isinstance(material, rsa.RSAPublicKey):
                    key = material
                else:
                    if type(material) is str:
                        material = material.encode("ascii")
                    if type(material) is not bytes or not 1 <= len(material) <= 16 * 1024:
                        _reject()
                    key = serialization.load_pem_public_key(material)
                if not isinstance(key, rsa.RSAPublicKey) or not 2048 <= key.key_size <= 8192:
                    _reject()
                accepted[key_id] = key
            object.__setattr__(self, "issuer", issuer)
            object.__setattr__(self, "audience", audience)
            object.__setattr__(self, "max_ttl_seconds", max_ttl_seconds)
            object.__setattr__(self, "_keys", MappingProxyType(accepted))
        except (ValueError, TypeError, UnicodeError, UnsupportedAlgorithm):
            raise TokenError("Invalid access-token verifier configuration") from None

    def verify(self, token: str, *, now: int) -> AccessIdentity:
        """Verify against pinned keys and the caller's trusted integer UTC clock.

        PyJWT verifies the fixed algorithm/signature/issuer/audience. Explicit
        checks below enforce time using ``now`` with zero clock tolerance; PyJWT's
        wall-clock time checks are disabled only to use this same supplied clock.
        """
        try:
            return self._verify(token, now=now)
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, jwt.PyJWTError):
            raise TokenError("Access token rejected") from None

    def _verify(self, token, *, now):
        _integer(now)
        if type(token) is not str or not 1 <= len(token) <= MAX_TOKEN_BYTES or not token.isascii():
            _reject()
        segments = token.split(".")
        if len(segments) != 3:
            _reject()
        header = _decode_object(segments[0], MAX_HEADER_BYTES)
        if set(header) != {"alg", "typ", "kid"} or header["alg"] != "RS256":
            _reject()
        if header["typ"] not in ("at+jwt", "application/at+jwt"):
            _reject()
        key_id = _text(header["kid"], 128)
        if key_id not in self._keys:
            _reject()
        key = self._keys[key_id]
        signature = _decode_segment(segments[2], 1024)
        if len(signature) != (key.key_size + 7) // 8:
            _reject()
        claims = _decode_object(segments[1], MAX_PAYLOAD_BYTES)
        if not REQUIRED_CLAIMS <= set(claims) or set(claims) - REQUIRED_CLAIMS - OPTIONAL_CLAIMS:
            _reject()
        if _text(claims["iss"], 512) != self.issuer or _text(claims["aud"], 256) != self.audience:
            _reject()
        subject = _text(claims["sub"], 256)
        client_id = _text(claims["client_id"], 256)
        token_id = _text(claims["jti"], 256)
        issued_at, not_before, expires_at = (_integer(claims[name]) for name in ("iat", "nbf", "exp"))
        raw_scope = claims["scope"]
        if type(raw_scope) is not str or not 1 <= len(raw_scope) <= 4096:
            _reject()
        scope_items = raw_scope.split(" ")
        if not 1 <= len(scope_items) <= 64 or len(set(scope_items)) != len(scope_items):
            _reject()
        scopes = frozenset(_text(item, 128) for item in scope_items)
        raw_cases = claims["case_ids"]
        if type(raw_cases) is not list or not 1 <= len(raw_cases) <= 64:
            _reject()
        cases = frozenset(_text(item, 128) for item in raw_cases)
        if len(cases) != len(raw_cases):
            _reject()
        acr = _text(claims["acr"], 256) if "acr" in claims else None
        auth_time = _integer(claims["auth_time"]) if "auth_time" in claims else None
        verified = jwt.decode(token, key=key, algorithms=["RS256"], issuer=self.issuer, audience=self.audience,
                              options={"verify_signature": True, "verify_iss": True, "verify_aud": True,
                                       "verify_sub": True, "verify_jti": True, "strict_aud": True,
                                       "verify_iat": False, "verify_nbf": False, "verify_exp": False,
                                       "require": sorted(REQUIRED_CLAIMS)})
        if verified != claims:
            _reject()
        if not issued_at <= now or not not_before <= now < expires_at:
            _reject()
        if not issued_at <= not_before <= expires_at or not 0 < expires_at - issued_at <= self.max_ttl_seconds:
            _reject()
        if auth_time is not None and auth_time > issued_at:
            _reject()
        return AccessIdentity(issuer=self.issuer, subject=subject, client_id=client_id, token_id=token_id,
                              key_id=key_id, issued_at=issued_at, expires_at=expires_at,
                              scopes=scopes, case_ids=cases, acr=acr, auth_time=auth_time)
