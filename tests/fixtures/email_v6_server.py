"""Local-only V6 UI, synthetic SQL and blocked outbound services."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import uvicorn
from streamlit.web.server.starlette import App
fixture='crm_email_performance.py' if os.environ['EMAIL_V6_MODE']=='campaign' else 'crm_automation_preview.py'
uvicorn.run(App(str(Path(__file__).with_name(fixture))),host='127.0.0.1',port=int(os.environ['EMAIL_V6_UI_PORT']))
