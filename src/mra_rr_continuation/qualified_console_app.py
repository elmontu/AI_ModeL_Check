"""Add Phase 5 public qualification without changing earlier console assets."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from .benchmark_console_app import create_app as create_benchmark_app
from .qualified_routes import mount_qualified_routes
from . import web


def create_app(root: Path, rr_data: Path | None = None) -> FastAPI:
    root = Path(root).absolute()
    app = create_benchmark_app(root, rr_data)
    app.state.research_qualified_benchmark_store = mount_qualified_routes(
        app, root.with_name(root.name + "-rr-qualified-benchmark"))
    paths = {"/", "/guide", "/research-rr", "/research-benchmark"}
    originals = {route.path: route.endpoint for route in app.router.routes
                 if getattr(route, "path", None) in paths}
    app.router.routes[:] = [route for route in app.router.routes
                            if getattr(route, "path", None) not in paths]
    static = Path(__file__).parent / "static"
    link = '<a class="nav-item" href="/research-qualified-benchmark"><span aria-hidden="true">✓</span> Public qualification</a>'

    def navigation(path):
        text = originals[path]().body.decode("utf-8")
        if "</nav>" not in text:
            raise RuntimeError("Preserved console navigation anchor is absent")
        return HTMLResponse(text.replace("</nav>", link + "</nav>", 1))

    @app.get("/", response_class=HTMLResponse)
    def index():
        return navigation("/")

    @app.get("/guide", response_class=HTMLResponse)
    def guide():
        text = originals["/guide"]().body.decode("utf-8")
        anchor = "</main>" if "</main>" in text else "</body>"
        addition = '<p><a href="/research-qualified-benchmark">Open the Phase 5 public encoding and preregistration workflow</a></p>'
        return HTMLResponse(text.replace(anchor, addition + anchor, 1))

    @app.get("/research-rr", response_class=HTMLResponse)
    def research_page():
        return navigation("/research-rr")

    @app.get("/research-benchmark", response_class=HTMLResponse)
    def benchmark_page():
        return navigation("/research-benchmark")

    @app.get("/research-qualified-benchmark", response_class=HTMLResponse)
    def qualified_page():
        return HTMLResponse(web._read_file(static / "qualified-benchmark.html").decode("utf-8"))

    @app.get("/research-qualified-benchmark/static/{name}")
    def qualified_asset(name: str):
        if name not in {"qualified-benchmark.js", "qualified-benchmark.css"}:
            raise HTTPException(404)
        media = "text/javascript" if name.endswith(".js") else "text/css"
        return Response(web._read_file(static / name), media_type=media)

    return app
