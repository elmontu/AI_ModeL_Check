"""Wrap the immutable Phase 5 application with the public Phase 6 evaluator."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from .qualified_console_app import create_app as create_qualified_app
from .qualified_evaluation_routes import mount_qualified_evaluation_routes
from . import web


def create_app(root: Path, rr_data: Path | None = None) -> FastAPI:
    root = Path(root).absolute()
    app = create_qualified_app(root, rr_data)
    app.state.research_qualified_evaluation_store = mount_qualified_evaluation_routes(
        app, root.with_name(root.name + "-rr-qualified-evaluation"),
        preregistration_root=app.state.research_qualified_benchmark_store.root)
    paths = {"/", "/guide", "/research-rr", "/research-benchmark", "/research-qualified-benchmark"}
    originals = {route.path: route.endpoint for route in app.router.routes
                 if getattr(route, "path", None) in paths}
    app.router.routes[:] = [route for route in app.router.routes
                            if getattr(route, "path", None) not in paths]
    static = Path(__file__).parent / "static"
    link = '<a class="nav-item" href="/research-qualified-evaluation"><span aria-hidden="true">▥</span> Public evaluation</a>'

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
        addition = '<p><a href="/research-qualified-evaluation">Open the frozen Phase 6 MOH, MAS and MSF usefulness evaluation</a></p>'
        return HTMLResponse(text.replace(anchor, addition + anchor, 1))

    @app.get("/research-rr", response_class=HTMLResponse)
    def research():
        return navigation("/research-rr")

    @app.get("/research-benchmark", response_class=HTMLResponse)
    def benchmark():
        return navigation("/research-benchmark")

    @app.get("/research-qualified-benchmark", response_class=HTMLResponse)
    def qualified():
        return navigation("/research-qualified-benchmark")

    @app.get("/research-qualified-evaluation", response_class=HTMLResponse)
    def evaluation():
        return HTMLResponse(web._read_file(static / "qualified-evaluation.html").decode("utf-8"))

    @app.get("/research-qualified-evaluation/static/{name}")
    def asset(name: str):
        if name not in {"qualified-evaluation.js", "qualified-evaluation.css"}:
            raise HTTPException(404)
        media = "text/javascript" if name.endswith(".js") else "text/css"
        return Response(web._read_file(static / name), media_type=media)

    return app

