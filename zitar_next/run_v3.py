"""Single-owner wrapper around the unchanged hourly V3 paper reference."""
import argparse
import importlib.util
from pathlib import Path
from zitar_next.hosting import check

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',required=True);p.add_argument('--next-root',required=True)
    a=p.parse_args();base=Path(a.base).resolve(strict=True)
    check(base,a.next_root)
    from zitar_paper_supervisor_v1 import FileLock
    lock=FileLock(base/'zitar_v3_cycle.lock')
    if not lock.acquire():raise RuntimeError('V3 cycle already owned')
    try:
        path=base/'multistrategy_live_runner_v3.py'
        spec=importlib.util.spec_from_file_location('zitar_existing_v3_cycle',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.main()
    finally:lock.close()

if __name__=='__main__':raise SystemExit(main())
