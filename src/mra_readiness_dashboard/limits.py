"""Fixed local connection bounds; no capacity or operational assurance claim."""
from __future__ import annotations

import math
from numbers import Real
import sys
import threading


class BoundedConnectionsMixin:
    """Bound handler threads and socket inactivity before HTTP parsing.

    These fixed defaults are local resource safeguards. The timeout applies to
    inactive socket operations; it is not an absolute request deadline and does
    not defeat a client that keeps sending data before each timeout expires.
    """

    max_active_connections = 8
    connection_idle_timeout_seconds = 5.0

    def __init__(self, *args, **kwargs):
        capacity = self.max_active_connections
        timeout = self.connection_idle_timeout_seconds
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("Connection capacity must be a positive integer")
        if isinstance(timeout, bool) or not isinstance(timeout, Real):
            raise ValueError("Connection inactivity timeout must be finite and positive")
        try:
            timeout = float(timeout)
        except (OverflowError, ValueError):
            raise ValueError("Connection inactivity timeout must be finite and positive") from None
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Connection inactivity timeout must be finite and positive")
        self._connection_slots = threading.BoundedSemaphore(capacity)
        self._connection_idle_timeout_seconds = timeout
        super().__init__(*args, **kwargs)

    def get_request(self):
        request, client_address = super().get_request()
        try:
            request.settimeout(self._connection_idle_timeout_seconds)
        except BaseException as setup_error:
            try:
                self.close_request(request)
            except BaseException as close_error:
                raise setup_error from close_error
            raise
        return request, client_address

    def process_request(self, request, client_address):
        if not self._connection_slots.acquire(blocking=False):
            # Reject without a handler thread, HTTP parsing, reflection or status.
            self.close_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception as dispatch_error:
            # Ordinary start failures have no worker owning this slot. A fatal
            # interrupt may arrive after the worker starts; let it propagate to
            # service shutdown without releasing that worker's slot prematurely.
            try:
                self.close_request(request)
            except BaseException as close_error:
                raise dispatch_error from close_error
            finally:
                self._connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError,
                                         ConnectionAbortedError, TimeoutError)):
            # Expected client disconnects carry no request or filesystem details.
            return
        # Programming errors remain visible through the standard error handler.
        super().handle_error(request, client_address)
