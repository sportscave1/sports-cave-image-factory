"""One delay contract. next_due_at is the persisted current-step deadline."""
from copy import deepcopy
from datetime import timedelta
from crm_logic import date


def single_delay(flow):
    result = deepcopy(flow)
    if result.get('timing_version') == 2:
        return result
    if result.get('trigger') == 'abandoned' and result.get('emails'):
        result['emails'][0]['delay_seconds'] += result.get('abandonment_seconds', 3600)
    result.pop('abandonment_seconds', None)
    result['timing_version'] = 2
    return result


def enrollment_steps(automation):
    steps = deepcopy(automation['steps'])
    flow = automation['config']['published']
    if steps and flow['trigger'] == 'abandoned' and flow.get('timing_version') != 2:
        steps[0]['delay_seconds'] += flow.get('abandonment_seconds', 3600)
    return steps


def scheduled_at(trigger_at, delay_seconds):
    anchor = date(trigger_at)
    if not anchor:
        raise ValueError('A verified trigger timestamp is required')
    return anchor + timedelta(seconds=delay_seconds)


def delay_controls(seconds):
    for name, multiplier in (('Days', 86400), ('Hours', 3600)):
        if seconds and seconds % multiplier == 0:
            return seconds // multiplier, name
    return seconds // 60, 'Minutes'
