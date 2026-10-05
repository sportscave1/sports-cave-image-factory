"""Run explicitly after approval: python crm_worker.py [--once] [--seed]."""
import argparse
import logging
import signal
import threading
import uuid

def main(argv=None):
    logging.basicConfig(level=logging.WARNING,format='%(asctime)s %(levelname)s %(message)s')
    # Enable only the safe batch counters/timings, not third-party debug output.
    logging.getLogger('crm_campaign_dispatch').setLevel(logging.INFO)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true');parser.add_argument('--seed',action='store_true',help='Insert draft definitions only; requires applied migration.')
    args=parser.parse_args(argv)
    from crm_store import Store
    store=Store()
    if args.seed:store.seed();return 0
    from crm_shopify import Shopify
    from crm_engine import Engine
    engine=Engine(store,Shopify());stop=threading.Event();owner=str(uuid.uuid4())
    signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
    while not stop.is_set():
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
        if args.once:break
        stop.wait(30)
    return 0

if __name__=='__main__':raise SystemExit(main())
