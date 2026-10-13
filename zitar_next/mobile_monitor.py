"""Loopback-only, read-only entrance for private Tailscale Serve."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener
from urllib.error import HTTPError
from zitar_next.gateway import NoRedirect


class Monitor(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if not self.path.startswith('/') or self.path.startswith('//') or '\\' in self.path:
            self.send_error(400)
            return
        request = Request('http://127.0.0.1:8080' + self.path,
                          headers={'Host': '127.0.0.1:8080'}, method='GET')
        try:
            try:
                response = build_opener(NoRedirect()).open(request, timeout=30)
            except HTTPError as error:
                response = error
            with response:
                body = response.read(20_000_001)
                if len(body) > 20_000_000:
                    self.send_error(502)
                    return
                self.send_response(response.code)
                for name in ('Content-Type', 'Location'):
                    if response.headers.get(name):
                        self.send_header(name, response.headers[name])
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('X-Frame-Options', 'DENY')
                self.end_headers()
                self.wfile.write(body)
        except OSError:
            self.send_error(503)

    def do_POST(self):
        if self.path!='/api/chat-proxy/chat':
            self.send_error(405,'Trading controls are disabled on mobile');return
        if self.headers.get('Origin') not in ('https://zitar-kvm4.tail409f42.ts.net','http://127.0.0.1:8081'):
            self.send_error(403,'Origin rejected');return
        if self.headers.get('Transfer-Encoding'):
            self.send_error(400);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192:raise ValueError('size')
            body=self.rfile.read(length)
            request=Request('http://127.0.0.1:8080/api/chat-proxy/chat',data=body,
                headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8080'},method='POST')
            try:response=build_opener(NoRedirect()).open(request,timeout=240)
            except HTTPError as error:response=error
            with response:
                payload=response.read(20000001)
                if len(payload)>20000000:raise ValueError('response size')
                self.send_response(response.code)
                self.send_header('Content-Type',response.headers.get('Content-Type','application/json'))
                self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(payload)
        except ValueError:self.send_error(400)
        except OSError:self.send_error(503)

    def reject_mutation(self):self.send_error(405,'Trading controls are disabled on mobile')

    do_PUT = reject_mutation
    do_DELETE = reject_mutation
    do_PATCH = reject_mutation


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 8081), Monitor).serve_forever()
