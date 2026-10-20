"""Wrap the unchanged research console with Phase 3 shared-history routes."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from .console_app import create_app as create_historical_app
from .history_routes import mount_history_routes
from .web import PREFIX


def create_app(root: Path, rr_data: Path | None = None) -> FastAPI:
    root = Path(root).absolute()
    app = create_historical_app(root, rr_data)
    research_root = Path(rr_data) if rr_data is not None else root.with_name(root.name + "-rr-research")
    app.router.routes[:] = [route for route in app.router.routes
                            if not str(getattr(route, "path", "")).startswith(PREFIX)]
    app.state.research_history_store = mount_history_routes(app, research_root)
    return app
