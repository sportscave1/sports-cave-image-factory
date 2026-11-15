"""Bounded retries exclusively for Meta Review GET reads; never wraps writes."""
import random
import time
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import requests
from urllib3.util import Timeout
import meta_ads_client as meta
LOGGER=logging.getLogger(__name__)

def transient(error):
    if not isinstance(error, meta.MetaAdsApiError):
        return False
    code=str(error.error_code)
    if code in ('10','100','102','190','200','294') or error.status_code in (401,403):
        return False
    if isinstance(error.__cause__, (requests.Timeout, requests.ConnectionError)):
        return True
    if error.is_transient is False:
        return False
    return (error.is_transient is True or code in ('2','4','17','32','613','80004')
            or error.status_code in (429,500,502,503,504))

def retry_after(value):
    try:
        return max(0.,float(value))
    except (ValueError,TypeError):
        try:
            return max(0.,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
        except (ValueError,TypeError,OverflowError):
            return 0.

def get(path, params, config, deadline, *, clock=time.monotonic, sleep=time.sleep, jitter=random.uniform):
    # The report deadline includes pages; this additional budget bounds each read.
    deadline=min(deadline,clock()+35)
    for attempt in range(3):
        remaining=deadline-clock()
        if remaining<=0:
            raise TimeoutError('Meta read time limit reached. Try a narrower reporting period.')
        token=meta.READ_TIMEOUT.set(Timeout(total=min(30.,remaining),
                                          connect=min(5.,remaining),read=min(30.,remaining)))
        started=clock()
        try:
            result=meta._request(path,params=params,config=config)
            if clock()>deadline:
                raise TimeoutError('Meta read time limit reached. Try a narrower reporting period.')
            LOGGER.info('Meta Review GET succeeded attempt=%d elapsed_ms=%.1f',attempt+1,(clock()-started)*1000)
            return result
        except meta.MetaAdsApiError as error:
            LOGGER.warning('Meta Review GET failed attempt=%d elapsed_ms=%.1f status=%s code=%s subcode=%s',
                           attempt+1,(clock()-started)*1000,error.status_code,error.error_code,error.error_subcode)
            if not transient(error) or attempt==2:
                raise
            delay=max(retry_after(error.retry_after), min(8.,2**attempt)+jitter(0,.5))
            if delay+0.1>=deadline-clock():
                raise
            sleep(delay)
        finally:
            meta.READ_TIMEOUT.reset(token)
