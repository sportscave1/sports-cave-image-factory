"""Read-time normalization preserves planner history and raw public inputs."""
import copy
from datetime import date
from unittest.mock import patch

import sports_cave_dashboard as dashboard


def sheet(day, **extra):
    return dict(id=f'sheet-{day}', user_id='owner', sheet_date=f'2026-08-{day:02d}',
                top_tasks=[dict(title=' Legacy title ', time='30 min', completed=True)],
                additional_items=[dict(note='Other task', time_allocated='15 min', status='skipped')], **extra)


def test_raw_entries_preserve_legacy_fields_and_do_not_mutate_inputs():
    rows = [sheet(3)]
    original = copy.deepcopy(rows)
    tasks = dashboard.daily_execution_weekly_task_instances(rows, today=date(2026, 8, 10))
    assert [(row['task'], row['outcome'], row['allocated_seconds']) for row in tasks] == [
        ('Legacy title', 'completed', 1800), ('Other task', 'skipped', 900)]
    summary = dashboard.daily_execution_weekly_summary(rows, today=date(2026, 8, 10))
    assert (summary['total_planned'], summary['completed'], summary['skipped']) == (2, 1, 1)
    assert rows == original


def test_summary_normalises_each_raw_sheet_once_and_excludes_future_or_bad_dates():
    rows = [sheet(3), sheet(11), dict(sheet(4), sheet_date='bad-date')]
    with patch.object(dashboard, '_normalise_daily_sheet', wraps=dashboard._normalise_daily_sheet) as normalise:
        summary = dashboard.daily_execution_weekly_summary(rows, today=date(2026, 8, 10))
    assert normalise.call_count == len(rows)
    assert summary['total_planned'] == 2
    assert summary['days_planned'] == 1


def test_carry_chain_keeps_latest_outcome_and_distinct_day_rows():
    first = dict(sheet(3), additional_items=[], top_tasks=[dict(task='Shared task', status='couldnt_finish')])
    second = dict(sheet(4), additional_items=[], top_tasks=[dict(task='Shared task', status='done', carried_from='2026-08-03')])
    result = dashboard.daily_execution_weekly_summary([second, first], today=date(2026, 8, 10))
    assert (result['total_planned'], result['completed'], result['did_not_finish']) == (1, 1, 0)
    assert result['days_planned'] == 2


def test_timer_outcomes_keep_paused_elapsed_and_zero_override():
    rows = [sheet(3)]
    timers = [dict(sheet_id='sheet-3', task_type='top', task_index=0, status='paused',
                   allocated_seconds=1800, remaining_seconds=300),
              dict(sheet_id='sheet-3', task_type='additional', task_index=0, actual_elapsed_seconds=0)]
    tasks = dashboard.daily_execution_weekly_task_instances(rows, timers, today=date(2026, 8, 10))
    assert [task['actual_elapsed_seconds'] for task in tasks] == [1500, 0]


def test_normalisation_is_per_call_and_has_no_stale_result_cache():
    rows = [sheet(3)]
    assert dashboard.daily_execution_weekly_summary(rows, today=date(2026, 8, 10))['completed'] == 1
    rows[0]['top_tasks'][0].update(completed=False, status='couldnt_finish')
    result = dashboard.daily_execution_weekly_summary(rows, today=date(2026, 8, 10))
    assert result['completed'] == 0
    assert result['did_not_finish'] == 1
