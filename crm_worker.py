"""Run explicitly after approval: python crm_worker.py [--once] [--seed]."""
import argparse
import logging
import signal
import threading
import uuid

def _prepare_campaign(store,shop,*,env=None):
    # General worker storage does not expose draft/render/history operations.
    # Reuse its connection factory through the existing campaign repository.
    from crm_campaign_store import CampaignStore
    from crm_campaign_preparation import tick
    return tick(CampaignStore(store.connect),shop,env=env)

def main(argv=None):
    logging.basicConfig(level=logging.WARNING,format='%(asctime)s %(levelname)s %(message)s')
    # Enable only the safe batch counters/timings, not third-party debug output.
    logging.getLogger('crm_campaign_dispatch').setLevel(logging.INFO)
    for name in ('crm_automation_runtime','crm_shopify_automation_events','crm_engine','crm_checkout_analytics','wall_preview_archive','wall_preview_crm_store'):
        logging.getLogger(name).setLevel(logging.INFO)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true');parser.add_argument('--seed',action='store_true',help='Insert draft definitions only; requires applied migration.')
    args=parser.parse_args(argv)
    from wall_preview_archive import configuration_diagnostic
    configuration_diagnostic()
    from crm_store import Store
    store=Store()
    if args.seed:store.seed();return 0
    from crm_shopify import Shopify
    from crm_engine import Engine
    engine=Engine(store,Shopify());stop=threading.Event();owner=str(uuid.uuid4())
    signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
    # Durable manual enrollment validation shares this worker process, but a
    # slow Shopify lookup must not block either its peers or the email cycle.
    from crm_checkout_enrollment_requests import Processor
    logging.getLogger('crm_checkout_enrollment_requests').setLevel(logging.INFO)
    enrollment=Processor(store,Shopify())
    enrollment_thread=threading.Thread(target=enrollment.run,args=(stop,),name='checkout-enrollment-poll',daemon=True)
    enrollment_thread.start()
    # The existing publication queue must not wait behind external maintenance.
    # --once retains the synchronous Engine tick for administrative/test callers.
    publication_thread=None
    # External verification is isolated from delivery ticks. The thread owns no
    # durable state: DB leases and fenced publication recover across processes.
    def preparation_run():
        preparation_shop=Shopify()
        while not stop.is_set():
            try:worked=_prepare_campaign(store,preparation_shop)
            except Exception as exc:
                worked=False
                logging.getLogger(__name__).warning('campaign_preparation_cycle_failed error_class=%s',type(exc).__name__)
            stop.wait(0.2 if worked else 2)
    preparation_thread=None
    if args.once:_prepare_campaign(store,Shopify())
    else:
        preparation_thread=threading.Thread(target=preparation_run,name='campaign-preparation-poll',daemon=True)
        preparation_thread.start()
    if not args.once:
        from crm_automation_publication import run as publication_run
        from crm_automation_store import AutomationStore
        logging.getLogger('crm_automation_publication').setLevel(logging.INFO)
        publication_thread=threading.Thread(target=publication_run,
            args=(AutomationStore(store.connect),owner+'-publication',stop),
            name='automation-publication-poll',daemon=True)
        engine.publication_background=True
        publication_thread.start()
    while not stop.is_set():
        try:
            from wall_preview_archive import tick as archive_tick
            archive_tick()
        except Exception as exc:logging.getLogger(__name__).warning('wall_preview_archive_cycle_failed type=%s',type(exc).__name__)
        try:
            from wall_preview_email import tick as wall_preview_tick
            wall_preview_tick()
        except Exception as exc:logging.getLogger(__name__).warning('wall_preview_worker_cycle_failed type=%s',type(exc).__name__)
        try:
            from wall_preview_customer import tick as wall_preview_customer_tick
            wall_preview_customer_tick()
        except Exception as exc:logging.getLogger(__name__).warning('wall_preview_customer_cycle_failed type=%s',type(exc).__name__)
        # Durable review imports are independent of marketing delivery gates.
        try:
            from reviews_worker import tick as review_import_tick
            review_import_tick()
        except Exception as exc:logging.getLogger(__name__).warning('review_worker_cycle_failed type=%s',type(exc).__name__)
        try:engine.tick(owner)
        except Exception as exc:logging.getLogger(__name__).warning('crm_worker_cycle_failed type=%s',type(exc).__name__)
        try:
            from crm_flow_tests import tick as flow_test_tick
            flow_test_tick(store)
        except Exception as exc:logging.getLogger(__name__).warning('crm_flow_test_cycle_failed type=%s',type(exc).__name__)
        if args.once:break
        stop.wait(30)
    stop.set();enrollment_thread.join(timeout=6)
    if publication_thread:publication_thread.join(timeout=6)
    if preparation_thread:preparation_thread.join(timeout=6)
    return 0

if __name__=='__main__':raise SystemExit(main())
