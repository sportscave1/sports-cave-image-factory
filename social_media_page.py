import html
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st

from activity_log import record_activity_log
import os_accounts
import social_media
import social_media_store


HISTORY_PAGE_SIZE = 15


PLATFORM_ICONS = {
    "Instagram": """
        <rect x="3" y="3" width="18" height="18" rx="5"></rect>
        <circle cx="12" cy="12" r="4"></circle>
        <circle cx="17.4" cy="6.7" r="1" class="fill"></circle>
    """,
    "Facebook": """
        <path class="fill" d="M14.2 22v-8h2.8l.5-3.2h-3.3V8.7c0-.9.3-1.6 1.7-1.6h1.8V4.2c-.3 0-1.4-.2-2.6-.2-2.6 0-4.4 1.6-4.4 4.5v2.3H8v3.2h2.7v8h3.5z"></path>
    """,
    "Pinterest": """
        <circle cx="12" cy="12" r="9"></circle>
        <path d="M10.1 18.5c.7-2 1.1-3 1.4-4.3-.7-1.3.1-4 1.5-4 1.2 0 1.3 1.5.9 2.6-.4 1.1.1 2 1.1 2 1.4 0 2.4-1.8 2.4-4.3 0-2.3-1.7-4-4.2-4-2.9 0-4.6 2.2-4.6 4.4 0 .9.3 1.8.8 2.3"></path>
    """,
    "TikTok": """
        <path class="fill" d="M14.2 3h3.1c.2 1.7 1.2 3 2.7 3.7v3.1c-1.4 0-2.7-.4-3.8-1.2v6.2c0 3.6-2.5 6.2-6 6.2-3.2 0-5.8-2.6-5.8-5.8s2.6-5.8 5.8-5.8c.4 0 .8 0 1.2.1v3.2c-.4-.1-.7-.2-1.1-.2-1.5 0-2.7 1.2-2.7 2.7s1.2 2.7 2.7 2.7c1.7 0 2.8-1.1 2.8-3.2V3h1.1z"></path>
    """,
    "YouTube": """
        <rect x="2.5" y="5.5" width="19" height="13" rx="4"></rect>
        <path class="fill-bg" d="M10 9l6 3-6 3z"></path>
    """,
}


def _inject_styles():
    st.markdown(
        """
        <style>
        .sc-social-header {
            background: #111111;
            border-bottom: 3px solid #b58a2a;
            border-radius: 6px;
            color: #ffffff;
            margin-bottom: 0.9rem;
            padding: 1.15rem 1.3rem;
        }
        .sc-social-header h1 {
            color: #ffffff !important;
            font-size: 1.65rem;
            letter-spacing: 0;
            line-height: 1.15;
            margin: 0;
        }
        .sc-social-header p {
            color: #d8d4ca !important;
            font-size: 0.88rem;
            margin: 0.35rem 0 0;
        }
        .sc-social-profiles {
            display: grid;
            gap: 0.55rem;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            margin: 0.1rem 0 1rem;
        }
        .sc-social-profile {
            align-items: center;
            background: #ffffff;
            border: 1px solid #dedbd3;
            border-radius: 6px;
            color: #171717 !important;
            display: flex;
            gap: 0.55rem;
            min-height: 3.2rem;
            padding: 0.6rem 0.7rem;
            text-decoration: none !important;
            transition: border-color 120ms ease, box-shadow 120ms ease;
        }
        .sc-social-profile:hover,
        .sc-social-profile:focus-visible {
            border-color: #b58a2a;
            box-shadow: 0 0 0 2px rgba(181, 138, 42, 0.16);
            outline: none;
        }
        .sc-social-profile svg {
            color: #181818;
            fill: none;
            flex: 0 0 1.45rem;
            height: 1.45rem;
            stroke: currentColor;
            stroke-linecap: round;
            stroke-linejoin: round;
            stroke-width: 1.8;
            width: 1.45rem;
        }
        .sc-social-profile svg .fill {
            fill: currentColor;
            stroke: none;
        }
        .sc-social-profile svg .fill-bg {
            fill: #ffffff;
            stroke: none;
        }
        .sc-social-profile-name {
            font-size: 0.82rem;
            font-weight: 700;
            line-height: 1.1;
            min-width: 0;
        }
        .sc-social-profile-open {
            color: #77736b;
            display: block;
            font-size: 0.68rem;
            font-weight: 500;
            margin-top: 0.14rem;
        }
        .sc-social-post-row {
            border-top: 1px solid #ebe7de;
            padding: 0.75rem 0 0.2rem;
        }
        .sc-social-post-title {
            font-size: 0.96rem;
            font-weight: 720;
        }
        .sc-social-post-meta {
            color: #716d65;
            font-size: 0.76rem;
            margin-top: 0.1rem;
        }
        .sc-social-live-link {
            color: #765914 !important;
            font-size: 0.78rem;
            font-weight: 650;
            text-decoration: underline;
        }
        @media (max-width: 900px) {
            .sc-social-profiles {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _profile_shortcuts():
    cards = []
    for platform, url in social_media.SOCIAL_PROFILES:
        safe_platform = html.escape(platform)
        safe_url = html.escape(url, quote=True)
        icon = PLATFORM_ICONS[platform]
        cards.append(
            f'<a class="sc-social-profile" href="{safe_url}" target="_blank" '
            f'rel="noopener noreferrer" aria-label="Open Sports Cave {safe_platform}">'
            f'<svg viewBox="0 0 24 24" role="img" aria-label="{safe_platform}">{icon}</svg>'
            f'<span class="sc-social-profile-name">{safe_platform}'
            '<span class="sc-social-profile-open">Open</span>'
            "</span></a>"
        )
    st.markdown(
        f'<div class="sc-social-profiles">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def _record_activity(result):
    activity = (result or {}).get("activity")
    if not activity:
        return
    record_activity_log(
        activity["action_type"],
        activity["page"],
        activity["message"],
        entity_type=activity["entity_type"],
        entity_id=activity["entity_id"],
        metadata=activity["metadata"],
        event_key=activity["event_key"],
    )


def _show_result_notice():
    notice = st.session_state.pop("social-media-notice", None)
    if not notice:
        return
    if notice.get("ok"):
        st.success(notice.get("message") or "Saved.")
    else:
        st.warning(notice.get("message") or "That change could not be saved.")


def _set_notice(ok, message):
    st.session_state["social-media-notice"] = {
        "ok": bool(ok),
        "message": str(message or ""),
    }


def _admin_staff_selector(user, staff):
    if not os_accounts.is_admin(user):
        return user
    by_id = {account["id"]: account for account in staff}
    selected_id = st.selectbox(
        "Staff member",
        tuple(by_id),
        format_func=lambda account_id: by_id[account_id]["display_name"],
        key="social-media-staff-selector",
    )
    return by_id[selected_id]


def _metric_cards(summary):
    columns = st.columns(4)
    columns[0].metric(
        "MIPs completed",
        f"{summary.get('priorities_completed', 0)} / {summary.get('priorities_total', 0)}",
    )
    columns[1].metric("Posts live today", summary.get("posts_live", 0))
    columns[2].metric(
        "Platforms used",
        len(summary.get("platforms_used") or []),
    )
    columns[3].metric("Daily score", f"{float(summary.get('score') or 0):.1f} / 10")


def _plan_defaults(snapshot):
    plan = snapshot.get("plan") or {}
    priorities = {
        int(row.get("priority_index") or 0): row
        for row in snapshot.get("priorities") or []
    }
    return plan, priorities


def _render_team_today(user, store, account_store, plan_date):
    if not os_accounts.is_admin(user):
        return
    if not st.toggle("Team today", value=False, key="social-media-team-today"):
        return
    try:
        rows = store.team_today_summary(
            user,
            plan_date=plan_date,
            account_store=account_store,
        )
    except Exception:
        st.warning("Team progress could not load right now.")
        return
    st.dataframe(
        [
            {
                "Staff": row["staff"]["display_name"],
                "Plan": str(row["plan_status"]).replace("_", " ").title(),
                "MIPs": f"{row['priorities_completed']} / {row['priorities_total']}",
                "Posts live": row["posts_live"],
                "Score": f"{row['score']:.1f}",
                "Blocker": "Yes" if row["has_blocker"] else "",
            }
            for row in rows
        ],
        use_container_width=True,
        hide_index=True,
    )


def _render_today(user, target, store, account_store):
    plan_date = social_media.sydney_today()
    try:
        snapshot = store.get_daily_snapshot(
            user,
            target_user_id=target["id"],
            plan_date=plan_date,
            account_store=account_store,
        )
    except Exception:
        st.warning("Today's social plan could not load right now.")
        return
    st.subheader("Today")
    _metric_cards(snapshot["summary"])
    _render_team_today(user, store, account_store, plan_date)
    plan, priorities = _plan_defaults(snapshot)
    completed = plan.get("status") == "completed"
    if completed:
        st.success("This social day is complete.")
        if st.button(
            "Reopen day",
            key=f"social-reopen-day::{target['id']}::{plan_date}",
            use_container_width=False,
        ):
            key = social_media_store.request_key(
                "reopen",
                user.get("id"),
                f"{target['id']}:{plan_date}:{plan.get('updated_at')}",
                {},
            )
            try:
                result = store.reopen_daily_plan(
                    user,
                    target_user_id=target["id"],
                    plan_date=plan_date,
                    request_key_value=key,
                    account_store=account_store,
                )
            except Exception:
                _set_notice(False, "The completed day could not be reopened.")
            else:
                _record_activity(result)
                _set_notice(True, "Social day reopened.")
            st.rerun()

    with st.form(
        f"social-daily-plan::{target['id']}::{plan_date}",
        clear_on_submit=False,
    ):
        st.markdown("#### Today's focus")
        focus_areas = st.multiselect(
            "Focus",
            social_media.FOCUS_OPTIONS,
            default=plan.get("focus_areas") or [],
            disabled=completed,
        )
        st.markdown("#### Most Important Priorities")
        priority_values = []
        labels = ("Top priority", "Priority 2", "Priority 3")
        for index, label in enumerate(labels, start=1):
            row = priorities.get(index, {})
            columns = st.columns([5, 1])
            task = columns[0].text_input(
                label,
                value=row.get("task") or "",
                max_chars=240,
                disabled=completed,
                key=f"social-priority-task::{target['id']}::{plan_date}::{index}",
            )
            done = columns[1].checkbox(
                "Done",
                value=bool(row.get("completed")),
                disabled=completed or not bool(task.strip()),
                key=f"social-priority-done::{target['id']}::{plan_date}::{index}",
            )
            priority_values.append({"task": task, "completed": done})

        st.markdown("#### Content plan")
        content_plan = st.text_area(
            "What are we creating or posting today?",
            value=plan.get("content_plan") or "",
            height=100,
            disabled=completed,
        )
        planned_platforms = st.multiselect(
            "Which platforms are planned?",
            social_media.PLATFORMS,
            default=plan.get("planned_platforms") or [],
            disabled=completed,
        )
        plan_columns = st.columns([1, 2])
        planned_post_count = plan_columns[0].number_input(
            "How many posts are planned?",
            min_value=0,
            value=plan.get("planned_post_count"),
            step=1,
            disabled=completed,
        )
        improvement_test = plan_columns[1].text_input(
            "What are we testing or improving today?",
            value=plan.get("improvement_test") or "",
            max_chars=1500,
            disabled=completed,
        )

        st.markdown("#### End-of-day review")
        review_columns = st.columns(2)
        what_worked = review_columns[0].text_area(
            "What worked today?",
            value=plan.get("what_worked") or "",
            height=90,
            disabled=completed,
        )
        what_learned = review_columns[1].text_area(
            "What did we learn?",
            value=plan.get("what_learned") or "",
            height=90,
            disabled=completed,
        )
        improve_next = review_columns[0].text_area(
            "What should we improve next?",
            value=plan.get("improve_next") or "",
            height=90,
            disabled=completed,
        )
        blockers = review_columns[1].text_area(
            "Any blockers or help needed?",
            value=plan.get("blockers") or "",
            height=90,
            disabled=completed,
        )
        action_columns = st.columns(2)
        save_clicked = action_columns[0].form_submit_button(
            "Update plan" if plan else "Save today's plan",
            use_container_width=True,
            disabled=completed,
        )
        complete_clicked = action_columns[1].form_submit_button(
            "Complete day",
            type="primary",
            use_container_width=True,
            disabled=completed,
        )

    payload = {
        "plan_date": plan_date,
        "focus_areas": focus_areas,
        "priorities": priority_values,
        "content_plan": content_plan,
        "planned_platforms": planned_platforms,
        "planned_post_count": planned_post_count,
        "improvement_test": improvement_test,
        "what_worked": what_worked,
        "what_learned": what_learned,
        "improve_next": improve_next,
        "blockers": blockers,
    }
    preview_score = social_media.calculate_daily_score(
        priority_values,
        payload,
    )
    with st.expander("How the score works", expanded=False):
        st.caption(
            f"Current score: {preview_score:.1f}/10. Up to 8 points come from completed "
            "priorities, with the Top priority worth twice each secondary priority. "
            "Each completed review answer adds 0.5 points. Platforms and post volume do not add points."
        )
    if not (save_clicked or complete_clicked):
        return
    action = "complete" if complete_clicked else "save"
    key = social_media_store.request_key(
        f"daily-{action}",
        user.get("id"),
        f"{target['id']}:{plan_date}:{plan.get('updated_at')}",
        payload,
    )
    try:
        result = store.save_daily_plan(
            user,
            target_user_id=target["id"],
            payload=payload,
            completing=bool(complete_clicked),
            request_key_value=key,
            account_store=account_store,
        )
    except social_media.SocialValidationError as error:
        st.warning(str(error))
        return
    except Exception:
        _set_notice(False, "Today's social plan could not be saved.")
    else:
        _record_activity(result)
        _set_notice(
            True,
            "Social day completed." if complete_clicked else "Today's social plan saved.",
        )
    st.rerun()


def _platform_map(post):
    return {
        row.get("platform"): dict(row or {})
        for row in (post or {}).get("platforms") or []
    }


def _local_datetime(value, timezone_name):
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)


def _render_post_rows(posts):
    if not posts:
        st.caption("No posts have been logged yet.")
        return
    for post in posts:
        platforms = post.get("platforms") or []
        live = [row["platform"] for row in platforms if row.get("status") == "Live"]
        status_text = ", ".join(
            f"{row.get('platform')}: {row.get('status')}"
            for row in platforms
        )
        st.markdown(
            f"""
            <div class="sc-social-post-row">
                <div class="sc-social-post-title">{html.escape(post.get("content_name") or "")}</div>
                <div class="sc-social-post-meta">
                    {html.escape(post.get("content_format") or "")}
                    &nbsp;|&nbsp; {html.escape(str(post.get("created_date") or ""))}
                    &nbsp;|&nbsp; {html.escape(status_text)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for row in platforms:
            url = row.get("public_url") or ""
            if row.get("status") == "Live" and url:
                st.markdown(
                    f'<a class="sc-social-live-link" href="{html.escape(url, quote=True)}" '
                    f'target="_blank" rel="noopener noreferrer">'
                    f'Open {html.escape(row.get("platform") or "post")} post</a>',
                    unsafe_allow_html=True,
                )
        if live:
            st.caption(f"Live on {', '.join(live)}")


def _render_post_tracker(user, target, store, account_store):
    st.subheader("Post Tracker")
    try:
        posts = store.list_posts(
            user,
            target_user_id=target["id"],
            limit=20,
            account_store=account_store,
        )
    except Exception:
        st.warning("Posts could not load right now.")
        return
    mode = st.segmented_control(
        "Post action",
        ("Add post", "Edit post"),
        default="Add post",
        key="social-post-action",
        label_visibility="collapsed",
    )
    editing = mode == "Edit post" and bool(posts)
    selected_post = {}
    if editing:
        by_id = {post["id"]: post for post in posts}
        selected_id = st.selectbox(
            "Post to edit",
            tuple(by_id),
            format_func=lambda post_id: by_id[post_id]["content_name"],
            key="social-post-edit-select",
        )
        selected_post = by_id[selected_id]
    elif mode == "Edit post":
        st.caption("There are no posts to edit yet.")

    platform_defaults = list(_platform_map(selected_post))
    selected_platforms = st.multiselect(
        "Platforms",
        social_media.PLATFORMS,
        default=platform_defaults,
        key=f"social-post-platforms::{selected_post.get('id') or 'new'}",
    )
    platform_defaults_by_name = _platform_map(selected_post)
    with st.form(
        f"social-post-form::{selected_post.get('id') or 'new'}",
        clear_on_submit=False,
    ):
        main_columns = st.columns(2)
        content_name = main_columns[0].text_input(
            "Post or content name",
            value=selected_post.get("content_name") or "",
            max_chars=240,
        )
        campaign = main_columns[1].text_input(
            "Product, artwork or campaign",
            value=selected_post.get("campaign") or "",
            max_chars=240,
        )
        content_format = main_columns[0].selectbox(
            "Content format",
            social_media.CONTENT_FORMATS,
            index=(
                social_media.CONTENT_FORMATS.index(selected_post.get("content_format"))
                if selected_post.get("content_format") in social_media.CONTENT_FORMATS
                else 0
            ),
        )
        market = main_columns[1].selectbox(
            "Market",
            social_media.MARKETS,
            index=(
                social_media.MARKETS.index(selected_post.get("market"))
                if selected_post.get("market") in social_media.MARKETS
                else social_media.MARKETS.index("Global")
            ),
        )
        created_date = main_columns[0].date_input(
            "Created date",
            value=selected_post.get("created_date") or social_media.sydney_today(),
        )
        notes = st.text_area(
            "Notes",
            value=selected_post.get("notes") or "",
            height=80,
        )
        platform_rows = {}
        for platform in selected_platforms:
            existing = platform_defaults_by_name.get(platform, {})
            st.markdown(f"**{platform}**")
            platform_columns = st.columns([1, 1.25, 2])
            status = platform_columns[0].selectbox(
                f"{platform} status",
                social_media.POST_STATUSES,
                index=(
                    social_media.POST_STATUSES.index(existing.get("status"))
                    if existing.get("status") in social_media.POST_STATUSES
                    else 0
                ),
                key=f"social-post-status::{selected_post.get('id') or 'new'}::{platform}",
            )
            scheduled_at = platform_columns[1].datetime_input(
                f"{platform} scheduled or published time",
                value=_local_datetime(existing.get("scheduled_published_at"), target["timezone"]),
                key=f"social-post-time::{selected_post.get('id') or 'new'}::{platform}",
            )
            public_url = platform_columns[2].text_input(
                f"{platform} public post URL",
                value=existing.get("public_url") or "",
                placeholder="Recommended when Live",
                key=f"social-post-url::{selected_post.get('id') or 'new'}::{platform}",
            )
            platform_rows[platform] = {
                "status": status,
                "scheduled_published_at": scheduled_at,
                "public_url": public_url,
            }
        with st.expander("Optional post results", expanded=False):
            for platform in selected_platforms:
                existing = platform_defaults_by_name.get(platform, {})
                st.caption(platform)
                metric_columns = st.columns(4)
                platform_rows[platform].update(
                    {
                        "reach_views": metric_columns[0].number_input(
                            "Reach / views",
                            min_value=0,
                            value=existing.get("reach_views"),
                            step=1,
                            key=f"social-post-reach::{selected_post.get('id') or 'new'}::{platform}",
                        ),
                        "engagements": metric_columns[1].number_input(
                            "Engagements",
                            min_value=0,
                            value=existing.get("engagements"),
                            step=1,
                            key=f"social-post-engagements::{selected_post.get('id') or 'new'}::{platform}",
                        ),
                        "link_clicks": metric_columns[2].number_input(
                            "Link clicks",
                            min_value=0,
                            value=existing.get("link_clicks"),
                            step=1,
                            key=f"social-post-clicks::{selected_post.get('id') or 'new'}::{platform}",
                        ),
                        "saves_shares": metric_columns[3].number_input(
                            "Saves / shares",
                            min_value=0,
                            value=existing.get("saves_shares"),
                            step=1,
                            key=f"social-post-saves::{selected_post.get('id') or 'new'}::{platform}",
                        ),
                        "result_note": st.text_input(
                            f"{platform} result or learning",
                            value=existing.get("result_note") or "",
                            key=f"social-post-result::{selected_post.get('id') or 'new'}::{platform}",
                        ),
                    }
                )
        submitted = st.form_submit_button(
            "Update post" if selected_post else "Save post",
            type="primary",
            use_container_width=True,
        )
    if submitted:
        payload = {
            "content_name": content_name,
            "campaign": campaign,
            "content_format": content_format,
            "market": market,
            "created_date": created_date,
            "notes": notes,
            "platforms": platform_rows,
        }
        key = social_media_store.request_key(
            "post-update" if selected_post else "post-create",
            user.get("id"),
            (
                f"{target['id']}:{selected_post.get('id') or created_date}:"
                f"{selected_post.get('updated_at') or ''}"
            ),
            payload,
        )
        try:
            result = store.save_post(
                user,
                target_user_id=target["id"],
                post_id=selected_post.get("id") or "",
                payload=payload,
                request_key_value=key,
                account_store=account_store,
            )
        except social_media.SocialValidationError as error:
            st.warning(str(error))
            return
        except Exception:
            _set_notice(False, "The post could not be saved.")
        else:
            _record_activity(result)
            _set_notice(True, "Post updated." if selected_post else "Post saved.")
        st.rerun()
    st.markdown("#### Recent posts")
    _render_post_rows(posts)


def _weekly_metric_rows(snapshot):
    by_platform = {
        row.get("platform"): row
        for row in snapshot.get("platform_metrics") or []
    }
    return [
        {
            "Platform": platform,
            "Audience total": by_platform.get(platform, {}).get("audience_total"),
            "Reach / views": by_platform.get(platform, {}).get("reach_views"),
            "Engagements": by_platform.get(platform, {}).get("engagements"),
            "Outbound clicks": by_platform.get(platform, {}).get("outbound_clicks"),
            "Posts published": by_platform.get(platform, {}).get("posts_published"),
            "Best post URL": by_platform.get(platform, {}).get("best_post_url") or "",
            "Best post result": by_platform.get(platform, {}).get("best_post_result") or "",
        }
        for platform in social_media.PLATFORMS
    ]


def _weekly_payload_from_editor(editor, performed_best, learned, test_next, week_start):
    rows = editor.to_dict("records") if hasattr(editor, "to_dict") else list(editor or [])
    return {
        "week_start": week_start,
        "performed_best": performed_best,
        "learned": learned,
        "test_next": test_next,
        "platform_metrics": {
            row["Platform"]: {
                "audience_total": row.get("Audience total"),
                "reach_views": row.get("Reach / views"),
                "engagements": row.get("Engagements"),
                "outbound_clicks": row.get("Outbound clicks"),
                "posts_published": row.get("Posts published"),
                "best_post_url": row.get("Best post URL"),
                "best_post_result": row.get("Best post result"),
            }
            for row in rows
        },
    }


def _render_weekly_summary(snapshot):
    report = snapshot.get("report") or {}
    if report.get("status") != "submitted":
        return
    summary = report.get("summary") or {}
    st.success("Weekly check-in submitted.")
    columns = st.columns(4)
    columns[0].metric("Posts published", summary.get("total_posts", 0))
    columns[1].metric("Audience growth", summary.get("total_audience_growth", 0))
    columns[2].metric(
        "Average score",
        (
            f"{float(summary['average_execution_score']):.1f}"
            if summary.get("average_execution_score") is not None
            else "No days"
        ),
    )
    columns[3].metric("MIPs completed", summary.get("mips_completed", 0))
    if summary.get("strongest_platform"):
        st.caption(f"Strongest platform: {summary['strongest_platform']}")
    comparisons = summary.get("comparisons") or []
    if comparisons:
        st.dataframe(
            [
                {
                    "Platform": row["platform"],
                    "Audience": row.get("audience_total"),
                    "Change": row.get("audience_change"),
                    "Reach / views": row.get("reach_views"),
                    "Reach change": row.get("reach_views_change"),
                    "Engagements": row.get("engagements"),
                    "Engagement change": row.get("engagements_change"),
                }
                for row in comparisons
            ],
            use_container_width=True,
            hide_index=True,
        )


def _render_weekly(user, target, store, account_store):
    week_start, week_end = social_media.sydney_week_bounds()
    try:
        snapshot = store.get_weekly_snapshot(
            user,
            target_user_id=target["id"],
            week_start=week_start,
            account_store=account_store,
        )
    except Exception:
        st.warning("This week's check-in could not load right now.")
        return
    st.subheader("Weekly Check-In")
    st.caption(
        f"Australia/Sydney week: {week_start.strftime('%d %b')} to {week_end.strftime('%d %b %Y')}"
    )
    _render_weekly_summary(snapshot)
    report = snapshot.get("report") or {}
    with st.form(f"social-weekly::{target['id']}::{week_start}"):
        editor = st.data_editor(
            _weekly_metric_rows(snapshot),
            hide_index=True,
            use_container_width=True,
            disabled=["Platform"],
            num_rows="fixed",
            column_config={
                "Platform": st.column_config.TextColumn("Platform"),
                "Audience total": st.column_config.NumberColumn(
                    "Audience total",
                    min_value=0,
                    step=1,
                ),
                "Reach / views": st.column_config.NumberColumn(
                    "Reach / views",
                    min_value=0,
                    step=1,
                ),
                "Engagements": st.column_config.NumberColumn(
                    "Engagements",
                    min_value=0,
                    step=1,
                ),
                "Outbound clicks": st.column_config.NumberColumn(
                    "Outbound clicks",
                    min_value=0,
                    step=1,
                ),
                "Posts published": st.column_config.NumberColumn(
                    "Posts published",
                    min_value=0,
                    step=1,
                ),
            },
            key=f"social-weekly-metrics::{target['id']}::{week_start}",
        )
        question_columns = st.columns(3)
        performed_best = question_columns[0].text_area(
            "What performed best this week?",
            value=report.get("performed_best") or "",
            height=110,
        )
        learned = question_columns[1].text_area(
            "What did we learn?",
            value=report.get("learned") or "",
            height=110,
        )
        test_next = question_columns[2].text_area(
            "What will we test next week?",
            value=report.get("test_next") or "",
            height=110,
        )
        action_columns = st.columns(2)
        draft_clicked = action_columns[0].form_submit_button(
            "Save draft",
            use_container_width=True,
        )
        submit_clicked = action_columns[1].form_submit_button(
            "Submit weekly check-in",
            type="primary",
            use_container_width=True,
        )
    if not (draft_clicked or submit_clicked):
        return
    payload = _weekly_payload_from_editor(
        editor,
        performed_best,
        learned,
        test_next,
        week_start,
    )
    key = social_media_store.request_key(
        "weekly-submit" if submit_clicked else "weekly-draft",
        user.get("id"),
        f"{target['id']}:{week_start}:{report.get('updated_at') or ''}",
        payload,
    )
    try:
        result = store.save_weekly_report(
            user,
            target_user_id=target["id"],
            payload=payload,
            submitting=bool(submit_clicked),
            request_key_value=key,
            account_store=account_store,
        )
    except social_media.SocialValidationError as error:
        st.warning(str(error))
        return
    except Exception:
        _set_notice(False, "The weekly check-in could not be saved.")
    else:
        _record_activity(result)
        _set_notice(
            True,
            "Weekly check-in submitted." if submit_clicked else "Weekly draft saved.",
        )
    st.rerun()


def _render_history(user, target, store, account_store):
    st.subheader("History")
    today = social_media.sydney_today()
    filter_columns = st.columns([1, 1, 1, 1, 1, 0.7])
    start_date = filter_columns[0].date_input(
        "From",
        value=today - timedelta(days=14),
        key="social-history-from",
    )
    end_date = filter_columns[1].date_input(
        "To",
        value=today,
        key="social-history-to",
    )
    platform = filter_columns[2].selectbox(
        "Platform",
        ("All",) + social_media.PLATFORMS,
        key="social-history-platform",
    )
    content_format = filter_columns[3].selectbox(
        "Format",
        ("All",) + social_media.CONTENT_FORMATS,
        key="social-history-format",
    )
    status = filter_columns[4].selectbox(
        "Status",
        ("All",) + social_media.POST_STATUSES,
        key="social-history-status",
    )
    page = filter_columns[5].number_input(
        "Page",
        min_value=1,
        value=1,
        step=1,
        key="social-history-page",
    )
    try:
        history = store.list_history(
            user,
            target_user_id=target["id"],
            start_date=start_date,
            end_date=end_date,
            platform="" if platform == "All" else platform,
            content_format="" if content_format == "All" else content_format,
            status="" if status == "All" else status,
            limit=HISTORY_PAGE_SIZE,
            offset=(int(page) - 1) * HISTORY_PAGE_SIZE,
            account_store=account_store,
        )
    except Exception:
        st.warning("Social Media history could not load right now.")
        return
    st.markdown("#### Recent daily plans")
    plans = history["daily_plans"]
    if plans:
        st.dataframe(
            [
                {
                    "Date": row.get("plan_date"),
                    "Status": str(row.get("status") or "").title(),
                    "Score": float(row.get("execution_score") or 0),
                    "Blocker": "Yes" if row.get("blockers") else "",
                }
                for row in plans
            ],
            use_container_width=True,
            hide_index=True,
        )
        by_date = {str(row["plan_date"]): row for row in plans}
        open_date = st.selectbox(
            "Open day",
            tuple(by_date),
            key="social-history-open-day",
        )
        try:
            day = store.get_daily_snapshot(
                user,
                target_user_id=target["id"],
                plan_date=open_date,
                account_store=account_store,
            )
        except Exception:
            day = {}
        if day:
            with st.container(border=True):
                plan = day.get("plan") or {}
                st.markdown(f"**{open_date} social plan**")
                st.write(plan.get("content_plan") or "No content plan recorded.")
                for priority in day.get("priorities") or []:
                    marker = "Complete" if priority["completed"] else "Outstanding"
                    st.write(f"- {priority['task']} ({marker})")
                st.caption(
                    f"{day['summary']['posts_live']} posts live | "
                    f"{', '.join(day['summary']['platforms_used']) or 'No platforms live'} | "
                    f"Score {day['summary']['score']:.1f}/10"
                )
                if plan.get("what_learned"):
                    st.write(f"Learning: {plan['what_learned']}")
    else:
        st.caption("No daily plans match these filters.")

    st.markdown("#### Recent posts")
    _render_post_rows(history["posts"])
    st.markdown("#### Weekly check-ins")
    weekly = history["weekly_reports"]
    if weekly:
        st.dataframe(
            [
                {
                    "Week": f"{row.get('week_start')} to {row.get('week_end')}",
                    "Status": str(row.get("status") or "").title(),
                    "Average score": row.get("average_execution_score"),
                    "MIPs": row.get("mips_completed") or 0,
                }
                for row in weekly
            ],
            use_container_width=True,
            hide_index=True,
        )
        by_week = {str(row["week_start"]): row for row in weekly}
        open_week = st.selectbox(
            "Open week",
            tuple(by_week),
            key="social-history-open-week",
        )
        try:
            week = store.get_weekly_snapshot(
                user,
                target_user_id=target["id"],
                week_start=open_week,
                account_store=account_store,
            )
        except Exception:
            week = {}
        if week:
            _render_weekly_summary(week)
    else:
        st.caption("No weekly check-ins match these filters.")


def render_page(user, *, store=social_media_store, account_store=None):
    if not os_accounts.can_access_page(user, social_media.SOCIAL_MEDIA_ROUTE):
        st.title("Access not approved")
        st.caption("This page is not available for your account.")
        return
    _inject_styles()
    st.markdown(
        """
        <div class="sc-social-header">
            <h1>Sports Cave Social Media</h1>
            <p>Plan today's content, track what goes live and learn what performs.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _profile_shortcuts()
    _show_result_notice()
    try:
        storage = store.schema_status()
    except Exception:
        storage = {"ready": False, "reason": "storage_unavailable"}
    if not storage.get("ready"):
        if os_accounts.is_admin(user):
            st.warning(
                "Social Media storage could not be prepared right now. "
                "Retry once; if it continues, the app's storage setup needs attention."
            )
        else:
            st.warning(
                "Social Media is temporarily unavailable. Your existing work is safe."
            )
        if st.button("Retry", key="social-media-storage-retry"):
            try:
                storage = store.schema_status(force=True)
            except Exception:
                storage = {"ready": False, "reason": "storage_unavailable"}
            if storage.get("ready"):
                st.rerun()
        return
    try:
        staff = store.authorised_social_staff(
            user,
            account_store=account_store,
        )
    except Exception:
        st.warning("Social Media access could not be loaded right now.")
        return
    target = _admin_staff_selector(user, staff)
    view = st.segmented_control(
        "Social Media view",
        ("Today", "Post Tracker", "Weekly Check-In", "History"),
        default="Today",
        key="social-media-view",
        label_visibility="collapsed",
    )
    if view == "Post Tracker":
        _render_post_tracker(user, target, store, account_store)
    elif view == "Weekly Check-In":
        _render_weekly(user, target, store, account_store)
    elif view == "History":
        _render_history(user, target, store, account_store)
    else:
        _render_today(user, target, store, account_store)
