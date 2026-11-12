"""Owner-authorized, read-only CRM tools for the private ChatGPT connector."""

import base64
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import threading
import time
from urllib.parse import parse_qsl, urlencode

from cryptography.fernet import Fernet, InvalidToken
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

import os_accounts
from chatgpt_crm_api import HEADERS, _campaign_summary
from files_upload_api import FilesUploadError, _request_user
from chatgpt_reporting import meta_daily, orders_daily, reporting_day

ISSUER = "https://sports-cave-image-factory.onrender.com"
MCP_PATH = "/api/chatgpt/crm/mcp"
RESOURCE = ISSUER + MCP_PATH
RESOURCE_METADATA = "/.well-known/oauth-protected-resource" + MCP_PATH
SERVER_METADATA = "/.well-known/oauth-authorization-server"
AUTH_PATH = "/api/chatgpt/crm/oauth/authorize"
TOKEN_PATH = "/api/chatgpt/crm/oauth/token"
REGISTRATION_PATH = "/api/chatgpt/crm/oauth/register"
SCOPE = "crm:summary"
TOOL = "get_crm_campaign_summary"
ORDERS_SCOPE = "orders:summary"
META_SCOPE = "meta:summary"
SCOPES = (SCOPE, ORDERS_SCOPE, META_SCOPE)
SCOPE_LIST = " ".join(SCOPES)
TOOLS = {
    TOOL: (SCOPE, "crm_campaigns_manage", "Get CRM campaign summary",
           "Read current CRM campaign counts and delivery activity.", False),
    "get_orders_daily_summary": (ORDERS_SCOPE, "orders", "Get daily Orders summary",
                                 "Read aggregate Shopify order counts and known totals by currency for a Sydney date.", True),
    "get_meta_daily_summary": (META_SCOPE, "ads_meta_review", "Get daily Meta reporting summary",
                               "Read saved ad-level Meta spend, attributed purchases and coverage for a Sydney date.", True),
}
REDIRECT = re.compile(
    r"https://chatgpt\.com/(?:connector_platform_oauth_redirect|connector/oauth/[A-Za-z0-9_-]{1,128})"
)
PKCE = re.compile(r"[A-Za-z0-9_-]{43}")
VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}")
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26")
ACCESS_SECONDS = 8 * 3600
CODE_SECONDS = 120
LOG = logging.getLogger(__name__)
_codes = {}
_code_lock = threading.Lock()


def _key():
    key = os.getenv("SPORTS_CAVE_CHATGPT_CRM_MCP_SECRET", "").strip()
    return key.encode("ascii") if re.fullmatch(r"[A-Za-z0-9_-]{43,128}", key) else b""


def mcp_home_url():
    if not _key():
        return ""
    url = os.getenv("SPORTS_CAVE_CHATGPT_CRM_MCP_URL", "").strip()
    if re.fullmatch(r"https://chatgpt\.com/plugins/[A-Za-z0-9_-]{1,180}", url):
        return url
    return "https://chatgpt.com/plugins"


def _response(data, status=200, extra=None):
    return JSONResponse(data, status_code=status, headers={**HEADERS, **(extra or {})})


def _tag(key, purpose, text):
    return hmac.new(key, (purpose + "\0" + text).encode(), hashlib.sha256).hexdigest()


def _seal(key, purpose, data):
    cipher = Fernet(base64.urlsafe_b64encode(bytes.fromhex(_tag(key, purpose, RESOURCE))))
    return cipher.encrypt(json.dumps(data, separators=(",", ":")).encode()).decode()


def _unseal(key, purpose, data, ttl):
    cipher = Fernet(base64.urlsafe_b64encode(bytes.fromhex(_tag(key, purpose, RESOURCE))))
    return json.loads(cipher.decrypt(data.encode(), ttl=ttl))


def _owner(user):
    return os_accounts.is_reporting_owner(user) and os_accounts.can_access_page(user, "crm_campaigns_manage")


def _owner_session(request):
    user = _request_user(request, required_page="crm_campaigns_manage")
    return user if _owner(user) else None


def _active_owner(claims, page):
    user = os_accounts.DEFAULT_STORE.get_user(claims["sub"])
    return (_owner(user) and os_accounts.can_access_page(user, page)
            and str(user.get("session_version") or 1) == claims["version"])


async def _read_body(request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384:
            raise ValueError("body too large")
    return bytes(body)


def _parameters(items):
    values = {}
    for key, value in items:
        if key in values or len(key) > 100 or len(value) > 8192:
            raise ValueError("invalid parameters")
        values[key] = value
    return values


async def _form(request):
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise ValueError("form content type required")
    return _parameters(parse_qsl((await _read_body(request)).decode(), max_num_fields=24))


async def protected_resource(_request):
    if not _key():
        return _response({"error": "not_found"}, 404)
    return _response({
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": list(SCOPES),
        "bearer_methods_supported": ["header"],
    })


async def authorization_server(_request):
    if not _key():
        return _response({"error": "not_found"}, 404)
    return _response({
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + AUTH_PATH,
        "token_endpoint": ISSUER + TOKEN_PATH,
        "registration_endpoint": ISSUER + REGISTRATION_PATH,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": list(SCOPES),
        "code_challenge_methods_supported": ["S256"],
        "authorization_response_iss_parameter_supported": True,
    })


async def register(request):
    key = _key()
    if not key:
        return _response({"error": "not_found"}, 404)
    try:
        data = json.loads(await _read_body(request))
        redirects = data.get("redirect_uris") if isinstance(data, dict) else None
        if (not isinstance(redirects, list) or len(redirects) != 1
                or not isinstance(redirects[0], str) or not REDIRECT.fullmatch(redirects[0])):
            return _response({"error": "invalid_redirect_uri"}, 400)
    except (ValueError, UnicodeError):
        return _response({"error": "invalid_client_metadata"}, 400)
    return _response({
        "client_id": _tag(key, "client", redirects[0]),
        "redirect_uris": redirects,
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "scope": SCOPE_LIST,
    }, 201)


def _authorization_values(key, values):
    redirect = values.get("redirect_uri", "")
    requested = set(values.get("scope", SCOPE_LIST).split())
    if (not REDIRECT.fullmatch(redirect)
            or not hmac.compare_digest(values.get("client_id", "").encode(), _tag(key, "client", redirect).encode())
            or values.get("response_type") != "code"
            or values.get("resource", RESOURCE) != RESOURCE
            or not requested or not requested.issubset(SCOPES)
            or values.get("code_challenge_method") != "S256"
            or not PKCE.fullmatch(values.get("code_challenge", ""))
            or not 1 <= len(values.get("state", "")) <= 1024):
        raise ValueError("invalid authorization request")
    return {**{field: values[field] for field in ("redirect_uri", "client_id", "code_challenge", "state")},
            "scope": " ".join(scope for scope in SCOPES if scope in requested)}


def _page(markup, status=200):
    return HTMLResponse(
        "<!doctype html><html lang=en><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Sports Cave CRM</title><main>" + markup + "</main></html>",
        status_code=status,
        headers={**HEADERS, "Referrer-Policy": "same-origin", "X-Frame-Options": "DENY",
                 "Content-Security-Policy": (
                     "default-src 'none'; frame-ancestors 'none'; form-action 'self' "
                     "https://chatgpt.com/connector_platform_oauth_redirect https://chatgpt.com/connector/oauth/"
                 )},
    )


async def authorize(request):
    key = _key()
    if not key:
        return _response({"error": "not_found"}, 404)
    try:
        owner = await run_in_threadpool(_owner_session, request)
    except FilesUploadError:
        owner = None
    if not owner:
        return _page(
            "<h1>Sports Cave OS owner sign-in required</h1>"
            "<p><a href='/' target='_blank' rel='noopener'>Open Sports Cave OS</a>, sign in, then retry in ChatGPT.</p>",
            403,
        )
    identity = {"sub": str(owner["id"]), "version": str(owner.get("session_version") or 1)}
    try:
        if request.method == "GET":
            values = _authorization_values(key, _parameters(request.query_params.multi_items()))
            allowed = {scope for scope, page, *_ in TOOLS.values() if os_accounts.can_access_page(owner, page)}
            if not set(values["scope"].split()).issubset(allowed):
                return _page("<h1>Sports Cave OS reporting permission required</h1>", 403)
            consent = html.escape(_seal(key, "consent", {**values, **identity}), quote=True)
            labels = {SCOPE: "CRM campaign counts and delivery status", ORDERS_SCOPE: "daily Orders totals",
                      META_SCOPE: "saved daily Meta reporting"}
            summary = ", ".join(labels[scope] for scope in values["scope"].split())
            return _page(
                "<h1>Connect Sports Cave CRM to ChatGPT</h1>"
                f"<p>Share {html.escape(summary)} with the private ChatGPT connector.</p>"
                f"<form method=post action='{AUTH_PATH}'>"
                f"<input type=hidden name=consent value='{consent}'>"
                "<button type=submit>Allow read-only access</button></form>"
            )
        if request.headers.get("origin") != ISSUER:
            raise ValueError("invalid consent origin")
        values = _unseal(key, "consent", (await _form(request)).get("consent", ""), 300)
        if any(values.get(field) != value for field, value in identity.items()):
            raise ValueError("account changed")
    except (ValueError, InvalidToken, UnicodeError):
        return _page("<h1>Invalid or expired request</h1><p>Retry the connection from ChatGPT.</p>", 400)
    code = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _code_lock:
        for expired in [item for item, (deadline, _) in _codes.items() if deadline <= now]:
            del _codes[expired]
        if len(_codes) >= 256:
            return _response({"error": "temporarily_unavailable"}, 503)
        _codes[code] = (now + CODE_SECONDS, values)
    redirect = values["redirect_uri"] + "?" + urlencode({
        "code": code, "state": values["state"], "iss": ISSUER,
    })
    return RedirectResponse(redirect, status_code=303, headers={**HEADERS, "Referrer-Policy": "no-referrer"})


async def token(request):
    key = _key()
    if not key:
        return _response({"error": "not_found"}, 404)
    try:
        data = await _form(request)
    except (ValueError, UnicodeError):
        return _response({"error": "invalid_request"}, 400)
    if data.get("grant_type") != "authorization_code":
        return _response({"error": "unsupported_grant_type"}, 400)
    verifier = data.get("code_verifier", "")
    if not VERIFIER.fullmatch(verifier) or data.get("resource", RESOURCE) != RESOURCE:
        return _response({"error": "invalid_grant"}, 400)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    code = data.get("code", "")
    with _code_lock:
        entry = _codes.get(code)
        if (not entry or entry[0] <= time.monotonic()
                or not hmac.compare_digest(entry[1]["code_challenge"], challenge)
                or entry[1]["client_id"] != data.get("client_id")
                or entry[1]["redirect_uri"] != data.get("redirect_uri")):
            return _response({"error": "invalid_grant"}, 400)
        claims = _codes.pop(code)[1]
    access = _seal(key, "access", {
        "sub": claims["sub"], "version": claims["version"], "scope": claims["scope"],
        "iss": ISSUER, "aud": RESOURCE,
    })
    return _response({"access_token": access, "token_type": "Bearer", "expires_in": ACCESS_SECONDS, "scope": claims["scope"]})


def _challenge(scope=SCOPE_LIST, status=401):
    return _response(
        {"error": "insufficient_scope" if status == 403 else "unauthorized"}, status,
        {"WWW-Authenticate": f'Bearer resource_metadata="{ISSUER + RESOURCE_METADATA}", scope="{scope}"'},
    )


def _rpc_error(identifier, code, message):
    return _response({"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}})


async def mcp(request):
    key = _key()
    if not key:
        return _response({"error": "not_found"}, 404)
    if request.headers.get("origin") not in (None, "https://chatgpt.com", ISSUER):
        return _response({"error": "invalid_origin"}, 403)
    scheme, _, bearer = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not 1 <= len(bearer) <= 2048:
        return _challenge()
    try:
        claims = _unseal(key, "access", bearer, ACCESS_SECONDS)
        granted = set(claims["scope"].split())
        if (claims["iss"], claims["aud"]) != (ISSUER, RESOURCE) or not granted or not granted.issubset(SCOPES):
            return _challenge()
    except (ValueError, InvalidToken, KeyError):
        return _challenge()
    if request.method != "POST":
        return Response(status_code=405, headers={**HEADERS, "Allow": "POST"})
    try:
        message = json.loads(await _read_body(request))
    except (ValueError, UnicodeError):
        return _rpc_error(None, -32700, "Parse error")
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _rpc_error(None, -32600, "Invalid request")
    method, identifier = message["method"], message.get("id")
    params = message.get("params", {})
    if not isinstance(params, dict):
        return _rpc_error(identifier, -32602, "Invalid params")
    if "id" not in message:
        return Response(status_code=202, headers=HEADERS)
    if method == "initialize":
        version = params.get("protocolVersion")
        result = {"protocolVersion": version if version in PROTOCOLS else PROTOCOLS[0],
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "Sports Cave CRM", "version": "1.0.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [
            {
                "name": name, "title": title, "description": description,
                "inputSchema": {"type": "object",
                                "properties": {"date": {"type": "string", "format": "date"}} if daily else {},
                                "required": ["date"] if daily else [], "additionalProperties": False},
                "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
                "securitySchemes": [{"type": "oauth2", "scopes": [scope]}],
                "_meta": {"securitySchemes": [{"type": "oauth2", "scopes": [scope]}]},
            }
            for name, (scope, _, title, description, daily) in TOOLS.items()
        ]}
    elif method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or name not in TOOLS or not isinstance(arguments, dict):
            return _rpc_error(identifier, -32602, "Unknown tool or invalid arguments")
        scope, page, _, _, daily = TOOLS[name]
        if scope not in granted:
            message = "Reconnect Sports Cave OS to authorize the requested reporting tool."
            auth = (f'Bearer resource_metadata="{ISSUER + RESOURCE_METADATA}", scope="{SCOPE_LIST}", '
                    f'error="insufficient_scope", error_description="{message}"')
            result = {"isError": True, "content": [{"type": "text", "text": message}],
                      "_meta": {"mcp/www_authenticate": [auth]}}
            return _response({"jsonrpc": "2.0", "id": identifier, "result": result})
        if set(arguments) != ({"date"} if daily else set()):
            return _rpc_error(identifier, -32602, "Invalid arguments")
        try:
            day = reporting_day(arguments["date"]) if daily else None
        except ValueError as error:
            return _rpc_error(identifier, -32602, str(error))
        try:
            if not await run_in_threadpool(_active_owner, claims, page):
                return _challenge()
            if scope == ORDERS_SCOPE:
                summary = await run_in_threadpool(orders_daily, day)
            elif scope == META_SCOPE:
                summary = await run_in_threadpool(meta_daily, day)
            else:
                summary = await run_in_threadpool(_campaign_summary)
        except Exception as error:
            LOG.warning("chatgpt_crm_mcp_unavailable type=%s", type(error).__name__)
            result = {"isError": True, "content": [{"type": "text", "text": "Reporting summary unavailable."}]}
        else:
            result = {"content": [{"type": "text", "text": json.dumps(summary)}], "structuredContent": summary}
    else:
        return _rpc_error(identifier, -32601, "Method not found")
    return _response({"jsonrpc": "2.0", "id": identifier, "result": result})


ROUTES = [
    (MCP_PATH, mcp, ["GET", "POST", "DELETE"]),
    (RESOURCE_METADATA, protected_resource, ["GET"]),
    (SERVER_METADATA, authorization_server, ["GET"]),
    (AUTH_PATH, authorize, ["GET", "POST"]),
    (TOKEN_PATH, token, ["POST"]),
    (REGISTRATION_PATH, register, ["POST"]),
]
