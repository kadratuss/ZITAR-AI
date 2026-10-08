import json,time
from pathlib import Path
def overview(base):
    base=Path(base);now=int(time.time()*1000);result={'now_ms':now,'discovery':None,'spot':None}
    for key,file in [('discovery','zitar_market_discovery_v1.json'),('spot','zitar_discovery_spot_v1.json')]:
        path=base/file
        if path.exists():
            data=json.loads(path.read_text(encoding='utf-8'));age=now-data.get('heartbeat_ms',data.get('completed_ms',0))
            result[key]=dict(data,age_seconds=age/1000,stale=age>180000)
            if key=='spot':result[key]['decisions']=data.get('decisions',[])[-30:]
    return result
