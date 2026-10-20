"""Add public retained-RR research routes without editing the frozen console."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from model_release_assurance.console import api as assurance_api

from .web import mount_research_routes


def create_app(root: Path, rr_data: Path | None = None) -> FastAPI:
    root = Path(root).absolute()
    app = assurance_api.create_app(root)
    research_root = Path(rr_data) if rr_data is not None else root.with_name(root.name + "-rr-research")
    mount_research_routes(app, research_root)
    # Replace only the presentation routes. Original source/evidence bytes stay intact.
    static = Path(assurance_api.__file__).parent / "static"
    app.router.routes[:] = [route for route in app.router.routes
                            if getattr(route, "path", None) not in {"/", "/guide"}]

    @app.get("/", response_class=HTMLResponse)
    def index():
        text = (static / "index.html").read_text(encoding="utf-8")
        link = '<a class="nav-item" href="/research-rr"><span aria-hidden="true">⌁</span> Research pipeline</a>'
        if "</nav>" not in text:
            raise RuntimeError("Console navigation anchor is missing")
        return HTMLResponse(text.replace("</nav>", link + "</nav>", 1))

    @app.get("/guide", response_class=HTMLResponse)
    def guide():
        text = (static / "guide.html").read_text(encoding="utf-8")
        link = '<p><a href="/research-rr#running-guide">Open the retained RR research pipeline and running guide</a></p>'
        anchor = "</main>" if "</main>" in text else "</body>"
        return HTMLResponse(text.replace(anchor, link + anchor, 1))

    research_static = Path(__file__).parent / "static"

    @app.get("/research-rr")
    def research_page():
        return FileResponse(research_static / "research.html")

    @app.get("/research-rr/static/{name}")
    def research_asset(name: str):
        if name not in {"research.js", "research.css"}:
            raise HTTPException(404)
        return FileResponse(research_static / name)

    return app
