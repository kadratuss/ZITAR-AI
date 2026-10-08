"""Periodic local MTF synthesis + append-only memory. Never refreshes market candles."""
import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from zitar_paper_supervisor_v1 import FileLock

INTERVAL=900

def metadata(base):
    path=Path(base)/'zitar_market_memory_refresh_v1.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'state':'NOT_RUN','interval_seconds':INTERVAL}

def refresh(base, force=False, runner=subprocess.run, clock=time.time):
    base=Path(base)
    lock=FileLock(base/'zitar_research_memory_writer.lock')
    if not lock.acquire(): return {'state':'BUSY'}
    try:
        previous=metadata(base)
        if not force and clock()<previous.get('next_run_epoch',0): return previous
        result={'state':'RUNNING','interval_seconds':INTERVAL,'started_utc':datetime.now(timezone.utc).isoformat(),'next_run_epoch':clock()+INTERVAL,'last_success_utc':previous.get('last_success_utc')}
        def save():
            target=base/'zitar_market_memory_refresh_v1.json'
            tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(target)
        save()
        try:
            for script in ['zitar_mtf_research_v2.py','zitar_research_memory_v1.py']:
                completed=runner([sys.executable,'-B',str(base/script)],cwd=str(base),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
                if completed.returncode: raise RuntimeError(script+': '+completed.stderr[-1500:])
            result.update(state='UPDATED',last_success_utc=datetime.now(timezone.utc).isoformat(),note='Yerel mumlar yeniden analiz edildi. Mum verisi bu işlemle indirilmez; kaynak tarihleri ayrıca kontrol edilmelidir.')
        except Exception as exc:
            result.update(state='ERROR',error=str(exc))
        save()
        return result
    finally: lock.close()
