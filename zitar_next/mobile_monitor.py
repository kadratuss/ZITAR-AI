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
        self.send_error(405, 'Mobile monitoring is read-only')

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 8081), Monitor).serve_forever()
