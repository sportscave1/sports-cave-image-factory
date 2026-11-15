"""Request-local optional budget over the existing Shopify adapter and rate gate."""
from copy import copy
import time
from crm_shopify import Shopify


def bounded(shop, seconds=8):
    if not isinstance(shop, Shopify): return shop  # Explicit test adapters.
    scoped = copy(shop)
    scoped.optional_deadline = time.monotonic() + seconds
    return scoped
