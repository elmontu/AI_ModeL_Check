"""Mount the sealed read-only readiness presentation inside the MRA application.

The outer ASGI boundary owns only the assurance namespace. Its bounds describe
ASGI's already parsed request representation, not physical HTTP wire lines.
Every configured request, including denied requests, uses a fresh sealed input
check and a fresh handler facade. No HTTP server, worker or benchmark is started.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from email.message import Message
from email.utils import formatdate
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote

from .protocol import (
    ERROR_BODIES, MAX_HEADER_BYTES, MAX_HEADER_LINE_BYTES,
    MAX_HEADER_LINES, MAX_REQUEST_LINE_BYTES,
)
from .server import PRACTICE_SAVES_SCRIPT, ReadinessHandler
from .portable import DemoConfig

PREFIX = "/assurance"
_ADAPTER_ERROR_BODIES = {**ERROR_BODIES, 403: b"Local assurance listener rejected.\n"}
_ORIGINAL_SCRIPT_SHA256 = "ff6982e58088e90479d0dbb09fb05f19c08816393d07eeafb302abf9e82ed47f"
_DEFAULT_CSP = "default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'"
_UNAVAILABLE = b"Snapshot unavailable: captured readiness or intake validation failed. No readiness or authorization claim is presented.\n"
_PIN = re.compile(r"[0-9a-f]{64}\Z")
_HEADER_NAME = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
_ATTRIBUTE = re.compile(r'''(?P<name>[^\s/<>=]+)(?P<equals>\s*=\s*)(?P<value>"[^"]*"|'[^']*'|[^\s>]+)''')
_BANNER = (
    '<aside class="notice" aria-label="Main application context">'
    '<p><a href="/">Return to the MRA application</a></p>'
    '<p>Readiness and learning within the MRA application. Agency decisions '
    'remain pending; all twelve real gaps remain open.</p></aside>'
)
_MIGRATION_NOTICE = (
    '<aside class="notice" aria-label="Saved-demo address change">'
    '<strong>Bring saved demos from the separate readiness address</strong>'
    '<p>This application address has its own browser storage. To copy demos '
    'you saved at the earlier address, open '
    '<a href="http://127.0.0.1:8770/practice-saves" target="_blank" '
    'rel="noopener noreferrer">the earlier saved-demo library</a>, select '
    'Export saved demos there, then use Import demo file here. Imports add '
    'new fictional copies. Nothing is copied automatically between addresses, '
    'and the earlier library remains unchanged.</p></aside>'
)


def _derive_script(raw: bytes) -> bytes:
    """Derive only the two fixed client navigation paths from the pinned asset."""
    if hashlib.sha256(raw).hexdigest() != _ORIGINAL_SCRIPT_SHA256:
        raise RuntimeError("The sealed saved-demo asset does not match its pin")
    for token in (b'return "/tutorial-practice?"', b'return "/tutorial-compare?"'):
        if raw.count(token) != 1:
            raise RuntimeError("The saved-demo navigation binding is unavailable")
        raw = raw.replace(token, token.replace(b'"/', b'"/assurance/'), 1)
    return raw


DERIVED_PRACTICE_SAVES_SCRIPT = _derive_script(PRACTICE_SAVES_SCRIPT)


@dataclass(frozen=True, slots=True)
class ReadinessConfig:
    """Immutable input locations and pins; construction performs no input I/O."""

    bundle: Path
    manifest_sha256: str
    intake_report: Path | None = None
    intake_manifest_sha256: str | None = None
    handoff_packet: Path | None = None
    handoff_archive_sha256: str | None = None
    handoff_manifest_sha256: str | None = None
    suspend_presentation: bool = False

    def __post_init__(self):
        if type(self.suspend_presentation) is not bool:
            raise ValueError("Presentation suspension must be a boolean")
        if (self.intake_report is None) != (self.intake_manifest_sha256 is None):
            raise ValueError("Intake location and pin must be supplied together")
        handoff = (self.handoff_packet, self.handoff_archive_sha256, self.handoff_manifest_sha256)
        if any(value is not None for value in handoff) and not all(value is not None for value in handoff):
            raise ValueError("Review packet location and pins must be supplied together")
        if self.handoff_packet is not None and self.intake_report is None:
            raise ValueError("A review packet requires a pinned intake report")
        for name in ("manifest_sha256", "intake_manifest_sha256", "handoff_archive_sha256", "handoff_manifest_sha256"):
            value = getattr(self, name)
            if value is not None and (type(value) is not str or _PIN.fullmatch(value) is None):
                raise ValueError("Captured input pins must be lowercase SHA-256 strings")
        if self.manifest_sha256 is None:
            raise ValueError("A captured bundle pin is required")
        for name in ("bundle", "intake_report", "handoff_packet"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, Path(value))
        if self.bundle is None:
            raise ValueError("A captured bundle location is required")


def default_config(repository: Path) -> ReadinessConfig:
    """Select the existing captured inputs without opening or changing them."""
    repository = Path(repository)
    if not repository.is_absolute():
        raise ValueError("The repository location must be absolute")
    verification = repository / ".local" / "verification"
    return ReadinessConfig(
        bundle=verification / "platform-readiness-remediation-20261019" / "bundle",
        manifest_sha256="397f8734a1b5b248e97fe116cea01f638039254fdc129b1df9b1e62ab4c99c13",
        intake_report=verification / "platform-evidence-intake-20261019" / "report",
        intake_manifest_sha256="7041b7ddf7cb9a299231b9f9516ef4d5f5a27290f63a7295d5fde56768ab9f1b",
        handoff_packet=verification / "platform-review-handoff-20261019" / "packet",
        handoff_archive_sha256="bb08a3be22c14fcda6bd124fb5442e64755c8cafded9045329475b6823a7bbf4",
        handoff_manifest_sha256="59bd56e17566468e422e5713fc162ab36a3fd5c603889560b427450b5be9d1ba",
    )


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: tuple[tuple[bytes, bytes], ...]
    body: bytes


@dataclass(frozen=True, slots=True)
class _RequestContext:
    config: ReadinessConfig
    server_port: int

    def __getattr__(self, name):
        return getattr(self.config, name)


class _PrefixHTML(HTMLParser):
    """Keep original text and tags; edit only named root-relative URL values."""

    def __init__(self, *, saved_page=False, banner=_BANNER):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self.saved_page = saved_page
        self.banner = banner

    @staticmethod
    def _tag(raw):
        def replace(match):
            if match["name"].lower() not in ("href", "action", "src"):
                return match[0]
            value = match["value"]
            quote = value[:1] if value[:1] in ("'", '"') else ""
            inner = value[1:-1] if quote else value
            if inner.startswith("/") and not inner.startswith("//"):
                inner = PREFIX + inner
            return match["name"] + match["equals"] + quote + inner + quote
        return _ATTRIBUTE.sub(replace, raw)

    def handle_starttag(self, tag, attrs):
        self.parts.append(self._tag(self.get_starttag_text()))
        if tag == "body":
            # These are deliberately inserted after rewriting: the return link
            # addresses the main app, and the migration link addresses 8770.
            self.parts.append(self.banner)
            if self.saved_page:
                self.parts.append(_MIGRATION_NOTICE)

    def handle_startendtag(self, tag, attrs):
        self.parts.append(self._tag(self.get_starttag_text()))

    def handle_endtag(self, tag):
        self.parts.append("</" + tag + ">")

    def handle_data(self, data):
        self.parts.append(data)

    def handle_entityref(self, name):
        self.parts.append("&" + name + ";")

    def handle_charref(self, name):
        self.parts.append("&#" + name + ";")

    def handle_decl(self, decl):
        self.parts.append("<!" + decl + ">")

    def handle_comment(self, data):
        self.parts.append("<!--" + data + "-->")

    def handle_pi(self, data):
        self.parts.append("<?" + data + ">")

    def unknown_decl(self, data):
        self.parts.append("<![" + data + "]>")


def prefix_html(raw: bytes, *, saved_page=False, banner=_BANNER) -> bytes:
    parser = _PrefixHTML(saved_page=saved_page, banner=banner)
    parser.feed(raw.decode("utf-8"))
    parser.close()
    return "".join(parser.parts).encode("utf-8")


def _response(code, raw, method, mime="text/plain; charset=utf-8", filename=None, csp=None):
    headers = [
        (b"server", b"MRAReadiness/1"),
        (b"date", formatdate(usegmt=True).encode("ascii")),
        (b"content-type", mime.encode("ascii")),
        (b"content-length", str(len(raw)).encode("ascii")),
        (b"cache-control", b"no-store, max-age=0"),
        (b"pragma", b"no-cache"),
        (b"x-content-type-options", b"nosniff"),
        (b"content-security-policy", (csp or _DEFAULT_CSP).encode("ascii")),
        (b"referrer-policy", b"no-referrer"),
        (b"x-frame-options", b"DENY"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        (b"connection", b"close"),
    ]
    if code == 503:
        headers.append((b"link", b'</assurance/local-status>; rel="help"; title="Local captured-input status"'))
    if code == 405:
        headers.append((b"allow", b"GET, HEAD"))
    if filename:
        headers.append((b"content-disposition", ('attachment; filename="' + filename + '"').encode("ascii")))
    return Response(code, tuple(headers), b"" if method == "HEAD" else raw)


def _namespace_path(value):
    """Identify the exact namespace, including ambiguous encodings of it."""
    if type(value) is not str:
        return False
    variants = (value, unquote(value), posixpath.normpath(unquote(value).replace("\\", "/")))
    return any(part == PREFIX or part.startswith(PREFIX + "/") or
               ("/" + part.lstrip("/")) == PREFIX or
               ("/" + part.lstrip("/")).startswith(PREFIX + "/")
               for part in variants)


def owns_scope(scope):
    """Leave every other ASGI route and all non-HTTP scopes upstream."""
    if scope.get("type") != "http":
        return False
    raw = scope.get("raw_path", b"")
    raw_text = raw.decode("latin-1") if type(raw) is bytes else ""
    return _namespace_path(scope.get("path")) or _namespace_path(raw_text)


def _request_parts(scope):
    """Bound the parsed ASGI representation and preserve duplicate headers."""
    error = None
    method = scope.get("method")
    if type(method) is not str or not method or not method.isascii() or not _HEADER_NAME.fullmatch(method.encode("ascii")):
        method, error = "GET", 400
    version = scope.get("http_version", "1.1")
    if version not in ("1.0", "1.1"):
        error = error or 505
    path = scope.get("path")
    raw_path = scope.get("raw_path")
    if raw_path is None and type(path) is str:
        raw_path = path.encode("utf-8")
    query = scope.get("query_string", b"")
    if type(raw_path) is not bytes or type(query) is not bytes:
        raw_path, query, error = b"/assurance", b"", error or 400
    target = raw_path + (b"?" + query if query else b"")
    # This is the byte representation available after the ASGI server parser.
    # It cannot establish the lengths of the original physical network lines.
    if len(method.encode("ascii")) + len(target) + len(str(version)) + 10 > MAX_REQUEST_LINE_BYTES:
        error = 414
    headers = Message()
    supplied = scope.get("headers", ())
    if not isinstance(supplied, (list, tuple)):
        supplied, error = (), error or 400
    if len(supplied) > MAX_HEADER_LINES:
        error = error or 431
    total = 2
    for pair in supplied[:MAX_HEADER_LINES]:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(type(part) is not bytes for part in pair):
            error = error or 400
            continue
        name, value = pair
        line_bytes = len(name) + len(value) + 4
        total += line_bytes
        if line_bytes > MAX_HEADER_LINE_BYTES or total > MAX_HEADER_BYTES:
            error = error or 431
            continue
        if not _HEADER_NAME.fullmatch(name) or any(char in value for char in (b"\r", b"\n", b"\x00")):
            error = error or 400
            continue
        # Message retains repeated fields; the sealed handler requires exactly
        # one expected Host and at most one exact same-origin Origin.
        headers[name.decode("ascii")] = value.decode("latin-1")
    logical = "/__asgi_boundary_denied__"
    try:
        raw_text = raw_path.decode("ascii")
        query_text = query.decode("ascii")
        if type(path) is not str or raw_text != path:
            raise ValueError
        if not (raw_text == PREFIX or raw_text.startswith(PREFIX + "/")):
            raise ValueError
        if any(character in raw_text for character in ("%", "\\", "?", "#", "\x00", "\r", "\n")):
            raise ValueError
        if "//" in raw_text or any(part in (".", "..") for part in raw_text.split("/")):
            raise ValueError
        if any(ord(character) < 32 or ord(character) == 127 for character in query_text):
            raise ValueError
        logical = raw_text[len(PREFIX):] or "/"
        logical += "?" + query_text if query else ""
    except (UnicodeError, ValueError):
        error = error or 400
    server = scope.get("server")
    port = server[1] if isinstance(server, (tuple, list)) and len(server) == 2 else None
    if type(port) is not int or not 1 <= port <= 65535:
        port, error = 0, error or 400
    # The main console may deliberately use another listener. Its unrelated
    # routes are untouched, but captured assurance content remains loopback-only.
    if not isinstance(server, (tuple, list)) or len(server) != 2 or server[0] != "127.0.0.1":
        error = error or 403
    return method, logical, headers, port, error


class _Facade(ReadinessHandler):
    """A socket-free, single-request use of the sealed request dispatcher."""

    def __init__(self, config, port, method, path, headers, forced_error=None, body_present=False):
        self.server = _RequestContext(config, port)
        self.command = method
        self.path = "/__asgi_boundary_denied__" if forced_error else path
        self.headers = headers
        self.forced_error = forced_error
        self.body_present = body_present
        self.response = None
        self.logical_path = path.split("?", 1)[0]

    def _send(self, code, raw, mime="text/plain; charset=utf-8", filename=None, csp=None):
        if self.forced_error and code != 503:
            code = self.forced_error
            raw = b"Request bodies are not accepted.\n" if self.body_present and code == 400 else _ADAPTER_ERROR_BODIES[code]
            mime, filename, csp = "text/plain; charset=utf-8", None, None
        elif mime.startswith("text/html"):
            raw = prefix_html(raw, saved_page=self.logical_path == "/practice-saves")
        elif code == 200 and self.logical_path == "/assets/practice-saves.js":
            raw = DERIVED_PRACTICE_SAVES_SCRIPT
        self.response = _response(code, raw, self.command, mime, filename, csp)


def dispatch_http(scope, config, *, body_present=False, forced_error=None) -> Response:
    """Dispatch one assurance request; caller must supply an owned HTTP scope.

    ``forced_error`` injects a fixed boundary denial only after the existing
    input checker has run. Failed or suspended input presentation retains the
    sealed 503 priority. The adapter never returns a handler or captured input.
    """
    method, path, headers, port, boundary_error = _request_parts(scope)
    if forced_error is not None and (type(forced_error) is not int or forced_error not in _ADAPTER_ERROR_BODIES):
        raise ValueError("Unsupported fixed ASGI boundary error")
    if type(body_present) is not bool:
        raise ValueError("Body presence must be a boolean")
    if config is None:
        return _response(503, _UNAVAILABLE, method)
    error = forced_error or boundary_error or (400 if body_present else None)
    if isinstance(config, DemoConfig):
        from .portable import dispatch_demo
        return dispatch_demo(method, path, headers, port, error=error, body_present=body_present)
    if not isinstance(config, ReadinessConfig):
        raise TypeError("A ReadinessConfig, DemoConfig or None is required")
    facade = _Facade(config, port, method, path, headers, error, body_present)
    try:
        facade._request()
        if facade.response is None:
            raise RuntimeError("The read-only dispatcher returned no response")
        return facade.response
    except Exception:
        # The failed check or rendering detail is neither echoed nor replaced
        # by a cached captured view. Main application routes remain independent.
        return _response(503, _UNAVAILABLE, method)


class AssuranceApplication:
    """Outer ASGI adapter; no lifespan action and no independent listening port."""

    def __init__(self, main_app, config=None):
        if config is not None and not isinstance(config, (ReadinessConfig, DemoConfig)):
            raise TypeError("A ReadinessConfig, DemoConfig or None is required")
        self.main_app = main_app
        self.config = config

    async def __call__(self, scope, receive, send):
        if not owns_scope(scope):
            await self.main_app(scope, receive, send)
            return
        method, _, headers, port, boundary_error = _request_parts(scope)
        expected = f"127.0.0.1:{port}"
        hosts = headers.get_all("Host", [])
        origins = headers.get_all("Origin", [])
        inspect_body = (
            self.config is not None and not boundary_error and
            method in ("GET", "HEAD") and hosts == [expected] and
            (not origins or origins == [f"http://{expected}"]) and
            not headers.get_all("Expect", []) and
            not headers.get_all("Transfer-Encoding", []) and
            headers.get_all("Content-Length", []) in ([], ["0"])
        )
        body_present = False
        if inspect_body:
            # Reading an Expect request can itself trigger Uvicorn's interim
            # 100 Continue. Requests already denied by the sealed guards must
            # reach those guards without calling receive or reading a body.
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            body_present = (message.get("type") != "http.request" or
                            bool(message.get("body", b"")) or
                            bool(message.get("more_body", False)))
        # An empty streamed first chunk is also refused; body data is never
        # accumulated or handed to the read-only presentation dispatcher.
        response = await asyncio.to_thread(dispatch_http, scope, self.config, body_present=body_present)
        await send({"type": "http.response.start", "status": response.status, "headers": list(response.headers)})
        await send({"type": "http.response.body", "body": response.body, "more_body": False})


__all__ = [
    "PREFIX", "ReadinessConfig", "DemoConfig", "default_config", "Response", "dispatch_http",
    "AssuranceApplication", "DERIVED_PRACTICE_SAVES_SCRIPT", "prefix_html", "owns_scope",
]
