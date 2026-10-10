"""Queue the human-authorized paper reset before first server start."""
import json
from pathlib import Path
from zitar_next.hosting import check
from zitar_reset_control_v1 import request
def main():
    base=Path('/srv/zitar/runtime');check(base,'/srv/zitar/data/next')
    result=request(base,{'confirm':'RESET_PAPER_10000'})
    Path('/etc/zitar/reset-request.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'id':result['id'],'status':result['status'],'real_orders':False}))
if __name__=='__main__':main()
