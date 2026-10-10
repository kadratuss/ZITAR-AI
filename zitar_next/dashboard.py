"""Independent loopback Next proposal console. Never controls production ZITAR."""
import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from zitar_next.store import Registry,workspace

def public_summary(value):
    """Keep the console bounded; complete decision traces remain in run artifacts."""
    if isinstance(value,dict):return {k:public_summary(v) for k,v in value.items() if k!='decisions'}
    if isinstance(value,list):return [public_summary(v) for v in value]
    return value


def handler(root,port,history_root=None,prefix=""):
    from research_dashboard import ResearchStore
    history = ResearchStore(history_root) if history_root else None
    root = workspace(root)
    registry = Registry(root)
    token = secrets.token_urlsafe(32)
    origin = 'http://127.0.0.1:'+str(port)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def send(self,status,body,mime='application/json; charset=utf-8'):
            raw = body.encode('utf-8') if isinstance(body,str) else json.dumps(body,allow_nan=False).encode('utf-8')
            self.send_response(status)
            for key,value in [('Content-Type',mime),('Content-Length',str(len(raw))),('Cache-Control','no-store'),
                              ('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),
                              ('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")]:
                self.send_header(key,value)
            self.end_headers()
            self.wfile.write(raw)

        def local(self):
            return self.headers.get('Host') == '127.0.0.1:'+str(port)

        def do_GET(self):
            if not self.local():
                return self.send(403,dict(error='LOCAL_HOST_REQUIRED'))
            try:
                parsed = urlsplit(self.path)
                from urllib.parse import parse_qs
                query = parse_qs(parsed.query)
                if parsed.path == '/api/history/runs':
                    return self.send(200,dict(runs=history.runs() if history else []))
                if parsed.path == '/api/history/run' and history:
                    return self.send(200,history.load(query.get('id',[''])[0]))
                if parsed.path == '/api/history/market' and history:
                    return self.send(200,history.market(query.get('symbol',[''])[0]))
                if self.path == '/':
                    return self.send(200,Path(__file__).with_name('dashboard.html').read_text(encoding='utf-8').replace('data-next-base=""','data-next-base="'+prefix+'"'),'text/html; charset=utf-8')
                if self.path == '/api/state':
                    from zitar_next.finrl_status import reports,combinations
                    status = json.loads((root/'status.json').read_text(encoding='utf-8')) if (root/'status.json').exists() else dict(state='NOT_STARTED')
                    from datetime import datetime,timezone
                    if status.get('updated'):
                        age=(datetime.now(timezone.utc)-datetime.fromisoformat(status['updated'])).total_seconds()
                        status['heartbeat_age_seconds']=age
                        status['stale']=not 0 <= age <= 660
                    market_path=root/'market_status.json'
                    markets=json.loads(market_path.read_text(encoding='utf-8')) if market_path.exists() else {}
                    return self.send(200,public_summary(dict(registry.all(),status=status,markets=markets,csrf=token,scope='NEXT_RESEARCH_ONLY',finrlx=reports(root),combinations=combinations(root))))
                if self.path == '/api/summary':
                    from zitar_next.bridge import summary
                    return self.send(200,summary(root))
                return self.send(404,dict(error='NOT_FOUND'))
            except (ValueError,OSError,KeyError,TypeError,RuntimeError):
                return self.send(503,dict(error='RESEARCH_STATE_UNAVAILABLE'))

        def do_POST(self):
            if not self.local() or self.headers.get('Origin') != origin or not secrets.compare_digest(self.headers.get('X-Next-CSRF',''),token):
                return self.send(403,dict(error='ORIGIN_OR_TOKEN_REJECTED'))
            if self.path != '/api/decision':
                return self.send(404,dict(error='NOT_FOUND'))
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 4096 or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('invalid request body')
                value = json.loads(self.rfile.read(length))
                state = registry.decide(value['id'],value['decision'],value['note'])
                return self.send(200,dict(state=state,scope='NEXT_PAPER_ONLY',real_orders=False))
            except (ValueError,KeyError,TypeError):
                return self.send(400,dict(error='Karar uygulanamadı: uygunluk, durum ve açıklamayı kontrol edin.'))
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--history-root')
    parser.add_argument('--port',type=int,default=8768)
    parser.add_argument('--prefix',default='')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1',args.port),handler(args.root,args.port,args.history_root,args.prefix))
    print('Next preview: http://127.0.0.1:'+str(args.port),flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
