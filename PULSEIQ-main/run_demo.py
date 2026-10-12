"""Loopback-only fictional demo. Never use this SQLite/test configuration on Render."""
import os
from pathlib import Path
import uvicorn
from backend.settings import Settings
from backend.api_v3 import create_app
os.environ['BOOTSTRAP_COLLEGE_NAME']='PULSEIQ Demo College'
os.environ['BOOTSTRAP_COLLEGE_DOMAIN']='demo.edu.in'
os.environ['BOOTSTRAP_ADMIN_EMAIL']='admin@demo.edu.in'
app=create_app(Settings('sqlite:///'+str(Path('local_demo.sqlite').resolve()),'local-demo-only-not-a-production-secret-12345','DemoCampus2026!',True,200,False,'test'))
if __name__=='__main__':
    print('Open http://127.0.0.1:8000 | admin@demo.edu.in | DemoCampus2026!')
    uvicorn.run(app,host='127.0.0.1',port=8000)
