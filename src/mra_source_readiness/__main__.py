from __future__ import annotations
import argparse,json
from pathlib import Path
from .validation import open_completed

def main():
 p=argparse.ArgumentParser(description='Offline public source-readiness audit; no evaluation or simulation command')
 p.add_argument('command',choices=['validate','show','serve']);p.add_argument('--repository',type=Path,required=True);p.add_argument('--port',type=int,default=8768)
 a=p.parse_args();root=a.repository.resolve(strict=True)
 raw,m,receipt=open_completed(root,root/'.local/demo-data-rr-readiness-20261013')
 if a.command=='show':print(raw.decode('utf-8'))
 elif a.command=='validate':print(json.dumps(receipt,sort_keys=True,indent=2))
 else:
  import uvicorn
  from .web import create_app
  uvicorn.run(create_app(root),host='127.0.0.1',port=a.port,access_log=False)
if __name__=='__main__':main()
