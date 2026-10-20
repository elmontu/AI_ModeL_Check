"""Add readiness and learning to the main local MRA application."""
from pathlib import Path
import html
from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from mra_readiness_dashboard.console_integration import AssuranceApplication, DemoConfig

MAIN_PAGES = ('/', '/guide', '/research-rr', '/research-benchmark',
              '/research-qualified-benchmark', '/research-qualified-evaluation')
NAV_CSS_PATH = '/main-assurance-navigation.css'
MAIN_LINKS = (
    ('/', 'Readiness overview'),
    ('/remediation', 'Gap checklists'),
    ('/evidence', 'Evidence register'),
    ('/tutorial', 'Tutorial examples'),
    ('/tutorial-lab', 'Interactive tutorial'),
    ('/tutorial-compare', 'Compare demos'),
    ('/tutorial-walkthrough', 'Guided tutorial'),
    ('/tutorial-practice', 'Guided practice'),
    ('/practice-saves', 'Saved demos'),
)
NAVIGATION_CSS = """.sidebar{overflow-y:auto;scrollbar-width:thin}.assurance-nav-group{border-top:1px solid #36504a;margin-top:17px;padding-top:10px}.assurance-nav-title{font-size:9px;letter-spacing:1.3px;color:#b9cfae;margin:8px 11px}.assurance-nav-group .nav-item{padding-top:8px;padding-bottom:8px}.assurance-entry{margin:22px 0 32px;padding:22px;border:1px solid #cbded5;border-radius:9px;background:#fff}.assurance-entry h2{font-size:20px;margin:0 0 8px}.assurance-entry p{font-size:12px;line-height:1.7;color:#526c62;max-width:900px}.assurance-entry-links{display:flex;flex-wrap:wrap;gap:9px;margin-top:16px}.assurance-entry-links a{display:block;padding:9px 12px;border:1px solid #a9c3b6;border-radius:5px;font-size:12px;text-decoration:none;color:#175d4f;background:#f5faf6}.assurance-entry-links a:hover{background:#e4f1e8}.running-guide .assurance-nav-title{color:#265c4d}.running-guide .assurance-nav-group{border-color:#dce4e1}.running-guide .assurance-nav-group .nav-item{color:#175d4f}@media(max-width:700px){.assurance-entry{padding:17px}.assurance-entry-links{display:grid;grid-template-columns:1fr 1fr}.assurance-entry-links a{overflow-wrap:anywhere}}@media(max-width:380px){.assurance-entry-links{grid-template-columns:1fr}}"""


def navigation_html():
    selected = ('Readiness overview', 'Gap checklists', 'Tutorial examples',
                'Compare demos', 'Guided practice', 'Saved demos')
    links = ''.join('<a class="nav-item" href="/assurance' + path + '">' + html.escape(label) + '</a>'
                    for path, label in MAIN_LINKS if label in selected)
    return ('<div class="assurance-nav-group" role="group" aria-label="Readiness and learning">'
            '<p class="assurance-nav-title">READINESS &amp; LEARNING</p>' + links + '</div>')


def entry_html():
    links = ''.join('<a href="/assurance' + path + '">' + html.escape(label) + '</a>'
                    for path, label in MAIN_LINKS)
    return ('<section id="readiness-learning" class="assurance-entry" aria-labelledby="readiness-learning-title">'
            '<h2 id="readiness-learning-title">Readiness &amp; learning</h2>'
            '<p>Review captured evidence and open requirements, explore fictional decisions and source assumptions, '
            'then practise, save and compare your configurations here in MRA. Real agency decisions remain pending. '
            'Demo choices supply no authentic evidence or release authority.</p>'
            '<nav class="assurance-entry-links" aria-label="Readiness and learning tools">' + links + '</nav></section>')


def decorate_main_navigation(app):
    """Extend fixed presentation endpoints; leave API and execution routes intact."""
    originals = [route for route in app.router.routes
                 if getattr(route, 'path', None) in MAIN_PAGES and 'GET' in getattr(route, 'methods', ())]
    if len({route.path for route in originals}) != len(originals):
        raise ValueError('Duplicate main presentation route')

    def endpoint(original, path):
        def render():
            response = original()
            if not isinstance(response, HTMLResponse):
                raise ValueError('Expected fixed main HTML response')
            text = response.body.decode('utf-8')
            if '</nav>' not in text or '</head>' not in text:
                raise ValueError('Main navigation anchor is unavailable')
            text = text.replace('</nav>', navigation_html() + '</nav>', 1)
            text = text.replace('</head>', '<link rel="stylesheet" href="' + NAV_CSS_PATH + '"></head>', 1)
            if path == '/':
                marker = '<section id="datasets"'
                if text.count(marker) != 1:
                    raise ValueError('Main dataset entry anchor is unavailable')
                text = text.replace(marker, entry_html() + marker, 1)
            headers = {key: value for key, value in response.headers.items()
                       if key.lower() not in ('content-length', 'content-type')}
            return HTMLResponse(text, status_code=response.status_code, headers=headers)
        return render

    app.router.routes[:] = [route for route in app.router.routes if route not in originals]
    for route in originals:
        app.add_api_route(route.path, endpoint(route.endpoint, route.path),
                          methods=list(route.methods), response_class=HTMLResponse,
                          name=route.name, include_in_schema=route.include_in_schema)

    @app.api_route(NAV_CSS_PATH, methods=['GET', 'HEAD'], include_in_schema=False)
    def navigation_styles(request: Request):
        raw = NAVIGATION_CSS.encode('utf-8')
        return Response(b'' if request.method == 'HEAD' else raw, media_type='text/css',
                        headers={'Content-Length': str(len(raw))})
    return app


def create_app(root: Path, rr_data: Path | None = None, *, readiness_config=None):
    """Compose the existing application and guarded same-origin readiness pages."""
    from .qualified_evaluation_console_app import create_app as create_existing_app
    app = decorate_main_navigation(create_existing_app(root, rr_data))
    configuration = readiness_config if readiness_config is not None else DemoConfig()
    return AssuranceApplication(app, configuration)
