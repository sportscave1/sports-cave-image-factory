"""Private publishing route used by the existing Morning Brief desktop handoff."""

from html import escape
import json
from urllib.parse import parse_qs

from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse

from files_upload_api import FilesUploadError, _request_user, _same_origin
from home_brief_calendar import MARKETS, iso_day, matches_market
import home_meta_morning_brief as meta
from home_morning_brief_actions import article_html
from home_sports_morning_brief import LOG, MAX_PAYLOAD, SETTING_KEY, archive_page, get_app_setting, parse_edition, publish
from sports_categories import CANONICAL_SPORT_CATEGORIES
import os_accounts
from sports_sales_calendar import sydney_date

PATH = "/ops/morning-brief/publish"
HEADERS = {
    "Cache-Control": "private, no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
}


def _page(message="", status=200, *, form=False, meta_brief=False):
    path = meta.PATH if meta_brief else PATH
    title = "Meta Morning Brief" if meta_brief else "Morning Brief"
    limit = meta.MAX_PAYLOAD if meta_brief else MAX_PAYLOAD
    instructions = (
        "Include date, coverage, summary, metrics and recommendations."
        if meta_brief else
        "Use the Sydney edition date and recommendations with title, recommendation, links, sport, "
        "markets, and confirmed start_date and end_date when available. Include the complete edition as full_brief."
    )
    body = f"<p>{escape(message)}</p>" if message else ""
    if form:
        body += (
            f'<form method="post" action="{path}">'
            f'<label for="brief">{title} JSON</label><br><p>{instructions}</p>'
            f'<textarea id="brief" name="brief" maxlength="{limit}" '
            'rows="14" cols="72" required></textarea><br>'
            '<button>Publish brief</button></form>'
        )
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        f'<title>{title} publishing</title>'
        f'<main><h1>{title} publishing</h1>{body}'
        '<p><a href="/?page=dashboard">Sports Cave OS Home</a></p></main>',
        status_code=status,
        headers=HEADERS,
    )


async def publication(request):
    meta_brief = request.url.path == meta.PATH
    title = "Meta Morning Brief" if meta_brief else "Morning Brief"
    limit = meta.MAX_PAYLOAD if meta_brief else MAX_PAYLOAD
    permitted = meta.can_view if meta_brief else os_accounts.is_reporting_owner
    publisher = meta.publish if meta_brief else publish

    def page(message="", status=200, *, form=False):
        return _page(message, status, form=form, meta_brief=meta_brief)

    if request.method == "POST" and (not request.headers.get("origin") or not _same_origin(request)):
        return page("Invalid request origin.", 403)
    try:
        user = await run_in_threadpool(_request_user, request, required_page="dashboard")
    except FilesUploadError:
        user = None
    if not permitted(user):
        return page("Sign in to Sports Cave OS as the owner with the required access.", 403)
    if request.method != "POST":
        return page(form=True)
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/x-www-form-urlencoded":
        return page("Expected a publication form.", 415)

    encoded = bytearray()
    async for chunk in request.stream():
        if len(encoded) + len(chunk) > limit * 12 + 6:
            return page("The brief is too long.", 413, form=True)
        encoded.extend(chunk)
    try:
        fields = parse_qs(encoded.decode("ascii"), strict_parsing=True, max_num_fields=1, errors="strict")
        raw = fields["brief"][0]
    except (KeyError, ValueError):
        return page("Invalid publication form.", 400, form=True)
    try:
        edition = await run_in_threadpool(publisher, raw, user)
    except ValueError as error:
        return page(str(error), 400, form=True)
    except Exception as error:
        LOG.warning("home_morning_brief_publish_failed type=%s", type(error).__name__)
        return page(f"The {title} could not be published. Try again.", 503, form=True)
    return page(f"Published the {edition['date']} {title}.")


async def history(request):
    try:
        user = await run_in_threadpool(_request_user, request, required_page="dashboard")
    except FilesUploadError:
        user = None
    if not os_accounts.is_reporting_owner(user):
        return JSONResponse({"error": "owner_required"}, status_code=403, headers=HEADERS)
    sport = request.query_params.get("sport")
    market = request.query_params.get("market")
    before = request.query_params.get("before")
    if sport not in CANONICAL_SPORT_CATEGORIES or market not in MARKETS:
        return JSONResponse({"error": "invalid_market_or_sport"}, status_code=400, headers=HEADERS)
    if before is not None:
        try:
            before = iso_day(before).isoformat()
        except ValueError:
            return JSONResponse({"error": "invalid_date"}, status_code=400, headers=HEADERS)
    today = sydney_date()
    try:
        entries, next_page = await run_in_threadpool(archive_page, today, before=before)
        if before is None:
            latest = await run_in_threadpool(get_app_setting, SETTING_KEY, ensure_schema_first=False)
            if latest and all(latest["date"] != entry["date"] for entry in entries):
                entries.insert(0, parse_edition(json.dumps(latest, ensure_ascii=False), today))
    except Exception as error:
        LOG.warning("home_brief_history_failed type=%s", type(error).__name__)
        return JSONResponse({"error": "history_unavailable"}, status_code=503, headers=HEADERS)
    allow_ads = os_accounts.can_access_page(user, "ads")
    html = []
    for entry in entries:
        articles = [article_html(item, allow_ads=allow_ads) for item in entry["recommendations"]
                    if item["sport"] == sport and matches_market(item, market)]
        if articles:
            label = iso_day(entry["date"]).strftime("%d %B %Y").lstrip("0")
            html.append(f'<section><h4>{label}</h4>{"".join(articles)}</section>')
    return JSONResponse({"html": "".join(html), "before": next_page}, headers=HEADERS)


ROUTES = [(PATH, publication, ("GET", "POST")),
          (meta.PATH, publication, ("GET", "POST")),
          ("/ops/morning-brief/history", history, ("GET",))]
