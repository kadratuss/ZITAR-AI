"""Single loopback entrance for production paper UI and Next research console."""
import argparse
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request,build_opener,HTTPRedirectHandler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):return None

def handler(port=8080,production_port=5020,research_port=8768,study_status='/srv/zitar/data/next/studies/20261010-v1/forward-status.json',filter_root='/srv/zitar/data/next/entry_filter_studies/20261010-v2',ops_status='/srv/zitar/data/next/operations/status.json'):
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
            if path=='/api/operations-study':
                if self.command!='GET':
                    return self.reply(405,b'{"error":"READ_ONLY"}')
                try:
                    source=Path(ops_status)
                    if source.is_symlink():raise ValueError('symlink')
                    data=json.loads(source.read_text(encoding='utf-8'))
                    return self.reply(200,json.dumps(data,ensure_ascii=False).encode('utf-8'))
                except (OSError,ValueError):
                    return self.reply(503,b'{"error":"OPERATIONS_STATUS_UNAVAILABLE"}')
            if path=='/api/entry-filter':
                if self.command!='GET':
                    return self.reply(405,b'{"error":"READ_ONLY"}')
                try:
                    folder=Path(filter_root)
                    if folder.is_symlink():raise ValueError('symlink')
                    status=folder/'status.json'
                    if status.is_symlink():raise ValueError('symlink')
                    data=json.loads(status.read_text(encoding='utf-8'))
                    if data.get('state')=='COMPLETE':
                        summary=folder/'summary.json'
                        if summary.is_symlink():raise ValueError('symlink')
                        data=json.loads(summary.read_text(encoding='utf-8'))
                    return self.reply(200,json.dumps(data,ensure_ascii=False).encode('utf-8'))
                except (OSError,ValueError):
                    return self.reply(503,b'{"error":"FILTER_STATUS_UNAVAILABLE"}')
            if path=='/api/forward-study':
                if self.command!='GET':
                    return self.reply(405,b'{"error":"READ_ONLY"}')
                try:
                    source=Path(study_status)
                    if source.is_symlink():raise ValueError('symlink')
                    data=json.loads(source.read_text(encoding='utf-8'))
                    return self.reply(200,json.dumps(data,ensure_ascii=False).encode('utf-8'))
                except (OSError,ValueError):
                    return self.reply(503,b'{"error":"STUDY_STATUS_UNAVAILABLE"}')
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
                    integration=Path(__file__).with_name('proposal_menu.html').read_bytes()
                    raw=raw.replace(b'</body>',integration+b'</body>')
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
