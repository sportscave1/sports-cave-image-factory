"""Explicit JSON boundary for campaign components; domain/cache values stay intact."""
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
import logging
import math
from uuid import UUID


def json_safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('Non-finite component number')
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('Non-finite component decimal')
        return str(value)  # Preserve precision for display metadata.
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, (str, UUID)):
                raise TypeError('Unsupported component key type')
            normalized = str(key)
            if normalized in result:
                raise ValueError('Duplicate component key')
            result[normalized] = json_safe(item)
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(item) for item in value]
    raise TypeError('Unsupported component value type')


def render_component(component, **payload):
    import streamlit as st
    from streamlit.components.v1.custom_component import MarshallComponentException
    try:
        safe = json_safe(payload)
        return component(**safe)
    except (TypeError, ValueError, MarshallComponentException) as exc:
        # Never log payloads, content, identifiers, or exception messages.
        logging.getLogger(__name__).warning('crm_component_payload_failed type=%s', type(exc).__name__)
        st.error('Campaign editor could not load. Your saved content is unchanged. Please retry.')
        return None
