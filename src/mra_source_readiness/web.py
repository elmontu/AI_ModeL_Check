"""Read-only Phase 7A routes, optionally wrapped around the preserved console."""
from pathlib import Path
from html import escape
from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse,Response
from .validation import open_completed,ReadinessError

STORE='.local/demo-data-rr-readiness-20261013'
def mount_routes(app,repository):
 repository=Path(repository)
 def load():
  try:return open_completed(repository,repository/STORE)
  except (ReadinessError,OSError,KeyError) as e:raise HTTPException(409,'Source readiness evidence is unavailable or changed') from e
 @app.get('/api/research-source-readiness/manifest')
 def manifest():
  raw,_,_=load();return Response(raw,media_type='application/json')
 @app.get('/api/research-source-readiness/status')
 def status():
  _,_,receipt=load();return receipt
 @app.get('/research-source-readiness',response_class=HTMLResponse)
 def page():
  _,m,_=load();parts=[]
  for domain,t in sorted(m['tasks'].items()):
   parts.append('<h2>'+domain.upper()+'</h2><p>'+escape(t['readiness'])+'</p><p>'+escape(t['decision'])+'</p><p>Real-time validity: '+escape(t['real_time_validity'])+'. '+escape(t['evaluation_frame'])+'</p>')
  return HTMLResponse('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Public source readiness</title><body style="font:16px system-ui;max-width:850px;margin:48px auto;padding:0 24px"><h1>Phase 7A Public source readiness</h1><p>Source availability audit completed. No new benchmark was designed or executed. Agency acceptance and practical benefit thresholds remain pending.</p>'+''.join(parts)+'<p><a href="/api/research-source-readiness/manifest">Download source readiness manifest</a></p><p><a href="http://127.0.0.1:8765/research-qualified-evaluation#run=42f8bd981ec870538d861ef0871404a7">Open preserved Phase 6 evaluation</a></p></body></html>')
 return app

def create_app(repository):return mount_routes(FastAPI(title='Public source readiness'),repository)

def create_console_app(console_root,repository):
 from mra_rr_continuation.qualified_evaluation_console_app import create_app as preserved_console
 return mount_routes(preserved_console(Path(console_root)),repository)
