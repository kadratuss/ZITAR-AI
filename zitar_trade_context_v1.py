"""Read-only V3 FIFO outcomes linked to analysis available before entry."""
import csv,io,json
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
from zitar_cost_replay_v1 import replay
from zitar_research_rag_api_v1 import validate_chain

def timestamp(value):
    d=datetime.fromisoformat(value)
    if d.tzinfo is None: raise ValueError('TIMEZONE_REQUIRED')
    return d.timestamp()

def match_entry(entry,records,max_age=3600):
    entered=timestamp(entry['executed_at_utc'])
    candidates=[r for r in records if r.get('symbol')==entry['symbol'] and timestamp(r['observed_utc'])<=entered and timestamp(r.get('source_generated_utc') or r['observed_utc'])<=entered]
    if not candidates:return {'status':'NO_PRIOR_ANALYSIS','reason':'İşlem açılmadan önce kaydedilmiş analiz yok.'}
    r=max(candidates,key=lambda r:timestamp(r['observed_utc']))
    age=entered-timestamp(r.get('source_generated_utc') or r['observed_utc'])
    if age>max_age:return {'status':'STALE_ANALYSIS','reason':'Girişte analiz 60 dakikadan eskiydi.','age_seconds':age,'record_id':r['record_id']}
    return {'status':'MATCHED','record_id':r['record_id'],'age_seconds':age,'observation':r['observation'],'reason':'Girişten önce kaydedilmiş analiz; mum güncelliği ayrıca doğrulanmalı.'}

def report(base):
    base=Path(base)
    trades=list(csv.DictReader(io.StringIO((base/'multistrategy_live_trades_v3.csv').read_text(encoding='utf-8-sig'))))
    records=[json.loads(x) for x in (base/'zitar_research_memory_v1.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    ok,reason=validate_chain(records)
    if not ok:raise ValueError('INVALID_MEMORY_CHAIN:'+reason)
    by_id={t['trade_id']:t for t in trades}
    result=replay(trades)
    rows=[]; groups={}
    for close in result['closed_trades']:
        for segment in close['segments']:
            entry=by_id[segment['buy_id']]
            context=match_entry(entry,records)
            row=dict(strategy=close['strategy'],symbol=close['symbol'],buy_id=segment['buy_id'],sell_id=close['sell_id'],entry_utc=entry['executed_at_utc'],exit_utc=close['closed_utc'],net_try=segment['modeled_net_try'],fee_try=segment['fee_try'],context=context)
            rows.append(row)
            if context['status']=='MATCHED':
                label=close['strategy']+' / '+str(context['observation'].get('overall','UNKNOWN'))
                group=groups.setdefault(label,{'label':label,'segments':0,'net_try':Decimal(0)})
                group['segments']+=1;group['net_try']+=Decimal(row['net_try'])
    return {'scope':'V3 bağımsız strateji hesapları; Master hesabının sonucu değildir.','generated_utc':datetime.now(timezone.utc).isoformat(),'closed_trades':len(result['closed_trades']),'matched_segments':sum(r['context']['status']=='MATCHED' for r in rows),'rows':rows,'groups':[dict(g,net_try=str(g['net_try'])) for g in groups.values()],'limitations':['Sonradan üretilen analiz geçmiş işleme bağlanmaz.','60 dakikadan eski giriş analizi eşleştirmeye alınmaz.','FIFO parçaları bağımsız işlem sayılmaz.','Bu çalışma ilişkiyi gösterir; neden-sonuç, strateji başarısı veya test edilmiş iyileşme kanıtı değildir.'],'execution_authority':False}
