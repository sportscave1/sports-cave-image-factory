"""Compatible baseline headers; does not modify webhook bodies or CORS."""
import os


class ProtectionHeaders:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope.get('type')!='http':return await self.app(scope,receive,send)
        async def protected_send(message):
            if message['type']=='http.response.start':
                headers=list(message.get('headers',[]))
                existing={k.lower() for k,_ in headers}
                baseline={b'x-content-type-options':b'nosniff',b'referrer-policy':b'strict-origin-when-cross-origin'}
                if os.getenv('RENDER'):baseline[b'strict-transport-security']=b'max-age=31536000'
                # Keep camera and recording available to existing features.
                baseline[b'permissions-policy']=b'display-capture=(self)'
                if scope.get('path') in ('/','/daily-planner'):
                    # Permit existing same-origin components, reject external admin framing.
                    baseline[b'content-security-policy']=b"frame-ancestors 'self'"
                if scope.get('path','').startswith('/api/os/security/'):
                    baseline[b'cache-control']=b'no-store'
                    baseline[b'content-security-policy']=b"default-src 'none'; frame-ancestors 'none'"
                for key,value in baseline.items():
                    if key not in existing:headers.append((key,value))
                message={**message,'headers':headers}
            await send(message)
        await self.app(scope,receive,protected_send)
