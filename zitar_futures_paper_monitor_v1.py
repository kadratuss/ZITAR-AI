import calendar,json,time
from pathlib import Path
from datetime import datetime
from zitar_futures_paper_engine_v1 import day,iso,number,POLICY

def overview(base):
 path=Path(base)/'zitar_futures_paper_v1.json'
 if not path.exists():return {'state':'NOT_STARTED','books':{}}
 s=json.loads(path.read_text(encoding='utf-8'));age=(time.time()*1000-s['heartbeat_ms'])/1000
 result={k:s[k] for k in ['state','policy','limitations','errors','universe']};result.update(started_utc=iso(s['started_ms']),heartbeat_age_seconds=age,books={},decisions=s['decisions'][-30:])
 result['pending_active_reset_id']=s.get('pending_active_reset_id')
 result['active_reset_ms']=s.get('active_reset_ms')
 result['active_strategy_names']=s.get('active_strategy_names')
 result['entry_control']=s.get('entry_control')
 result['retired_accounts']=[n for n,b in s['books'].items() if b.get('retired_ms')]
 result['signal_status']=s.get('signal_status')
 result['data_pipeline_version']=s.get('data_pipeline_version')
 result['strategy_lab']=None if s.get('active_strategy_names') else s.get('strategy_lab')
 result['trigger_lab']=None if s.get('active_strategy_names') else s.get('trigger_lab')
 from zitar_futures_settings_v1 import read_request,CHOICES
 result['leverage_choices']=list(CHOICES);result['leverage_request']=read_request(base)
 result['can_change_leverage']=not any(b['positions'] for b in s['books'].values())
 if age>120:result['state']='STALE_RUNTIME'
 for name,b in s['books'].items():
  if b.get('retired_ms') and not b['positions'] and not b.get('accounting_pending'):continue
  daily=list(b['daily'])+[dict(date=b['period'],start=b['period_start'],end=b['equity'],return_pct=str((number(b['equity'])/number(b['period_start'])-1)*100) if number(b['period_start']) else '0',quality=['OPEN_DAY'])]
  periods={}
  for kind in ['week','month']:
   groups={}
   for row in daily:
    d=datetime.fromisoformat(row['date']);i=d.isocalendar();key=f'{i.year}-W{i.week:02}' if kind=='week' else row['date'][:7];groups.setdefault(key,[]).append(row)
   periods[kind]=[]
   for key,rows in groups.items():
    rows.sort(key=lambda x:x['date']);start=number(rows[0]['start']);end=number(rows[-1]['end']);d=datetime.fromisoformat(rows[0]['date']);expected=7 if kind=='week' else calendar.monthrange(d.year,d.month)[1]
    periods[kind].append(dict(date=key,return_pct=str((end/start-1)*100) if start else '0',quality=['MODEL_LIMITATIONS']+(['PARTIAL_PERIOD'] if len(rows)<expected or any('OPEN_DAY' in r['quality'] for r in rows) else [])))
  result['books'][name]={k:b.get(k,'0') for k in ['cash','equity','unrealized','margin','fees_total','funding_total','realized','max_drawdown_pct','slot']}
  result['books'][name].update(period=b['period'],period_start=b['period_start'],daily=b['daily'])
  result['books'][name].update(entries_disabled=b.get('entries_disabled',False),retired_ms=b.get('retired_ms'),review_24h=b.get('review_24h'),daily_limit=b.get('daily_limit'),daily_pnl_pct=b.get('daily_pnl_pct'),accounting_pending=b.get('accounting_pending',False),valuation_ms=b.get('valuation_ms',min([v.get('quote_ms',0) for v in b['positions'].values()] or [0])),started_ms=b.get('started_ms',s['started_ms']),rules=b.get('rules'),evaluations=b.get('evaluations',{}),positions=list(b['positions'].values()),closed=b['closed'],days=daily,weeks=periods['week'],months=periods['month'],return_pct=str((number(b['equity'])/10000-1)*100))
 return result
