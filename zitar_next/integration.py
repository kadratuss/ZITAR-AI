"""Opt-in ASGI mount for the independent console; no production imports."""
import asyncio
import io
import json
import re
from email.message import Message
from urllib.parse import urlsplit
from zitar_next.dashboard import handler


class ResearchASGI:
    def __init__(self, root, origin, history_root=None, prefix='/zitar-next'):
        parsed = urlsplit(origin)
        if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or
                not parsed.port or parsed.username or parsed.password or
                parsed.path or parsed.query or parsed.fragment):
            raise ValueError('explicit loopback HTTP origin required')
        if not re.fullmatch(r'/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', prefix):
            raise ValueError('invalid mount prefix')
        self.prefix = prefix
        self.handler = handler(root, parsed.port, history_root, prefix)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            raise ValueError('HTTP only')
        body = bytearray()
        while True:
            event = await receive()
            if event['type'] == 'http.disconnect':
                return
            body.extend(event.get('body', b''))
            if len(body) > 4096:
                await send({'type':'http.response.start','status':413,'headers':[]})
                await send({'type':'http.response.body','body':b'Request too large'})
                return
            if not event.get('more_body'):
                break
        path = scope['path']
        if path == self.prefix or path.startswith(self.prefix+'/'):
            path = path[len(self.prefix):] or '/'
        query = scope.get('query_string',b'').decode('ascii')
        request = object.__new__(self.handler)
        request.path = path + ('?'+query if query else '')
        request.headers = Message()
        for key,value in scope['headers']:
            request.headers[key.decode('latin1')] = value.decode('latin1')
        request.headers.replace_header('Content-Length',str(len(body))) if 'Content-Length' in request.headers else request.headers.add_header('Content-Length',str(len(body)))
        request.rfile = io.BytesIO(body)
        response = []
        request.send = lambda status,payload,mime='application/json; charset=utf-8': response.append((status,payload,mime))
        method = scope['method']
        if method in ('GET','POST'):
            # File validation and optional public market reads must not block the ASGI loop.
            await asyncio.to_thread(getattr(request,'do_'+method))
        else:
            response.append((405,{'error':'METHOD_NOT_ALLOWED'},'application/json'))
        status,payload,mime = response[0]
        raw = payload.encode('utf-8') if isinstance(payload,str) else json.dumps(payload,allow_nan=False).encode('utf-8')
        headers = [(b'content-type',mime.encode()),(b'cache-control',b'no-store'),
                   (b'x-content-type-options',b'nosniff'),(b'x-frame-options',b'DENY'),
                   (b'content-security-policy',b"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")]
        await send({'type':'http.response.start','status':status,'headers':headers})
        await send({'type':'http.response.body','body':raw})


def mount_fastapi(app, root, origin, history_root=None, prefix='/zitar-next'):
    """Call explicitly during a future installation; starts no worker or server."""
    component = ResearchASGI(root,origin,history_root,prefix)
    app.mount(prefix,component,name='zitar-next-research')
    return component
