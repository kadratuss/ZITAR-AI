"""Local paper process supervisor. Never kills a process or edits portfolio state."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone


class FileLock:
    def __init__(self, path):
        self.path = Path(path)
        self.fh = None

    def acquire(self):
        self.fh = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            self.fh.write(b'0')
            self.fh.flush()
        self.fh.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self.close()
            return False

    def close(self):
        if self.fh:
            self.fh.close()
            self.fh = None


def lock_held(path):
    probe = FileLock(path)
    try:
        return not probe.acquire()
    finally:
        probe.close()


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def age(stamp, now):
    if not stamp:
        return float('inf')
    return now - datetime.fromisoformat(stamp).timestamp()


def decision(held, occupied, status, now, attempts, paused=False):
    if paused:
        return 'PAUSED'
    if held:
        fresh = all(-30 <= age(status.get(k), now) < limit for k, limit in
                    [('heartbeat_utc', 30), ('last_successful_cycle_utc', 120)])
        return 'WATCHING' if fresh and occupied else 'UNHEALTHY_OWNER_NO_KILL'
    if occupied:
        return 'PORT_BUSY_NO_START'
    recent = [t for t in attempts if now - t < 900]
    if len(recent) >= 5:
        return 'RESTART_RATE_LIMIT'
    if recent and now - recent[-1] < min(300, 15 * 2 ** (len(recent) - 1)):
        return 'RESTART_BACKOFF'
    return 'START_REQUIRED'


class Supervisor:
    def __init__(self, base, port, python):
        self.base, self.port, self.python = Path(base).resolve(), port, python
        self.path = self.base / 'zitar_paper_supervisor_v1.json'
        self.attempts = read(self.path).get('attempts', []) if self.path.exists() else []
        self.children = []

    def save(self, data):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        os.replace(tmp, self.path)

    def step(self):
        self.children = [child for child in self.children if child.poll() is None]
        now = time.time()
        try:
            runtime = read(self.base / 'zitar_full_paper_runtime_v1.json')
        except (OSError, ValueError):
            runtime = {}
        self.attempts = [t for t in self.attempts if now - t < 900]
        action = decision(lock_held(self.base / 'zitar_full_paper_runtime_v1.lock'),
                          port_open(self.port), runtime, now, self.attempts,
                          (self.base / 'zitar_paper_supervisor.pause').exists())
        data = dict(schema='ZITAR_PAPER_SUPERVISOR_V1', pid=os.getpid(),
                    heartbeat_utc=datetime.now(timezone.utc).isoformat(), action=action,
                    runtime_pid=runtime.get('pid'), runtime_state=runtime.get('state'),
                    attempts=self.attempts, port=self.port)
        if action == 'START_REQUIRED':
            # Persist the attempt before spawning. A crash cannot erase the rate limit.
            self.attempts.append(now)
            self.save(data)
            env = dict(os.environ)
            env['PYTHONPATH'] = str(self.base / '.venv' / 'Lib' / 'site-packages')
            env['PYTHONIOENCODING'] = 'utf-8'
            with (self.base / 'zitar_full_paper_stdout.log').open('ab') as out, \
                 (self.base / 'zitar_full_paper_stderr.log').open('ab') as err:
                child = subprocess.Popen([self.python, '-B', str(self.base / 'zitar_full_paper_runtime_v1.py'),
                                          '--base', str(self.base), '--port', str(self.port)],
                                         cwd=self.base, env=env, stdout=out, stderr=err,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.children.append(child)
            data.update(action='START_REQUESTED', child_pid=child.pid)
        self.save(data)
        return data


class ResearchSupervisor(Supervisor):
    def __init__(self, base, python):
        self.base, self.python = Path(base).resolve(), python
        self.path = self.base / 'zitar_research_supervisor_v1.json'
        self.attempts = read(self.path).get('attempts', []) if self.path.exists() else []
        self.children = []

    def step(self):
        script = self.base/'zitar_research_runtime_v1.py'
        if not script.exists(): return {'action':'NOT_INSTALLED'}
        self.children = [p for p in self.children if p.poll() is None]
        now = time.time()
        try: runtime=read(self.base/'zitar_research_runtime_v1.json')
        except (OSError,ValueError): runtime={}
        held=lock_held(self.base/'zitar_research_runtime_v1.lock')
        self.attempts=[t for t in self.attempts if now-t<900]
        paused=(self.base/'zitar_research_supervisor.pause').exists()
        if paused: action='PAUSED'
        elif held: action='WATCHING' if -30<=age(runtime.get('heartbeat_utc'),now)<180 else 'UNHEALTHY_OWNER_NO_KILL'
        else: action=decision(False,False,{},now,self.attempts)
        data=dict(schema='ZITAR_RESEARCH_SUPERVISOR_V1',pid=os.getpid(),
                  heartbeat_utc=datetime.now(timezone.utc).isoformat(),action=action,
                  runtime_pid=runtime.get('pid'),attempts=self.attempts)
        if action=='START_REQUIRED':
            self.attempts.append(now); self.save(data)
            env=dict(os.environ); env['PYTHONIOENCODING']='utf-8'
            env['PYTHONPATH']=str(self.base/'.venv'/'Lib'/'site-packages')
            with (self.base/'zitar_research_stdout.log').open('ab') as out, (self.base/'zitar_research_stderr.log').open('ab') as err:
                child=subprocess.Popen([self.python,'-B',str(script),'--base',str(self.base)],
                    cwd=self.base,env=env,stdout=out,stderr=err,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.children.append(child)
            data.update(action='START_REQUESTED',child_pid=child.pid)
        self.save(data)
        return data


class ComparisonSupervisor(Supervisor):
    def __init__(self, base, python):
        self.base, self.python = Path(base).resolve(), python
        self.path = self.base / 'zitar_comparison_supervisor_v1.json'
        self.attempts = read(self.path).get('attempts', []) if self.path.exists() else []
        self.children = []

    def step(self):
        script = self.base/'zitar_comparison_runtime_v1.py'
        if not script.exists() or not (self.base/'zitar_comparison_start_v1.json').exists(): return {'action':'NOT_INSTALLED'}
        self.children = [p for p in self.children if p.poll() is None]
        now = time.time()
        try: runtime=read(self.base/'zitar_comparison_runtime_v1.json')
        except (OSError,ValueError): runtime={}
        held=lock_held(self.base/'zitar_comparison_runtime_v1.lock')
        self.attempts=[t for t in self.attempts if now-t<900]
        paused=(self.base/'zitar_comparison_supervisor.pause').exists()
        if paused: action='PAUSED'
        elif held: action='WATCHING' if -30<=age(runtime.get('heartbeat_utc'),now)<180 else 'UNHEALTHY_OWNER_NO_KILL'
        else: action=decision(False,False,{},now,self.attempts)
        data=dict(schema='ZITAR_COMPARISON_SUPERVISOR_V1',pid=os.getpid(),
                  heartbeat_utc=datetime.now(timezone.utc).isoformat(),action=action,
                  runtime_pid=runtime.get('pid'),attempts=self.attempts)
        if action=='START_REQUIRED':
            self.attempts.append(now); self.save(data)
            env=dict(os.environ); env['PYTHONIOENCODING']='utf-8'
            env['PYTHONPATH']=str(self.base/'.venv'/'Lib'/'site-packages')
            with (self.base/'zitar_comparison_stdout.log').open('ab') as out, (self.base/'zitar_comparison_stderr.log').open('ab') as err:
                child=subprocess.Popen([self.python,'-B',str(script),'--base',str(self.base)],
                    cwd=self.base,env=env,stdout=out,stderr=err,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.children.append(child)
            data.update(action='START_REQUESTED',child_pid=child.pid)
        self.save(data)
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--port', type=int, default=5020)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    guard = FileLock(args.base / 'zitar_paper_supervisor_v1.lock')
    if not guard.acquire():
        print('Supervisor already active.')
        return
    try:
        worker = Supervisor(args.base, args.port, args.python)
        research_worker = ResearchSupervisor(args.base, args.python)
        comparison_worker = ComparisonSupervisor(args.base, args.python)
        while True:
            try:
                result = worker.step()
                result['research'] = research_worker.step()
                result['comparison'] = comparison_worker.step()
                if args.once:
                    print(json.dumps(result))
                    return
            except Exception as exc:
                print(repr(exc), file=sys.stderr, flush=True)
                if args.once:
                    raise
            time.sleep(10)
    finally:
        guard.close()


if __name__ == '__main__':
    main()
