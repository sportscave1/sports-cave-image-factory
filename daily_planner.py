from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import html
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

import os_accounts
import sports_cave_dashboard


OPEN_STATE_KEY = "daily_planner_popup_open"
PLAN_DATE_KEY = "daily_planner_plan_date"
STOP_CONFIRM_KEY = "daily_planner_stop_confirm_timer"
QUERY_PARAM = "daily_planner"
SYDNEY_TZ = ZoneInfo("Australia/Sydney")


def open_daily_planner():
    st.session_state[OPEN_STATE_KEY] = True


def close_daily_planner():
    st.session_state[OPEN_STATE_KEY] = False


def consume_query_open_request(user):
    if not sports_cave_dashboard.can_manage_daily_planner(user):
        return False
    try:
        value = st.query_params.get(QUERY_PARAM, "")
    except Exception:
        return False
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    if str(value or "").strip().casefold() not in {"1", "true", "open", "outcome"}:
        return False
    st.session_state[OPEN_STATE_KEY] = True
    try:
        del st.query_params[QUERY_PARAM]
    except Exception:
        pass
    return True


def _local_now(user):
    timezone_name = os_accounts.timezone_for_user(user) or "Australia/Sydney"
    try:
        tzinfo = ZoneInfo(timezone_name)
    except Exception:
        tzinfo = SYDNEY_TZ
    return datetime.now(timezone.utc).astimezone(tzinfo)


def _rerun():
    try:
        st.rerun()
    except Exception:
        pass


def _status_label(status):
    value = str(status or "").strip().casefold()
    if value == sports_cave_dashboard.DAILY_TASK_STATUS_DONE:
        return "Completed"
    if value == sports_cave_dashboard.DAILY_TASK_STATUS_COULDNT_FINISH:
        return "Did not finish"
    return "Planned"


def _outcome_label(value):
    clean = str(value or "").strip().casefold()
    if clean == sports_cave_dashboard.DAILY_TIMER_OUTCOME_COMPLETED:
        return "Completed"
    if clean == sports_cave_dashboard.DAILY_TIMER_OUTCOME_DID_NOT_FINISH:
        return "Did not finish"
    return ""


def _format_timestamp(value, timezone_name="Australia/Sydney"):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    try:
        tzinfo = ZoneInfo(timezone_name)
    except Exception:
        tzinfo = SYDNEY_TZ
    return value.astimezone(tzinfo).strftime("%d %b, %I:%M %p").lstrip("0")


def _duration_number_minutes(seconds):
    try:
        return max(float(seconds or 0) / 60, 0.02)
    except (TypeError, ValueError):
        return 0.02


def _timer_lookup(timers):
    return {
        (str(timer.get("task_type") or ""), int(timer.get("task_index") or 0)): dict(timer)
        for timer in timers or []
    }


def _audio_bridge(*, play_alarm=False, bridge_key="daily-planner-audio"):
    components.html(
        f"""
        <script>
        (() => {{
          const parentWindow = window.parent || window;
          const doc = parentWindow.document;
          const KEY = "SportsCavePlannerAudio";
          const createTone = async (testOnly = false) => {{
            const AudioContext = parentWindow.AudioContext || parentWindow.webkitAudioContext;
            if (!AudioContext) return false;
            const audio = parentWindow[KEY]?.context || new AudioContext();
            parentWindow[KEY] = parentWindow[KEY] || {{}};
            parentWindow[KEY].context = audio;
            try {{ await audio.resume(); }} catch (_error) {{ return false; }}
            const playOne = (offset, duration, frequency) => {{
              const oscillator = audio.createOscillator();
              const gain = audio.createGain();
              oscillator.type = "sine";
              oscillator.frequency.setValueAtTime(frequency, audio.currentTime + offset);
              gain.gain.setValueAtTime(0.0001, audio.currentTime + offset);
              gain.gain.exponentialRampToValueAtTime(0.16, audio.currentTime + offset + 0.02);
              gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + offset + duration);
              oscillator.connect(gain);
              gain.connect(audio.destination);
              oscillator.start(audio.currentTime + offset);
              oscillator.stop(audio.currentTime + offset + duration + 0.04);
            }};
            playOne(0, testOnly ? 0.12 : 0.2, 660);
            if (!testOnly) {{
              playOne(0.26, 0.2, 880);
              playOne(0.52, 0.25, 660);
            }}
            return true;
          }};
          const install = () => {{
            parentWindow[KEY] = parentWindow[KEY] || {{}};
            parentWindow[KEY].play = () => createTone(false);
            parentWindow[KEY].test = () => createTone(true);
            if (parentWindow[KEY].controller) parentWindow[KEY].controller.abort();
            const controller = new parentWindow.AbortController();
            parentWindow[KEY].controller = controller;
            doc.addEventListener("click", (event) => {{
              const button = event.target?.closest?.("button");
              const text = String(button?.textContent || "");
              if (/Start Timer|Enable Sound|Test Sound/.test(text)) createTone(/Enable Sound|Test Sound/.test(text));
            }}, {{capture: true, signal: controller.signal}});
          }};
          install();
          if ({str(bool(play_alarm)).lower()}) {{
            parentWindow[KEY]?.play?.().then((ok) => {{
              if (!ok) {{
                doc.body.setAttribute("data-sc-planner-audio-blocked", "true");
                const existing = doc.getElementById("sc-planner-audio-blocked");
                const notice = existing || doc.createElement("div");
                notice.id = "sc-planner-audio-blocked";
                notice.textContent = "Daily Planner sound was blocked by the browser. Use Test Sound or check site audio permissions.";
                notice.style.cssText = "position:fixed;right:24px;bottom:24px;z-index:2147483647;max-width:320px;padding:12px 14px;border-radius:8px;background:#1f1f1f;color:#fff;font:13px/1.4 system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;box-shadow:0 12px 32px rgba(0,0,0,.28);";
                if (!existing) doc.body.appendChild(notice);
                parentWindow.setTimeout(() => notice.remove(), 8000);
              }}
            }});
          }}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _countdown_bridge(rows):
    payload = []
    for row in rows:
        timer = row.get("timer") or {}
        if str(timer.get("status") or "") == "running" and timer.get("deadline_at"):
            payload.append(
                {
                    "id": row["row_id"],
                    "deadline": str(timer.get("deadline_at")),
                }
            )
    components.html(
        f"""
        <script>
        (() => {{
          const parentWindow = window.parent || window;
          const doc = parentWindow.document;
          const timers = {payload!r};
          if (parentWindow.SportsCavePlannerCountdown) {{
            parentWindow.clearInterval(parentWindow.SportsCavePlannerCountdown);
          }}
          const pad = (value) => String(Math.max(Number(value) || 0, 0)).padStart(2, "0");
          const render = () => {{
            timers.forEach((timer) => {{
              const target = doc.querySelector(`[data-sc-planner-countdown="${{timer.id}}"]`);
              if (!target) return;
              const remaining = Math.max(Math.ceil((new Date(timer.deadline).getTime() - Date.now()) / 1000), 0);
              const hours = Math.floor(remaining / 3600);
              const minutes = Math.floor((remaining % 3600) / 60);
              const seconds = remaining % 60;
              target.textContent = hours ? `${{hours}}:${{pad(minutes)}}:${{pad(seconds)}}` : `${{pad(minutes)}}:${{pad(seconds)}}`;
              target.dataset.remainingSeconds = String(remaining);
            }});
          }};
          render();
          parentWindow.SportsCavePlannerCountdown = parentWindow.setInterval(render, 1000);
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _render_planning_form(user, target_date, existing_sheet, source_sheet, timezone_name):
    date_key = target_date.isoformat()
    top_tasks = (existing_sheet or {}).get("top_tasks") or sports_cave_dashboard._blank_top_tasks()
    existing_other = [
        item
        for item in (existing_sheet or {}).get("additional_items") or []
        if sports_cave_dashboard._daily_additional_item_has_content(item)
    ]
    count_key = f"daily-planner-other-count::{date_key}"
    st.session_state.setdefault(count_key, max(len(existing_other) + 1, 1))
    carry_candidates = sports_cave_dashboard.daily_execution_unfinished_tasks(source_sheet)

    with st.form(f"daily-planner-plan::{date_key}"):
        st.markdown("**Three priority tasks**")
        planned_top = []
        for index in range(3):
            task = dict(top_tasks[index] if index < len(top_tasks) else {})
            cols = st.columns([2.2, 2.4, 1.1], gap="small")
            planned_top.append(
                {
                    "task": cols[0].text_input(
                        f"MIP Task {index + 1}",
                        value=task.get("task") or "",
                        key=f"daily-planner-mip-task::{date_key}::{index}",
                    ),
                    "why": cols[1].text_input(
                        "Details/outcome required",
                        value=task.get("why") or "",
                        key=f"daily-planner-mip-details::{date_key}::{index}",
                    ),
                    "time_blocked": cols[2].text_input(
                        "Allocated",
                        value=task.get("time_blocked") or "",
                        key=f"daily-planner-mip-time::{date_key}::{index}",
                    ),
                    "status": task.get("status") or "",
                    "completed_at": task.get("completed_at"),
                }
            )

        selected_carryovers = []
        if carry_candidates:
            st.markdown("**Carryover**")
            for index, candidate in enumerate(carry_candidates):
                selected = st.checkbox(
                    candidate.get("task") or "Unfinished task",
                    value=False,
                    key=f"daily-planner-carry::{date_key}::{index}",
                )
                if selected:
                    selected_carryovers.append(
                        {
                            "key": candidate.get("key") or str(index),
                            "task": candidate.get("task") or "",
                            "details": candidate.get("details") or "",
                            "time_blocked": candidate.get("time_blocked") or "",
                            "status": "",
                            "carried_from": (source_sheet or {}).get("sheet_date") or "",
                        }
                    )

        st.markdown("**Other tasks**")
        planned_other = []
        for index in range(int(st.session_state.get(count_key) or 1)):
            task = dict(existing_other[index] if index < len(existing_other) else {})
            cols = st.columns([2.2, 2.4, 1.1], gap="small")
            planned_other.append(
                {
                    "task": cols[0].text_input(
                        "Other task",
                        value=task.get("task") or "",
                        key=f"daily-planner-other-task::{date_key}::{index}",
                    ),
                    "details": cols[1].text_input(
                        "Details",
                        value=task.get("details") or "",
                        key=f"daily-planner-other-details::{date_key}::{index}",
                    ),
                    "time_blocked": cols[2].text_input(
                        "Allocated",
                        value=task.get("time_blocked") or "",
                        key=f"daily-planner-other-time::{date_key}::{index}",
                    ),
                    "status": task.get("status") or "",
                    "completed_at": task.get("completed_at"),
                }
            )
        planning = (existing_sheet or {}).get("planning_data") or {}
        main_outcome = st.text_input(
            "Main outcome for the day",
            value=planning.get("main_outcome") or "",
            key=f"daily-planner-outcome::{date_key}",
        )
        fixed_event = st.text_input(
            "Appointment, deadline or fixed event",
            value=planning.get("fixed_event") or "",
            key=f"daily-planner-fixed::{date_key}",
        )
        notes = st.text_area(
            "Optional planning notes",
            value=planning.get("notes") or "",
            key=f"daily-planner-notes::{date_key}",
        )
        actions = st.columns([1, 1, 1.4], gap="small")
        add_other = actions[0].form_submit_button("Add other task", use_container_width=True)
        cancel = actions[1].form_submit_button("Cancel", use_container_width=True)
        save = actions[2].form_submit_button("Save plan", type="primary", use_container_width=True)

    if add_other:
        st.session_state[count_key] = int(st.session_state.get(count_key) or 1) + 1
        _rerun()
    if cancel:
        st.session_state.pop(PLAN_DATE_KEY, None)
        _rerun()
    if save:
        if any(not str(task.get("task") or "").strip() for task in planned_top):
            st.warning("Add all three MIP tasks before saving the plan.")
            return
        try:
            saved = sports_cave_dashboard.save_daily_execution_plan(
                user,
                target_date,
                timezone_name,
                planned_top,
                selected_carryovers + planned_other,
                {
                    "main_outcome": main_outcome,
                    "fixed_event": fixed_event,
                    "notes": notes,
                    "carried_forward": selected_carryovers,
                    "planned_for": date_key,
                },
            )
        except sports_cave_dashboard.DashboardStorageError as error:
            st.warning(str(error) or "The Daily Planner could not save right now.")
            return
        if not saved:
            st.warning("The Daily Planner could not confirm the saved plan.")
            return
        st.session_state.pop(PLAN_DATE_KEY, None)
        st.success("Plan saved.")
        _rerun()


def _render_task_save_form(user, sheet):
    sheet_id = sheet.get("id")
    with st.form(f"daily-planner-tasks::{sheet_id}"):
        updated_top = []
        updated_other = []
        status_options = ("", sports_cave_dashboard.DAILY_TASK_STATUS_DONE, sports_cave_dashboard.DAILY_TASK_STATUS_COULDNT_FINISH)
        st.markdown("**Tasks**")
        for index, task in enumerate(sheet.get("top_tasks") or [], start=1):
            cols = st.columns([2.1, 2.2, 1, 1.1], gap="small")
            status = str(task.get("status") or "").strip()
            updated_top.append(
                {
                    "task": cols[0].text_input("Task", value=task.get("task") or "", key=f"daily-planner-task-title::{sheet_id}::{index}", label_visibility="collapsed"),
                    "why": cols[1].text_input("Details", value=task.get("why") or "", key=f"daily-planner-task-details::{sheet_id}::{index}", label_visibility="collapsed"),
                    "time_blocked": cols[2].text_input("Allocated", value=task.get("time_blocked") or "", key=f"daily-planner-task-time::{sheet_id}::{index}", label_visibility="collapsed"),
                    "status": cols[3].selectbox(
                        "Status",
                        status_options,
                        index=status_options.index(status) if status in status_options else 0,
                        format_func=_status_label,
                        key=f"daily-planner-task-status::{sheet_id}::{index}",
                        label_visibility="collapsed",
                    ),
                    "completed_at": task.get("completed_at"),
                    "finished_at": task.get("finished_at"),
                    "outcome": task.get("outcome") or "",
                }
            )
        st.markdown("**Other tasks**")
        for index, task in enumerate(sheet.get("additional_items") or [{"task": "", "details": "", "time_blocked": "", "status": ""}], start=1):
            cols = st.columns([2.1, 2.2, 1, 1.1], gap="small")
            status = str(task.get("status") or "").strip()
            updated_other.append(
                {
                    "task": cols[0].text_input("Other task", value=task.get("task") or "", key=f"daily-planner-other-title::{sheet_id}::{index}", label_visibility="collapsed"),
                    "details": cols[1].text_input("Details", value=task.get("details") or "", key=f"daily-planner-other-details-save::{sheet_id}::{index}", label_visibility="collapsed"),
                    "time_blocked": cols[2].text_input("Allocated", value=task.get("time_blocked") or "", key=f"daily-planner-other-time-save::{sheet_id}::{index}", label_visibility="collapsed"),
                    "status": cols[3].selectbox(
                        "Status",
                        status_options,
                        index=status_options.index(status) if status in status_options else 0,
                        format_func=_status_label,
                        key=f"daily-planner-other-status::{sheet_id}::{index}",
                        label_visibility="collapsed",
                    ),
                    "completed_at": task.get("completed_at"),
                    "finished_at": task.get("finished_at"),
                    "outcome": task.get("outcome") or "",
                }
            )
        save = st.form_submit_button("Save List", use_container_width=True)
    if save:
        try:
            sports_cave_dashboard.save_daily_execution_tasks(
                sheet_id,
                updated_top,
                updated_other,
                user=user,
            )
        except sports_cave_dashboard.DashboardStorageError as error:
            st.warning(str(error) or "The task list could not save right now.")
            return
        _rerun()


def _render_timer_controls(user, rows):
    if not rows:
        return
    active = {}
    try:
        active = sports_cave_dashboard.get_active_daily_planner_timer(user)
    except sports_cave_dashboard.DashboardStorageError:
        active = {}
    st.markdown("**Timers**")
    _audio_bridge()
    _countdown_bridge(rows)
    sound_cols = st.columns([1, 1, 4], gap="small")
    sound_cols[0].button("Enable Sound", key="daily-planner-enable-sound", use_container_width=True)
    sound_cols[1].button("Test Sound", key="daily-planner-test-sound", use_container_width=True)
    sound_cols[2].caption("Sound can play while Sports Cave OS is open after a user interaction.")
    for row in rows:
        timer = row.get("timer") or {}
        row_id = row["row_id"]
        allocated_seconds = row.get("allocated_seconds") or int(timer.get("allocated_seconds") or 0)
        with st.container(border=True):
            cols = st.columns([2.2, 0.9, 0.9, 1.1, 1.35], gap="small")
            cols[0].markdown(f"**{html.escape(row.get('task') or 'Task')}**")
            cols[0].caption(f"{row.get('category') or 'Task'} | {row.get('details') or 'No details'}")
            cols[1].metric("Allocated", sports_cave_dashboard.format_duration_seconds(allocated_seconds))
            remaining = int(timer.get("remaining_seconds") or allocated_seconds or 0)
            if timer.get("status") == "running":
                remaining_html = (
                    f'<span data-sc-planner-countdown="{html.escape(row_id, quote=True)}">'
                    f'{sports_cave_dashboard.format_duration_seconds(remaining)}</span>'
                )
                cols[2].markdown(f"**Remaining**<br>{remaining_html}", unsafe_allow_html=True)
            else:
                cols[2].metric("Remaining", sports_cave_dashboard.format_duration_seconds(remaining))
            cols[3].metric("Elapsed", sports_cave_dashboard.format_duration_seconds(timer.get("elapsed_seconds") or timer.get("actual_elapsed_seconds") or 0))
            status = str(timer.get("status") or "").strip()
            if status:
                cols[4].caption(f"Timer: {status.title()}")
            else:
                cols[4].caption(row.get("status") or "Planned")

            control_cols = st.columns([0.8, 0.8, 0.9, 1.1, 2], gap="small")
            duration_minutes = control_cols[0].number_input(
                "Timer minutes",
                min_value=0.02,
                max_value=480.0,
                value=round(_duration_number_minutes(allocated_seconds), 2),
                step=0.5,
                key=f"daily-planner-duration::{row_id}",
                disabled=bool(status in {"running", "paused", "expired"}),
            )
            active_is_other = bool(
                active
                and active.get("id")
                and (
                    active.get("sheet_id") != row.get("sheet_id")
                    or active.get("task_type") != row.get("task_type")
                    or int(active.get("task_index") or 0) != int(row.get("task_index") or 0)
                )
                and active.get("status") in sports_cave_dashboard.DAILY_TIMER_RUNNING_STATUSES
            )
            if not status or status in {"idle", "stopped", "completed"}:
                if control_cols[1].button(
                    "Start Timer",
                    key=f"daily-planner-start::{row_id}",
                    disabled=active_is_other or bool(row.get("status") in {"Completed", "Did not finish"}) or duration_minutes <= 0,
                    use_container_width=True,
                ):
                    try:
                        sports_cave_dashboard.start_daily_planner_timer(
                            user,
                            row.get("sheet_id"),
                            row.get("task_type"),
                            row.get("task_index"),
                            int(round(float(duration_minutes) * 60)),
                        )
                    except sports_cave_dashboard.DashboardStorageError as error:
                        st.warning(str(error))
                    else:
                        _rerun()
            elif status == "running":
                if control_cols[1].button("Pause", key=f"daily-planner-pause::{row_id}", use_container_width=True):
                    try:
                        sports_cave_dashboard.pause_daily_planner_timer(user, timer.get("id"))
                    except sports_cave_dashboard.DashboardStorageError as error:
                        st.warning(str(error))
                    else:
                        _rerun()
            elif status == "paused":
                if control_cols[1].button("Resume", key=f"daily-planner-resume::{row_id}", use_container_width=True):
                    try:
                        sports_cave_dashboard.resume_daily_planner_timer(user, timer.get("id"))
                    except sports_cave_dashboard.DashboardStorageError as error:
                        st.warning(str(error))
                    else:
                        _rerun()
            if status in {"running", "paused", "expired"} and not timer.get("outcome"):
                confirm = st.session_state.get(STOP_CONFIRM_KEY) == timer.get("id")
                if not confirm:
                    if control_cols[2].button("Stop/reset", key=f"daily-planner-stop-open::{row_id}", use_container_width=True):
                        st.session_state[STOP_CONFIRM_KEY] = timer.get("id")
                        _rerun()
                else:
                    if control_cols[2].button("Confirm reset", key=f"daily-planner-stop-confirm::{row_id}", use_container_width=True):
                        try:
                            sports_cave_dashboard.stop_daily_planner_timer(user, timer.get("id"))
                        except sports_cave_dashboard.DashboardStorageError as error:
                            st.warning(str(error))
                        else:
                            st.session_state.pop(STOP_CONFIRM_KEY, None)
                            _rerun()
                    if control_cols[3].button("Keep timer", key=f"daily-planner-stop-cancel::{row_id}", use_container_width=True):
                        st.session_state.pop(STOP_CONFIRM_KEY, None)
                        _rerun()
            if active_is_other:
                control_cols[4].warning(f"Active timer: {active.get('task') or 'Daily Planner task'}")


def _render_daily_review(user, sheet):
    if not sports_cave_dashboard.daily_execution_all_tasks_complete(sheet):
        st.caption("Complete or close all three MIP tasks to unlock Daily Review.")
        return
    if sports_cave_dashboard.daily_execution_review_complete(sheet):
        st.caption("Daily Review complete.")
        return
    with st.expander("Daily Review", expanded=False):
        with st.form(f"daily-planner-review::{sheet.get('id')}"):
            completed = st.text_area("What was completed today?", key=f"daily-planner-review-completed::{sheet.get('id')}")
            unfinished = st.text_area("What could not be finished and why?", key=f"daily-planner-review-unfinished::{sheet.get('id')}")
            tomorrow = st.text_area("What is the ONE THING tomorrow must nail?", key=f"daily-planner-review-tomorrow::{sheet.get('id')}")
            rating = st.number_input("Overall Score", min_value=1, max_value=10, value=7, step=1, key=f"daily-planner-review-rating::{sheet.get('id')}")
            submitted = st.form_submit_button("Complete Daily Review", type="primary", use_container_width=True)
        if submitted:
            try:
                sports_cave_dashboard.complete_daily_execution_review(
                    sheet.get("id"),
                    {
                        "daily_summary": completed,
                        "tomorrow_intention": tomorrow,
                        "review_data": {"completed": completed, "could_not_finish": unfinished},
                        "no_grey_zone": {"completed": completed, "avoided": unfinished},
                        "ratings": {"Overall Score": rating},
                    },
                    user=user,
                )
            except sports_cave_dashboard.DashboardStorageError as error:
                st.warning(str(error) or "Daily Review could not save right now.")
            else:
                _rerun()


def _render_planner_body(user):
    local_now = _local_now(user)
    today = local_now.date()
    timezone_name = os_accounts.timezone_for_user(user) or "Australia/Sydney"
    try:
        events = sports_cave_dashboard.reconcile_daily_planner_timers(user)
        for event in events:
            if event.get("event") == "halfway":
                task = event.get("task") or "Daily Planner task"
                if hasattr(st, "toast"):
                    st.toast(f"Halfway through: {task}")
    except sports_cave_dashboard.DashboardStorageError:
        pass
    try:
        sheets = sports_cave_dashboard.get_daily_execution_home_sheets(user, today)
    except sports_cave_dashboard.DashboardStorageError:
        st.warning("Daily Planner could not load right now.")
        return
    sheet = sheets.get("today") or sheets.get("carryover_review") or {}
    tomorrow_sheet = sheets.get("tomorrow") or {}
    workflow_date = today
    if sheet.get("sheet_date"):
        try:
            workflow_date = date.fromisoformat(sheet.get("sheet_date"))
        except ValueError:
            workflow_date = today
    st.caption(f"Work date: {workflow_date.strftime('%A, %d %B %Y').replace(', 0', ', ')}")

    plan_date = st.session_state.get(PLAN_DATE_KEY)
    if plan_date:
        try:
            target_date = date.fromisoformat(str(plan_date))
        except ValueError:
            target_date = today
        _render_planning_form(
            user,
            target_date,
            sheet if target_date == today else tomorrow_sheet,
            sheet,
            timezone_name,
        )
        return

    if not sheet:
        st.info("Today's execution sheet has not been planned.")
        if st.button("Create today's sheet", key="daily-planner-create-today", type="primary", use_container_width=True):
            st.session_state[PLAN_DATE_KEY] = today.isoformat()
            _rerun()
        return

    action_cols = st.columns([1, 1, 4], gap="small")
    if sports_cave_dashboard.daily_execution_review_complete(sheet):
        if action_cols[0].button("Plan tomorrow", key="daily-planner-plan-tomorrow", type="primary", use_container_width=True):
            st.session_state[PLAN_DATE_KEY] = (workflow_date + timedelta(days=1)).isoformat()
            _rerun()
        if tomorrow_sheet:
            action_cols[1].caption("Tomorrow saved")
    _render_task_save_form(user, sheet)

    try:
        backend = sports_cave_dashboard.get_supabase_backend()
        timers = (
            backend.list_daily_execution_timers_for_sheets(
                sports_cave_dashboard.daily_execution_user_id(user),
                [sheet.get("id")],
            )
            if hasattr(backend, "list_daily_execution_timers_for_sheets")
            else []
        )
    except Exception:
        timers = []
    rows = sports_cave_dashboard.daily_execution_task_rows(sheet, timers)
    _render_timer_controls(user, rows)
    _render_daily_review(user, sheet)


def _render_outcome_dialog(user, timer):
    alarm_key = (
        f"daily_planner_alarm_played::{timer.get('id')}::"
        f"{timer.get('expiry_notified_at') or timer.get('updated_at') or ''}"
    )
    should_play_alarm = not st.session_state.get(alarm_key)
    if should_play_alarm:
        st.session_state[alarm_key] = True
    _audio_bridge(play_alarm=should_play_alarm, bridge_key=f"daily-planner-alarm::{timer.get('id')}")

    @st.dialog("Time's up", width="large")
    def outcome_dialog():
        st.warning("Time’s up — did you complete this task?")
        st.markdown(f"**{html.escape(timer.get('task') or 'Daily Planner task')}**")
        st.caption(f"Elapsed: {sports_cave_dashboard.format_duration_seconds(timer.get('elapsed_seconds') or timer.get('actual_elapsed_seconds') or timer.get('allocated_seconds'))}")
        st.caption("If you do not hear the chime, use Test Sound in the Daily Planner or check browser site audio permissions.")
        actions = st.columns(2, gap="small")
        if actions[0].button("Completed", key=f"daily-planner-outcome-completed::{timer.get('id')}", type="primary", use_container_width=True):
            try:
                sports_cave_dashboard.apply_daily_planner_timer_outcome(
                    user,
                    timer.get("id"),
                    sports_cave_dashboard.DAILY_TIMER_OUTCOME_COMPLETED,
                )
            except sports_cave_dashboard.DashboardStorageError as error:
                st.warning(str(error))
            else:
                st.session_state[OPEN_STATE_KEY] = True
                _rerun()
        if actions[1].button("Half complete / Did not finish", key=f"daily-planner-outcome-dnf::{timer.get('id')}", use_container_width=True):
            try:
                sports_cave_dashboard.apply_daily_planner_timer_outcome(
                    user,
                    timer.get("id"),
                    sports_cave_dashboard.DAILY_TIMER_OUTCOME_DID_NOT_FINISH,
                )
            except sports_cave_dashboard.DashboardStorageError as error:
                st.warning(str(error))
            else:
                st.session_state[OPEN_STATE_KEY] = True
                _rerun()
        if st.button("Stop Sound/Dismiss", key=f"daily-planner-stop-sound::{timer.get('id')}", use_container_width=True):
            st.caption("Choose an outcome above to clear this prompt.")

    outcome_dialog()


def _render_planner_dialog(user):
    @st.dialog("Daily Planner", width="large")
    def planner_dialog():
        close_cols = st.columns([5, 1], gap="small")
        close_cols[0].caption("Daily Task Execution Sheet")
        if close_cols[1].button("Close", key="daily-planner-close", use_container_width=True):
            close_daily_planner()
            _rerun()
        _render_planner_body(user)

    planner_dialog()


def render_daily_planner_overlays(user):
    if not sports_cave_dashboard.can_manage_daily_planner(user):
        st.session_state.pop(OPEN_STATE_KEY, None)
        return False
    consume_query_open_request(user)
    try:
        active = sports_cave_dashboard.get_active_daily_planner_timer(user)
    except sports_cave_dashboard.DashboardStorageError:
        active = {}
    if active and (active.get("outcome_required") or active.get("status") == "expired"):
        _render_outcome_dialog(user, active)
        return True
    if st.session_state.get(OPEN_STATE_KEY):
        _render_planner_dialog(user)
        return True
    return False
