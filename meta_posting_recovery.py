"""Durable write intents inside the existing submission's ad_results JSON.

No request payloads or uploads are stored. An interrupted pending write is never
replayed. Known completed IDs can be reused even if the following checkpoint
failed. Explicit Meta rejections can be retried; unknown outcomes need review.
"""
from copy import deepcopy
import hashlib
import json
import logging
from pathlib import Path
import re
import traceback

from meta_ads_client import MetaAdsApiError, MetaAdsAmbiguousResultError

LOG = logging.getLogger('meta_posting_service')
KEY = 'posting_operations_v1'
WRITES = frozenset('create_campaign create_adset upload_image upload_page_photo create_canvas_element create_canvas create_collection_creative create_carousel_creative create_creative create_paused_ad copy_paused_ad_from_template rename_paused_ad'.split())


def requires_reconciliation(row):
    rows = row.get('ad_results') or []
    journal = rows[0].get(KEY) or {} if rows else {}
    return (str(row.get('safe_error') or '').startswith(('The Meta request failed.', 'The Meta Carousel request failed.'))
            or any(r.get('state') == 'pending' for r in journal.values()))


def verify_resume_objects(client, record):
    from meta_posting_service import PostingValidationError, normalize_account_id, validate_existing_posting_target, CAROUSEL_AD_TYPE
    rows = record.get('ad_results') or []
    journal = rows[0].get(KEY) or {} if rows else {}
    def identity(field, operation):
        return str(record.get(field) or next((r.get('result') for r in journal.values()
                    if r.get('operation') == operation and r.get('state') == 'complete'), '') or '')
    campaign_id = identity('campaign_id', 'create_campaign')
    adset_id = identity('adset_id', 'create_adset')
    campaign = client.configured_campaign(campaign_id) if campaign_id else {}
    adset = client.configured_adset(adset_id) if adset_id else {}
    for field, row, expected in [('campaign',campaign,campaign_id),('adset',adset,adset_id)]:
        if not expected:
            continue
        if str(row.get('id') or '') != expected or normalize_account_id(row.get('account_id')) != normalize_account_id(client.ad_account_id):
            raise PostingValidationError('Saved Meta object ownership could not be verified. No replacement was created.')
        if record.get(field + '_ownership', 'CREATED_BY_RUN') == 'CREATED_BY_RUN' and str(row.get('configured_status') or row.get('status')).upper() != 'PAUSED':
            raise PostingValidationError('A saved run-owned Meta object is not PAUSED. Review it before resuming.')
    if adset_id:
        validate_existing_posting_target(campaign=campaign, adset=adset,
            expected_campaign_id=campaign_id, expected_adset_id=adset_id,
            expected_account_id=client.ad_account_id, expected_catalog_id=record.get('catalog_id'),
            expected_product_set_id=record.get('product_set_id'), expected_pixel_id=record.get('pixel_id'),
            allow_product_set_mismatch=record.get('ad_type') == CAROUSEL_AD_TYPE)
    return {'campaign': campaign, 'adset': adset}


def diagnostic(error, stage, submission_id):
    """Trace locations only: exception strings/source lines can contain payloads."""
    frames = [{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
              for f in traceback.extract_tb(error.__traceback__)]
    token = lambda v: re.sub(r'[^A-Za-z0-9_.-]', '', str(v or ''))[:160]
    data = dict(submission_id=token(submission_id), operation=token(stage),
                exception_class=type(error).__name__, traceback=frames,
                sqlstate=token(getattr(error, 'sqlstate', '')))
    for field in ('error_code', 'error_subcode', 'fbtrace_id'):
        data[field] = token(getattr(error, field, ''))
    LOG.error('posting_failure %s', json.dumps(data, sort_keys=True))
    from ads_schema import AdsSchemaUnavailable
    if isinstance(error, AdsSchemaUnavailable):
        return str(error)
    if data['sqlstate'] in {'57014', '40P01', '55P03'}:
        reason = 'Database checkpoint timed out or encountered a lock conflict'
    elif type(error).__module__.startswith('psycopg') or stage.startswith('checkpoint_'):
        reason = 'Database checkpoint could not be confirmed'
    else:
        reason = 'Posting encountered an internal error (' + type(error).__name__ + ')'
    return f'{reason} during {stage.replace("_", " ")}. Saved objects are retained; verify their status before resuming.'


class RecoveryStore:
    def __init__(self, store):
        self.raw = store
        self.record = {}
        self.journal = {}
        self.operation = 'validation'
        self.route = 0
        self.resuming = False

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def claim(self, *args, **kwargs):
        result = self.raw.claim(*args, **kwargs)
        self.record = deepcopy(result.get('record') or {})
        rows = self.record.get('ad_results') or []
        self.journal = deepcopy(rows[0].get(KEY) or {}) if rows else {}
        self.resuming = bool(self.journal or self.record.get('campaign_id') or self.record.get('adset_id'))
        if result.get('claimed'):
            from meta_posting_service import PostingAmbiguousError
            # Old generic errors do not prove that the missing operation failed.
            legacy_unknown = str(self.record.get('safe_error') or '').startswith(('The Meta request failed.', 'The Meta Carousel request failed.'))
            if legacy_unknown or any(r.get('state') == 'pending' for r in self.journal.values()):
                message = 'An earlier Meta write has an unknown outcome. Reconcile the existing submission and saved IDs before resuming; no replacement objects were created.'
                self.update_stage(self.record['submission_id'], 'AMBIGUOUS', safe_error=message)
                raise PostingAmbiguousError(message, result=self.record)
        return result

    def update_stage(self, submission_id, status, **fields):
        # The template-copy service can resolve a lost POST response by reading
        # and verifying the route copy. Preserve that authoritative recovery.
        for row in fields.get('ad_results') or []:
            if row.get('status') == 'CREATED' and row.get('meta_ad_configured_status') == 'PAUSED' and row.get('meta_ad_id'):
                for operation in self.journal.values():
                    if (operation.get('state') == 'pending'
                            and operation.get('operation') == 'copy_paused_ad_from_template'
                            and operation.get('route') == row.get('index')):
                        operation.update(state='complete', result=row['meta_ad_id'])
        if self.journal:
            rows = deepcopy(fields.get('ad_results', self.record.get('ad_results')) or [{'index': 1}])
            rows[0][KEY] = deepcopy(self.journal)
            fields['ad_results'] = rows
        self.operation = 'checkpoint_' + status.lower()
        result = self.raw.update_stage(submission_id, status, **fields)
        self.record = deepcopy(result or {**self.record, **fields, 'status': status})
        return result

    def persist(self):
        self.update_stage(self.record['submission_id'], self.record['status'])


class RecoveryClient:
    def __init__(self, client, store):
        self.raw, self.store = client, store
        self.resume_verified = False

    def __getattr__(self, name):
        value = getattr(self.raw, name)
        if not callable(value):
            return value
        def call(*args, **kwargs):
            self.store.operation = name
            if name not in WRITES or not self.store.record:
                return value(*args, **kwargs)
            if self.store.resuming and not self.resume_verified:
                verify = getattr(self.raw, 'verify_posting_resume', None)
                if callable(verify):
                    self.store.operation = 'verify_existing_resources'
                    verify(self.store.record)
                self.resume_verified = True
            def encode(obj):
                if isinstance(obj, (bytes, bytearray)):
                    return {'sha256': hashlib.sha256(obj).hexdigest()}
                raise TypeError('Unsupported posting operation input')
            identity_args, identity_kwargs = args, kwargs
            if name == 'create_adset' and args:
                # The service generates start_time from now on every attempt;
                # it is not a new intentional ad set within the same run.
                identity_args = ({k:v for k,v in args[0].items() if k != 'start_time'}, *args[1:])
            if name in {'upload_image', 'upload_page_photo'}:
                identity_kwargs = {k:v for k,v in kwargs.items() if k != 'filename'}
            digest = hashlib.sha256(json.dumps([self.store.route,name,identity_args,identity_kwargs], default=encode, sort_keys=True).encode()).hexdigest()
            previous = self.store.journal.get(digest, {})
            if previous.get('state') == 'complete':
                return previous.get('result')
            if previous.get('state') == 'pending':
                raise MetaAdsAmbiguousResultError('An earlier write requires reconciliation; it will not be repeated.')
            self.store.journal[digest] = {'operation': name, 'route': self.store.route, 'state': 'pending'}
            self.store.persist()  # Must commit intent before contacting Meta.
            self.store.operation = name
            try:
                result = value(*args, **kwargs)
            except MetaAdsAmbiguousResultError:
                raise
            except MetaAdsApiError:
                self.store.journal[digest]['state'] = 'rejected'
                self.store.persist()
                self.store.operation = name
                raise
            # Only IDs/hashes/None are returned by these existing write methods.
            self.store.journal[digest].update(state='complete', result=result)
            self.store.persist()  # Missing acknowledgement leaves durable intent.
            self.store.operation = name
            return result
        return call
