"""Fixed, bounded HTTP input policy for the local read-only presentation service.

The standard-library parser still interprets requests and header fields.  This
adapter limits bytes read before that parser handles them; physical header
lines, including continuations, are counted without claiming stricter RFC
header semantics.  It does not parse or read request bodies.
"""
from __future__ import annotations

import re

MAX_REQUEST_LINE_BYTES = 4096
MAX_HEADER_LINE_BYTES = 4096
MAX_HEADER_BYTES = 16384
MAX_HEADER_LINES = 32

# Public constants let focused protocol tests assert that parser errors never
# repeat request targets, method tokens, header values or exception details.
ERROR_BODIES = {
    400: b"Malformed HTTP request.\n",
    414: b"HTTP request line exceeds the local limit.\n",
    417: b"Request expectations are not accepted.\n",
    431: b"HTTP headers exceed the local limits.\n",
    500: b"Local request processing failed.\n",
    501: b"HTTP method is not supported.\n",
    505: b"HTTP version is not supported.\n",
}
_VERSION = re.compile(r"HTTP/([0-9]{1,10})\.([0-9]{1,10})\Z")

def _request_words(raw):
    # Match stdlib's decoded tokenization for HEAD even before parsing succeeds.
    return raw.decode("iso-8859-1").rstrip("\r\n").split()


class RequestBoundaryError(Exception):
    """A fixed local request-input error, with no request-supplied message."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class BoundedRequestReader:
    """A readline adapter used only while stdlib reads request headers.

    The request line and each header line include their raw line terminators.
    The aggregate header budget includes the terminating blank line.  Reads
    request at most the remaining budget plus one byte, so an excessive line
    never reaches the standard library's much larger default line budget.
    """

    def __init__(self, stream):
        self.stream = stream
        self.requestline_prefix = b""
        self.header_bytes = 0
        self.header_lines = 0
        self._headers = False
        self._header_line = b""
        self._header_end = False

    def start_headers(self):
        self._headers = True

    def readline(self, size=-1):
        if not self._headers:
            limit = MAX_REQUEST_LINE_BYTES - len(self.requestline_prefix) + 1
        else:
            limit = min(MAX_HEADER_LINE_BYTES - len(self._header_line) + 1,
                        MAX_HEADER_BYTES - self.header_bytes + 1)
        if size >= 0:
            limit = min(limit, size)
        if limit == 0:
            return b""
        raw = self.stream.readline(limit)
        if not self._headers:
            self.requestline_prefix += raw
            if len(self.requestline_prefix) > MAX_REQUEST_LINE_BYTES:
                raise RequestBoundaryError(414)
            return raw
        if not raw:
            # A disconnected client has not terminated the header section.
            raise RequestBoundaryError(400)
        self.header_bytes += len(raw)
        self._header_line += raw
        if (self.header_bytes > MAX_HEADER_BYTES or
                len(self._header_line) > MAX_HEADER_LINE_BYTES):
            raise RequestBoundaryError(431)
        if raw.endswith(b"\n"):
            if self._header_line in (b"\r\n", b"\n"):
                self._header_end = True
            else:
                self.header_lines += 1
                if self.header_lines > MAX_HEADER_LINES:
                    raise RequestBoundaryError(431)
            self._header_line = b""
        return raw

    def __getattr__(self, name):
        return getattr(self.stream, name)


class BoundedRequestMixin:
    """Keep stdlib parsing while bounding its reads and fixing error output."""

    def handle_one_request(self):
        # The stdlib initializes these only after reading the request line.
        # Set them first so a read-limit error has safe framing and HEAD state.
        self.raw_requestline = b""
        self.requestline = ""
        self.request_version = "HTTP/1.1"
        self.command = ""
        self.close_connection = True
        original = self.rfile
        reader = BoundedRequestReader(original)
        self.rfile = reader
        try:
            super().handle_one_request()
        except RequestBoundaryError as error:
            self.raw_requestline = reader.requestline_prefix
            self.send_error(error.code)
        finally:
            self.rfile = original

    def parse_request(self):
        # Exclude the old two-token HTTP/0.9 path before stdlib's permissive
        # parser can omit normal HTTP framing.  Only the two supported literal
        # versions proceed to that parser; no header interpretation is copied.
        words = _request_words(self.raw_requestline)
        if len(words) != 3:
            self.send_error(400)
            return False
        version = words[2]
        if version not in ("HTTP/1.0", "HTTP/1.1"):
            match = _VERSION.fullmatch(version)
            if match is None or tuple(map(int, match.groups())) == (0, 9):
                self.send_error(400)
            else:
                self.send_error(505)
            return False
        self.rfile.start_headers()
        return super().parse_request()

    def send_error(self, code, message=None, explain=None):
        # Discard stdlib diagnostics, including attacker-controlled syntax and
        # version text.  Derive HEAD even when parsing stopped before command
        # assignment, and force HTTP framing for every error response.
        prefix = _request_words(self.raw_requestline)
        self.command = "HEAD" if prefix and prefix[0] == "HEAD" else ""
        self.request_version = "HTTP/1.1"
        fixed_code = int(code) if int(code) in ERROR_BODIES else 500
        self._send(fixed_code, ERROR_BODIES[fixed_code])

    def handle_expect_100(self):
        # Defer every Expect decision to the guarded application request path.
        # No interim response may precede fresh input, host and origin checks.
        return True
