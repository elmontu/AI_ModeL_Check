"""Add the public domain benchmark while preserving earlier console sources."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from .history_console_app import create_app as create_history_app
from .benchmark_routes import mount_benchmark_routes
from . import web


def create_app(root: Path, rr_data: Path | None = None) -> FastAPI:
    root = Path(root).absolute()
    app = create_history_app(root, rr_data)
    app.state.research_benchmark_store = mount_benchmark_routes(
        app, root.with_name(root.name + "-rr-benchmark"))
    originals = {route.path: route.endpoint for route in app.router.routes
                 if getattr(route, "path", None) in {"/", "/guide"}}
    app.router.routes[:] = [route for route in app.router.routes
                            if getattr(route, "path", None) not in {"/", "/guide", "/research-rr"}]
    static = Path(__file__).parent / "static"
    link = '<a class="nav-item" href="/research-benchmark"><span aria-hidden="true">≋</span> Public usefulness benchmark</a>'

    def navigation(text):
        if "</nav>" not in text:
            raise RuntimeError("Preserved console navigation anchor is absent")
        return text.replace("</nav>", link + "</nav>", 1)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(navigation(originals["/"]().body.decode("utf-8")))

    @app.get("/guide", response_class=HTMLResponse)
    def guide():
        text = originals["/guide"]().body.decode("utf-8")
        anchor = "</main>" if "</main>" in text else "</body>"
        addition = '<p><a href="/research-benchmark">Open the Phase 4 public usefulness benchmark</a></p>'
        return HTMLResponse(text.replace(anchor, addition + anchor, 1))

    @app.get("/research-rr", response_class=HTMLResponse)
    def research_page():
        return HTMLResponse(navigation(web._read_file(static / "research.html").decode("utf-8")))

    @app.get("/research-benchmark", response_class=HTMLResponse)
    def benchmark_page():
        return HTMLResponse(web._read_file(static / "benchmark.html").decode("utf-8"))

    @app.get("/research-benchmark/static/{name}")
    def benchmark_asset(name: str):
        if name not in {"benchmark.js", "benchmark.css"}:
            raise HTTPException(404)
        media = "text/javascript" if name.endswith(".js") else "text/css"
        return Response(web._read_file(static / name), media_type=media)

    return app

