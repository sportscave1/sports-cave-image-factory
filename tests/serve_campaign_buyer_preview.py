"""Launch only the synthetic local UI with no production credentials."""
import os, subprocess, sys
from pathlib import Path
keep={'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','LOCALAPPDATA','APPDATA','PROGRAMFILES','PROGRAMFILES(X86)'}
env={k:v for k,v in os.environ.items() if k.upper() in keep}
env['STREAMLIT_BROWSER_GATHER_USAGE_STATS']='false'
env['USERPROFILE']=str(Path('.tmp-product-sport-tags-v2/profile').resolve())
env['HOME']=env['USERPROFILE']
raise SystemExit(subprocess.call([sys.executable,'-m','streamlit','run',
    'tests/fixtures/campaign_buyer_segments_preview.py','--server.address=127.0.0.1',
    '--server.port=8598','--server.headless=true','--browser.gatherUsageStats=false'],env=env))
