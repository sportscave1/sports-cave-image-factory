"""Loopback-only Streamlit fixture, with synthetic API and no app startup hooks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
import sc_auth
sc_auth._signing_key=lambda **kwargs:b'local-synthetic-fixture-key'
import auto_editions_status as status
from tests import edition_status_fixture_state as state
from starlette.responses import JSONResponse
from starlette.routing import Route
from streamlit.web.server.starlette import App


async def statuses(request):
    body=await request.json()
    return JSONResponse(status.signed({'rows':state.rows(body['product_gids'])}, {'id':'synthetic-reader'}))


async def change(request):
    body=await request.json();state.stage=body['stage']
    if 'review_jobs' in body:state.review_jobs=body['review_jobs']
    return JSONResponse({'ok':True})


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',action='store_true')
    args=parser.parse_args()
    import uvicorn
    app=App(Path(__file__).with_name('edition_status_baseline_fixture.py' if args.baseline else 'edition_status_browser_fixture.py'),secrets={},routes=[
        Route('/api/auto-editions/status',statuses,methods=['POST']),Route('/fixture-stage',change,methods=['POST'])])
    uvicorn.run(app,host='127.0.0.1',port=8646 if args.baseline else 8645,log_level='warning')
