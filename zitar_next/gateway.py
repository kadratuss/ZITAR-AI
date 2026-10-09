"""Single loopback entrance for production paper UI and Next research console."""
import argparse
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request,build_opener,HTTPRedirectHandler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):return None

def handler(port=8080,production_port=5020,research_port=8768):
    class Gateway(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,raw,mime='application/json'):
            self.send_response(status)
            for k,v in [('Content-Type',mime),('Content-Length',str(len(raw))),('Cache-Control','no-store'),
                        ('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY')]:self.send_header(k,v)
            self.end_headers();self.wfile.write(raw)
        def proxy(self):
            host=f'127.0.0.1:{port}'
            if self.headers.get('Host')!=host:
                return self.reply(403,b'{"error":"LOCAL_HOST_REQUIRED"}')
            if self.command=='POST' and self.headers.get('Origin')!='http://'+host:
                return self.reply(403,b'{"error":"ORIGIN_REJECTED"}')
            path=self.path
            if path=='/zitar-next':
                self.send_response(302);self.send_header('Location','/zitar-next/');self.end_headers();return
            next_panel=path.startswith('/zitar-next/')
            upstream=research_port if next_panel else production_port
            if next_panel:path=path[len('/zitar-next'):]
            if not path.startswith('/') or path.startswith('//') or '\\' in path:
                return self.reply(400,b'{"error":"INVALID_PATH"}')
            if self.headers.get('Transfer-Encoding'):
                return self.reply(400,b'{"error":"TRANSFER_ENCODING_REJECTED"}')
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<=length<=65536:raise ValueError('size')
                body=self.rfile.read(length) if self.command=='POST' else None
                headers={'Host':f'127.0.0.1:{upstream}'}
                for key in ('Content-Type','X-Next-CSRF'):
                    if key in self.headers:headers[key]=self.headers[key]
                if self.command=='POST':headers['Origin']=f'http://127.0.0.1:{upstream}'
                request=Request(f'http://127.0.0.1:{upstream}'+path,data=body,headers=headers,method=self.command)
                try:response=build_opener(NoRedirect()).open(request,timeout=30)
                except HTTPError as exc:response=exc
                with response:
                    raw=response.read(20000001);status=response.code;mime=response.headers.get('Content-Type','application/json')
                if len(raw)>20000000:raise ValueError('response size')
                if status==200 and 'text/html' in mime and next_panel:
                    raw=raw.replace(b'data-next-base=""',b'data-next-base="/zitar-next"')
                if status==200 and 'text/html' in mime and not next_panel and path=='/':
                    link='<a href="/zitar-next/" style="display:block;padding:12px;color:#5eead4;background:#101827">Araştırma ve öğrenme · ZİTAR Next</a>'
                    raw=raw.replace(b'</body>',link.encode('utf-8')+b'</body>')
                self.reply(status,raw,mime)
            except (ValueError,OSError):self.reply(503,b'{"error":"UPSTREAM_UNAVAILABLE"}')
        do_GET=proxy
        do_POST=proxy
    return Gateway

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--production-port',type=int,default=5020)
    parser.add_argument('--research-port',type=int,default=8768)
    args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(args.port,args.production_port,args.research_port))
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':main()
