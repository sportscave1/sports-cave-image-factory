"""Full actual dispatcher survey; all external connections fail closed."""
from pathlib import Path
import sys, socket, runpy, os
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
# Constrain every Python socket, including clients other than requests.
_original_connect=socket.socket.connect
_original_connect_ex=socket.socket.connect_ex
def loopback(address):
 return isinstance(address,tuple) and address[0] in ('127.0.0.1','::1','localhost')
def connect(sock,address):
 if not loopback(address):raise RuntimeError('External sockets forbidden in application-wide local survey')
 return _original_connect(sock,address)
def connect_ex(sock,address):
 if not loopback(address):raise RuntimeError('External sockets forbidden in application-wide local survey')
 return _original_connect_ex(sock,address)
# Do not wrap twice on Streamlit reruns.
if not getattr(socket,'_appwide_survey_guard',False):
 socket.socket.connect=connect
 socket.socket.connect_ex=connect_ex
 socket._appwide_survey_guard=True
os.environ['SC_V5_SOURCE_DELAY']='0'
os.environ['SC_V5_CRM_SQL']='0'
os.environ['SC_V5_VARIANT']='after'
import ast, streamlit as st
import importlib, page_presentation
importlib.reload(page_presentation)
from functools import lru_cache
from tests.fixtures import navigation_v5_sources as sources
@lru_cache(maxsize=2)
def definitions(path,modified):
 tree=ast.parse(Path(path).read_text(encoding='utf-8-sig'))
 nodes=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.ClassDef,ast.Assign,ast.AnnAssign))]
 return compile(ast.Module(body=nodes,type_ignores=[]),str(ROOT/'app.py'),'exec')
source=ROOT/'tmp/appwide-ui-v1-app.before.py' if st.query_params.get('phase')=='before' else ROOT/'app.py'
sources.app_definitions=lambda before=False:definitions(str(source),source.stat().st_mtime_ns)
runpy.run_path(str(ROOT/'tests/fixtures/navigation_v5_preview.py'),run_name='appwide_survey')
