"""Standalone isolated UI fixture for browser interaction tests, never a real batch."""
import argparse
import tempfile
from pathlib import Path
import uvicorn
from test_workbench import fixture
from workbench import make_app

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--port',type=int,default=8766);args=parser.parse_args()
    root=Path(args.output).resolve();root.mkdir(parents=True,exist_ok=True)
    store,key=fixture(root)
    (root/'job-id.txt').write_text(key)
    print(key,flush=True)
    uvicorn.run(make_app(store),host='127.0.0.1',port=args.port,access_log=False)
