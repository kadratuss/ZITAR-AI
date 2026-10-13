"""Read-only adapter for the existing Control Center data endpoint."""
import argparse
import importlib.util
import os
import subprocess
from pathlib import Path
from http.server import ThreadingHTTPServer

def provider(base):
    path=Path(base).resolve(strict=True)/'zitar_control_center_v2_3_1_test.py'
    spec=importlib.util.spec_from_file_location('zitar_readonly_control_center',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if os.name!='nt':
        def timer_status():
            try:
                result=subprocess.run(['systemctl','show','zitar-v3.timer','--property=ActiveState','--value'],capture_output=True,text=True,timeout=3)
                status=result.stdout.strip() if result.returncode==0 else 'UNKNOWN'
            except (OSError,subprocess.TimeoutExpired):status='UNKNOWN'
            return dict(State=status,LastRunTime='',LastTaskResult=None,NextRunTime='',source='LINUX_SYSTEMD_TIMER')
        module.task_status=timer_status
    return module

def handler(module):
    class ReadOnly(module.Handler):
        def do_POST(self):self.send_bytes(b'Method not allowed','text/plain',405)
        def do_GET(self):
            if self.path!='/api/dashboard':return self.send_bytes(b'Not found','text/plain',404)
            return super().do_GET()
    return ReadOnly

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',required=True);p.add_argument('--port',type=int,default=5017)
    a=p.parse_args();server=ThreadingHTTPServer(('127.0.0.1',a.port),handler(provider(a.base)))
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':main()
