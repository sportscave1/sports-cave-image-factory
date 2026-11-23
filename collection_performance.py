"""Small operational timing records; never customer IDs, URLs or request bodies."""
from functools import wraps
import logging
import math
import time

LOGGER = logging.getLogger('uvicorn.error.collection_performance')
LOGGER.setLevel(logging.INFO)
OPERATIONS = frozenset({'collection_orders', 'bootstrap', 'review_options', 'recommendations', 'frame_prices', 'pair_products'})


def validate_samples(body):
    if not isinstance(body, dict) or set(body) != {'samples'}:
        raise ValueError('Invalid performance report')
    samples = body['samples']
    if not isinstance(samples, list) or not 1 <= len(samples) <= 12:
        raise ValueError('Invalid performance report size')
    result = []
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {'operation', 'duration_ms', 'outcome'}:
            raise ValueError('Invalid performance sample')
        duration = sample['duration_ms']
        if sample['operation'] not in OPERATIONS or sample['outcome'] not in ('ok', 'error', 'aborted'):
            raise ValueError('Invalid performance operation')
        if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 <= duration <= 120_000:
            raise ValueError('Invalid performance duration')
        result.append((sample['operation'], round(duration), sample['outcome']))
    return result


def observe(operation, handler):
    @wraps(handler)
    async def measured(request):
        if request.method == 'OPTIONS':
            return await handler(request)
        started = time.perf_counter()
        response = await handler(request)
        elapsed = (time.perf_counter() - started) * 1000
        response.headers['Server-Timing'] = f'app;dur={elapsed:.2f}'
        LOGGER.info('collection_perf source=server operation=%s status=%d duration_ms=%.2f', operation, response.status_code, elapsed)
        if operation == 'recommendations':
            from collector_recommendation_cache import CANDIDATES
            LOGGER.info('collection_cache kind=rank counters=%s', CANDIDATES.diagnostics())
        elif operation == 'frame_preview' and request.query_params.get('frame'):
            from collector_preview_cache import PREVIEWS
            LOGGER.info('collection_cache kind=frame counters=%s source_counters=%s', PREVIEWS.images.diagnostics(), PREVIEWS.sources.diagnostics())
        return response
    return measured
