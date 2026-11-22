"""Customer-only endpoints. Mutations require same-origin JSON; private pages never cache."""
import secrets
from urllib.parse import urlencode

from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from marketplace import BASE_PATH as B, email, identifier
from marketplace_accounts import Accounts, COOKIE, FLOW_COOKIE, NEXT_COOKIE, MAX_AGE, SignInRequired, AuthUnavailable, safe_next
from marketplace_chat import ChatStore
import marketplace_account_views as views


def headers(nonce=''):
    from marketplace_api import security
    return {**security(nonce), 'Vary': 'Cookie', 'Referrer-Policy': 'no-referrer', 'X-Robots-Tag': 'noindex, nofollow'}


def cookie(response, name, value, age):
    response.set_cookie(name, value, max_age=age, path=B, secure=True, httponly=True, samesite='lax')


def redirect(path):
    return RedirectResponse(path, status_code=303, headers=headers())


def error(exc):
    from marketplace_api import form_error
    if isinstance(exc, SignInRequired):
        return JSONResponse({'ok': False, 'error': str(exc), 'signin': B + '/signup'}, status_code=401, headers=headers())
    if isinstance(exc, AuthUnavailable):
        return JSONResponse({'ok': False, 'error': str(exc)}, status_code=503, headers=headers())
    return form_error(exc, headers())


async def identity(request, store):
    return await run_in_threadpool(Accounts(store).authenticate, request.cookies.get(COOKIE))


async def page(request):
    from marketplace_api import unavailable_page
    nonce = secrets.token_urlsafe(18)
    path = request.url.path.rstrip('/')
    next_path = safe_next(request.query_params.get('next') or request.cookies.get(NEXT_COOKIE))
    try:
        if path == B + '/account/confirmed':
            return HTMLResponse(views.confirmed(nonce, next_path), headers=headers(nonce))
        if path == B + '/auth/recovery':
            await run_in_threadpool(Accounts(ChatStore()).recovery_exchange, request.cookies.get(FLOW_COOKIE), request.query_params.get('code'))
            return redirect(B + '/reset')
        if path in (B + '/signup', B + '/signin', B + '/recover', B + '/reset'):
            mode = path.rsplit('/', 1)[-1]
            if mode in ('signup', 'signin') and request.cookies.get(COOKIE):
                try:
                    await identity(request, ChatStore())
                    return redirect(next_path)
                except SignInRequired:
                    pass
            return HTMLResponse(views.auth(mode, next_path, nonce), headers=headers(nonce))
        store = ChatStore()
        try:
            profile = await identity(request, store)
        except SignInRequired:
            location = B + '/signup?' + urlencode({'next': safe_next(path + ('?' + request.url.query if request.url.query else ''))})
            return redirect(location)
        if path == B + '/account':
            document = views.account(profile, nonce)
        elif 'listing_id' in request.path_params:
            key = request.path_params['listing_id']
            if key == 'demo':
                document = views.demo_conversation(nonce)
            else:
                row = await run_in_threadpool(store.listing, identifier(key))
                if not row or row['status'] != 'published':
                    return unavailable_page(nonce, 404)
                if row['seller_email'].lower() == profile['email'] or row.get('seller_user_id') == profile['id']:
                    return redirect(B + '/inbox')
                intent = 'offer' if request.query_params.get('intent') == 'offer' else 'message'
                document = views.contact(row, intent, nonce)
        else:
            threads = await run_in_threadpool(store.inbox, profile['id'])
            selected, messages = None, []
            if 'thread_id' in request.path_params:
                result = await run_in_threadpool(store.conversation, request.path_params['thread_id'], profile['id'])
                selected, messages = result['conversation'], result['messages']
            document = views.inbox(threads, selected, messages, nonce)
        return HTMLResponse(document, headers=headers(nonce))
    except (ValueError, PermissionError) as exc:
        content = f'<main id="main" class="narrow"><h1>Let’s get you back.</h1><p>{views.h(str(exc))}</p><a class="button dark" href="{B}/signin">Sign in</a><a class="text-link" href="{B}/recover">Request a new reset link</a></main>'
        return HTMLResponse(views.document(content, 'Account access', '/account', nonce), status_code=403 if isinstance(exc, PermissionError) else 404, headers=headers(nonce))
    except Exception:
        return unavailable_page(nonce, 503)


async def auth_action(request):
    from marketplace_api import body, allow_rate
    try:
        payload = await body(request, 5000)
        action = request.path_params['action']
        store = ChatStore()
        accounts = Accounts(store)
        if action in ('signup', 'signin', 'recover'):
            address = email(payload.get('email'))
            if not allow_rate(request, 'account:' + address):
                raise ValueError('Please wait before trying again. Check your email for an existing link.')
        if action == 'signup':
            if payload.get('consent') is not True:
                raise ValueError('Agree to the marketplace terms and privacy notice.')
            try:
                await run_in_threadpool(accounts.provider.signup, address, payload.get('password'), payload.get('name'))
            except SignInRequired:
                # Do not disclose whether the email is already registered.
                pass
            response = JSONResponse({'ok': True, 'message': 'Check your email to confirm your account, then sign in. If you already have an account, sign in or reset your password.'}, headers=headers())
            cookie(response, NEXT_COOKIE, safe_next(payload.get('next')), 3600)
            return response
        if action == 'signin':
            bearer, _ = await run_in_threadpool(accounts.signin, address, payload.get('password'))
            response = JSONResponse({'ok': True, 'redirect': safe_next(payload.get('next'))}, headers=headers())
            cookie(response, COOKIE, bearer, MAX_AGE)
            cookie(response, NEXT_COOKIE, '', 0)
            return response
        if action == 'signout':
            await run_in_threadpool(accounts.logout, request.cookies.get(COOKIE))
            response = JSONResponse({'ok': True, 'redirect': B}, headers=headers())
            cookie(response, COOKIE, '', 0)
            return response
        if action == 'recover':
            bearer = await run_in_threadpool(accounts.recover, address)
            response = JSONResponse({'ok': True, 'message': 'If an account exists, a reset link is on its way. Open it in this browser.'}, headers=headers())
            cookie(response, FLOW_COOKIE, bearer, 900)
            return response
        if action == 'reset':
            await run_in_threadpool(accounts.reset_password, request.cookies.get(FLOW_COOKIE), payload.get('password'))
            response = JSONResponse({'ok': True, 'redirect': B + '/signin'}, headers=headers())
            cookie(response, FLOW_COOKIE, '', 0)
            cookie(response, COOKIE, '', 0)
            return response
        raise ValueError('Choose an account action.')
    except Exception as exc:
        return error(exc)


async def start(request, *, legacy=False):
    from marketplace_api import body
    try:
        payload = await body(request, 5000)
        store = ChatStore()
        profile = await identity(request, store)
        if legacy:
            payload = {'listing_id': payload.get('listing_id'), 'kind': 'text', 'text': payload.get('message'),
                       'request_id': str(__import__('uuid').uuid4())}
        result = await run_in_threadpool(store.start, profile['id'], payload.get('listing_id'), payload)
        return JSONResponse({'ok': True, **result, 'redirect': B + '/inbox/' + result['id']}, status_code=201, headers=headers())
    except Exception as exc:
        return error(exc)


async def messages(request):
    from marketplace_api import body
    try:
        store = ChatStore()
        payload = await body(request, 5000) if request.method == 'POST' else None
        profile = await identity(request, store)
        thread_id = identifier(request.path_params['thread_id'])
        if payload is not None:
            result = await run_in_threadpool(store.send, thread_id, profile['id'], payload)
            return JSONResponse({'ok': True, **result}, status_code=201, headers=headers())
        try:
            cursor = int(request.query_params.get('after', '0'))
        except ValueError:
            raise ValueError('Invalid message cursor.') from None
        result = await run_in_threadpool(store.conversation, thread_id, profile['id'], cursor)
        return JSONResponse({'ok': True, **result}, headers=headers())
    except Exception as exc:
        return error(exc)


async def safety(request):
    from marketplace_api import body
    try:
        payload = await body(request, 3000)
        store = ChatStore()
        profile = await identity(request, store)
        await run_in_threadpool(store.safety, request.path_params['thread_id'], profile['id'], payload.get('action'), payload.get('reason'))
        return JSONResponse({'ok': True}, headers=headers())
    except Exception as exc:
        return error(exc)


ROUTES = tuple((B + path, page, ('GET', 'HEAD')) for path in (
    '/account', '/signup', '/signin', '/recover', '/reset', '/account/confirmed', '/auth/recovery',
    '/inbox', '/inbox/{thread_id}', '/contact/{listing_id}')) + (
    (B + '/api/auth/{action}', auth_action, ('POST',)),
    (B + '/api/conversations', start, ('POST',)),
    (B + '/api/conversations/{thread_id}/messages', messages, ('GET', 'POST')),
    (B + '/api/conversations/{thread_id}/safety', safety, ('POST',)),
)
