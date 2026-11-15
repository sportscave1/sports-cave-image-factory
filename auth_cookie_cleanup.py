"""Compatibility cleanup for cookies issued HttpOnly by the retired implementation.

No session/authentication store. Only explicit same-origin cookie writes call this.
It allows the original browser cookie writer to work for existing installations.
"""
from urllib.parse import urlsplit
from starlette.responses import Response
import sc_auth


async def clear_cookie(request):
    origin = urlsplit(request.headers.get('origin',''))
    if origin.scheme not in ('http','https') or origin.netloc != request.headers.get('host'):
        return Response(status_code=403)
    response = Response(status_code=204,headers={'Cache-Control':'no-store'})
    response.delete_cookie(sc_auth.AUTH_COOKIE_NAME,path='/',httponly=True,samesite='lax')
    return response


ROUTES = (('/api/os/auth/clear-cookie',clear_cookie,('POST',)),)
