"""Bounded server health summary without account credentials or chat contents."""
import json
from pathlib import Path
from urllib.request import urlopen
def main():
    base=Path('/srv/zitar/runtime');out={}
    for name,url in [('snapshot','http://127.0.0.1:8080/api/snapshot'),('dashboard','http://127.0.0.1:8080/api/dashboard'),
                     ('reset','http://127.0.0.1:5020/api/paper-reset'),('learning','http://127.0.0.1:8080/zitar-next/api/state')]:
        try:
            with urlopen(url,timeout=25) as response:data=json.load(response)
            if name=='reset':out[name]=data
            elif name=='snapshot':out[name]=dict(state=data.get('runtime',{}).get('state'),live_health=data.get('runtime',{}).get('live_health'),last_error=data.get('runtime',{}).get('last_error'))
            elif name=='learning':out[name]=dict(active=len(data.get('active',[])),proposals=len(data.get('proposals',[])),status=data.get('status',{}).get('state'),markets=data.get('markets'))
            else:out[name]=dict(available=True,real_orders=data.get('real_orders'),keys=list(data)[:12])
        except Exception as e:out[name]=dict(error=str(e))
    names={'spot':'zitar_discovery_spot_v1.json','futures':'zitar_futures_paper_v1.json','scalping':'zitar_indicator_lab_v1.json','research':'zitar_research_experiment_v1.json','momentum':'zitar_momentum_experiment_v2.json'}
    for market,name in names.items():
        try:
            data=json.loads((base/name).read_text(encoding='utf-8-sig'))
            out[market]=dict(state=data.get('state'),errors=data.get('errors'),
                accounts={key:dict(cash=book.get('cash'),positions=len(book.get('positions',{}))) for key,book in data.get('books',{}).items() if key in data.get('active_strategy_names',[])})
        except Exception as e:out[market]=dict(error=str(e))
    print(json.dumps(out,indent=2))
if __name__=='__main__':main()
