"""Independent LOCAL recovery console. Never expose this listener to a public network."""
import json,secrets,subprocess,threading,time,urllib.request
from pathlib import Path
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from zitar_paper_supervisor_v1 import FileLock
class Manager:
 def __init__(self,base):
  self.base=Path(base);self.csrf=secrets.token_urlsafe(32);self.lock=threading.Lock();self.job={'state':'IDLE'};self.last=0
 def health(self):
  try:
   with urllib.request.urlopen('http://127.0.0.1:5020/api/snapshot',timeout=3) as r:d=json.load(r)
   runtime=d.get('runtime',{});stamp=runtime.get('heartbeat_utc');age=time.time()-datetime.fromisoformat(stamp).timestamp() if stamp else None
   return {'reachable':True,'fresh':age is not None and 0<=age<30,'heartbeat_age':age,'state':runtime.get('state','UNKNOWN')}
  except Exception:return {'reachable':False,'fresh':False,'state':'UNREACHABLE'}
 def recover(self):
  with self.lock:
   if self.job['state']=='RUNNING':return self.job
   if time.monotonic()-self.last<120:return {'state':'COOLDOWN'}
   self.last=time.monotonic();self.job={'state':'RUNNING','started_utc':datetime.now(timezone.utc).isoformat()}
   threading.Thread(target=self.run,daemon=True).start();return self.job
 def run(self):
  try:
   # Fixed script only: never execute request-supplied paths, commands or PIDs.
   result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(self.base/'Repair-Zitar.ps1')],cwd=self.base,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   ok=result.returncode==0 and self.health()['fresh']
   self.job={'state':'VERIFIED' if ok else 'FAILED','exit_code':result.returncode,'finished_utc':datetime.now(timezone.utc).isoformat()}
  except subprocess.TimeoutExpired:self.job={'state':'TIMEOUT_CHECK_SYSTEM'}
  except Exception:self.job={'state':'START_FAILED'}
def server(base,port=5023):
 manager=Manager(base);assets=Path(base)/'zitar_app';host=f'127.0.0.1:{port}';origin='http://'+host
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def send(self,data,code=200,mime='application/json'):
   body=data if isinstance(data,bytes) else json.dumps(data).encode()
   self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY');self.end_headers();self.wfile.write(body)
  def valid_host(self):return self.headers.get('Host')==host
  def do_GET(self):
   if not self.valid_host():return self.send({'error':'HOST_REJECTED'},403)
   if self.path=='/status':return self.send(dict(engine=manager.health(),recovery=manager.job,csrf=manager.csrf,real_orders=False))
   routes={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript'),'/manifest.webmanifest':('manifest.webmanifest','application/manifest+json'),'/icon.svg':('icon.svg','image/svg+xml')}
   if self.path not in routes:return self.send({'error':'NOT_FOUND'},404)
   name,mime=routes[self.path];return self.send((assets/name).read_bytes(),mime=mime)
  def do_POST(self):
   if not self.valid_host() or self.headers.get('Origin')!=origin or not secrets.compare_digest(self.headers.get('X-Zitar-CSRF',''),manager.csrf):return self.send({'error':'FORBIDDEN'},403)
   if self.path!='/recover':return self.send({'error':'NOT_FOUND'},404)
   if self.headers.get('Content-Length','0')!='0':return self.send({'error':'BODY_NOT_ALLOWED'},400)
   return self.send(manager.recover(),202)
 return ThreadingHTTPServer(('127.0.0.1',port),Handler)
if __name__=='__main__':
 base=Path(__file__).resolve().parent;guard=FileLock(base/'zitar_app_manager_v1.lock')
 if guard.acquire():
  try:server(base).serve_forever()
  finally:guard.close()
