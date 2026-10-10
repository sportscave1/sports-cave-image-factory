"""Read-only local SQL and shell-stage attribution inside the script thread."""
import os,sys,json,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
root=Path(a.source).resolve();output=Path(a.output).resolve()
source=(Path(__file__).parent/'fixtures/campaign_final_preview.py').read_text()
os.environ['CAMPAIGN_SOURCE_ROOT']=str(root);sys.path.insert(0,str(root));os.chdir(root)
source=source.replace("exec(compile(fixture.read_text(encoding='utf-8').split('st.title(get_current_page())')[0],str(fixture),'exec'))", """shell_started=time.perf_counter()
exec(compile(fixture.read_text(encoding='utf-8').split('st.title(get_current_page())')[0],str(fixture),'exec'))
st.session_state['profile_shell_ms']=(time.perf_counter()-shell_started)*1000""")
source=source.replace('            return super().q(*args,**kwargs)',"""            started=time.perf_counter()
            result=super().q(*args,**kwargs)
            st.session_state.setdefault('profile_queries',[]).append({'sql':args[0].strip()[:110],'ms':(time.perf_counter()-started)*1000,'response_bytes':len(str(result).encode())})
            return result""")
from streamlit.testing.v1 import AppTest
app=AppTest.from_string(source,default_timeout=30);app.query_params['view']='workspace';app.run()
assert not app.exception,list(app.exception)
output.write_text(json.dumps({'shell_fixture_ms':app.session_state['profile_shell_ms'],'queries':app.session_state['profile_queries']},indent=2))
