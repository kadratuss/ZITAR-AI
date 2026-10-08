import tempfile
import unittest
import sys
import time
import socket
from pathlib import Path
from datetime import datetime, timezone
from zitar_paper_supervisor_v1 import FileLock, lock_held, decision, Supervisor, ResearchSupervisor


class SupervisorTests(unittest.TestCase):
    def test_research_restart_guard_and_pause(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)
            (base/'zitar_research_runtime_v1.py').write_text('print("research fixture")',encoding='utf-8')
            worker=ResearchSupervisor(base,sys.executable)
            lock=FileLock(base/'zitar_research_runtime_v1.lock'); self.assertTrue(lock.acquire())
            self.assertEqual(worker.step()['action'],'UNHEALTHY_OWNER_NO_KILL')
            lock.close()
            self.assertEqual(worker.step()['action'],'START_REQUESTED')
            for child in worker.children: self.assertEqual(child.wait(timeout=5),0)
            self.assertEqual(worker.step()['action'],'RESTART_BACKOFF')
            (base/'zitar_research_supervisor.pause').touch()
            self.assertEqual(worker.step()['action'],'PAUSED')

    def test_existing_writer_never_restarted_even_stale(self):
        self.assertEqual(decision(True, True, {}, 1000, []), 'UNHEALTHY_OWNER_NO_KILL')
        stamp = datetime.fromtimestamp(990, timezone.utc).isoformat()
        self.assertEqual(decision(True, True, {'heartbeat_utc': stamp, 'last_successful_cycle_utc': stamp},
                                  1000, []), 'WATCHING')

    def test_busy_port_and_pause_prevent_launch(self):
        self.assertEqual(decision(False, True, {}, 1000, []), 'PORT_BUSY_NO_START')
        self.assertEqual(decision(False, False, {}, 1000, [], True), 'PAUSED')

    def test_rate_limit_and_backoff(self):
        self.assertEqual(decision(False, False, {}, 1000, [999]), 'RESTART_BACKOFF')
        self.assertEqual(decision(False, False, {}, 1000, [500,600,700,800,900]), 'RESTART_RATE_LIMIT')
        self.assertEqual(decision(False, False, {}, 2000, [500,600,700,800,900]), 'START_REQUIRED')

    def test_lock_released_after_owner_exits(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'owner.lock'
            owner = FileLock(path)
            self.assertTrue(owner.acquire())
            self.assertTrue(lock_held(path))
            owner.close()
            self.assertFalse(lock_held(path))

    def test_real_child_exit_then_restart_without_duplicate(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            module_dir = str(Path(__file__).resolve().parent)
            (base / 'zitar_full_paper_runtime_v1.py').write_text(
                'import sys,time\nfrom pathlib import Path\n'
                f'sys.path.insert(0,{module_dir!r})\n'
                'from zitar_paper_supervisor_v1 import FileLock\n'
                'p=Path(__file__).parent\n'
                'lock=FileLock(p/"zitar_full_paper_runtime_v1.lock")\n'
                'assert lock.acquire()\n'
                'with (p/"starts.txt").open("a") as f: f.write("start\\n")\n'
                'time.sleep(1)\nlock.close()\n', encoding='utf-8')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0))
                port = sock.getsockname()[1]
            worker = Supervisor(base, port, sys.executable)
            self.assertEqual(worker.step()['action'], 'START_REQUESTED')
            deadline = time.time()+5
            while not (base/'starts.txt').exists() and time.time()<deadline:
                time.sleep(.05)
            self.assertTrue(lock_held(base/'zitar_full_paper_runtime_v1.lock'))
            self.assertEqual(worker.step()['action'], 'UNHEALTHY_OWNER_NO_KILL')
            while lock_held(base/'zitar_full_paper_runtime_v1.lock') and time.time()<deadline:
                time.sleep(.05)
            self.assertEqual(worker.step()['action'], 'RESTART_BACKOFF')
            worker.attempts = [time.time()-20]
            self.assertEqual(worker.step()['action'], 'START_REQUESTED')
            for child in worker.children:
                child.wait(timeout=5)
            self.assertEqual((base/'starts.txt').read_text().splitlines(), ['start','start'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
