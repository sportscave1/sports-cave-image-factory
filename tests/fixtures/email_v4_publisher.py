"""Local publisher thread sharing the SQL adapter's transaction lock."""
import os
from copy import deepcopy
from threading import Event,Thread
from tests.crm_db_fixture import connect
from tests.test_crm_send_flow import CFG,LIVE
from crm_automation_store import AutomationStore
from crm_automation_publication import run

def start():
    if os.getenv('CRM_TEST_POSTGRES')!='1':raise RuntimeError('Explicit local fixture required')
    os.environ.update(LIVE)
    store=AutomationStore(connect);store.render_settings=lambda env=None:deepcopy(CFG)
    stop=Event();thread=Thread(target=run,args=(store,'local-browser-publication',stop),daemon=True)
    import logging
    logging.getLogger('crm_automation_publication').setLevel(logging.INFO)
    thread.start();return stop,thread
