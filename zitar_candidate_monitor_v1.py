"""Calendar monitoring for isolated candidate; incomplete periods never count as passes."""
import calendar,json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
TZ=ZoneInfo('Europe/Istanbul')
def overview(base):
    path=Path(base)/'zitar_candidate_runtime_v1.json'
    if not path.exists():return {'state':'NOT_STARTED','books':{}}
    state=json.loads(path.read_text(encoding='utf-8'))
    result={k:state.get(k) for k in ('state','started_utc','heartbeat_utc','valuation_state','policy','policy_hash')}
    heartbeat=datetime.fromisoformat(state['heartbeat_utc'])
    result['heartbeat_age_seconds']=(datetime.now(heartbeat.tzinfo)-heartbeat).total_seconds()
    if result['heartbeat_age_seconds']>120:result['state']='STALE_RUNTIME'
    result['scope']='Yeni ve eşit 10.000 TRY hesaplar; canlı Master ve eski karşılaştırmadan ayrı. Aday V1, V3 girişlerini filtreler; çıkışlar kaynak desteklerinin kalkmasıyla yapılır.'
    result['books']={}
    for name,book in state['books'].items():
        daily=list(state['performance']['books'][name]['days'])
        period=book['current_period'];account=book['account']
        start=float(period['start_equity_try']);end=float(account['equity_try'])
        daily.append(dict(date=period['period_id'],start_equity_try=str(start),closing_equity_try=str(end),return_pct=(end/start-1)*100,eligible=False,reasons=['OPEN_DAY']))
        summaries={}
        for kind in ('week','month'):
            groups={}
            for row in daily:
                d=datetime.fromisoformat(row['date']);iso=d.isocalendar()
                key=f'{iso.year}-W{iso.week:02}' if kind=='week' else row['date'][:7]
                groups.setdefault(key,[]).append(row)
            summaries[kind]=[]
            for key,rows in groups.items():
                rows.sort(key=lambda r:r['date']);d=datetime.fromisoformat(rows[0]['date'])
                expected=7 if kind=='week' else calendar.monthrange(d.year,d.month)[1]
                complete=len(rows)==expected and all(r['eligible'] for r in rows)
                summaries[kind].append(dict(period=key,observed_days=len(rows),expected_days=expected,complete=complete,return_pct=(float(rows[-1]['closing_equity_try'])/float(rows[0]['start_equity_try'])-1)*100))
        open_positions=[dict(p,symbol=symbol) for symbol,p in account['positions'].items()]
        result['books'][name]=dict(realized_pnl_try=account.get('realized_pnl_try'),unrealized_pnl_try=account.get('unrealized_pnl_try'),cash_try=account['cash_try'],equity_try=account['equity_try'],positions=account['open_position_count'],open_positions=open_positions,closed_positions=book.get('closed_positions',[]),position_tracking_started_utc=book.get('position_tracking_started_utc'),valuation_state=state.get('valuation_state'),last_mtm_utc=state.get('last_mtm_utc'),total_return_pct=(end/10000-1)*100,max_drawdown_pct=state['performance']['books'][name]['observed_max_drawdown_pct'],days=daily,weeks=summaries['week'],months=summaries['month'])
    result['events']=state['events'][-30:]
    result['release']='Otomatik strateji terfisi yok; tamamlanmış ve güvenilir dönemler üzerinden değerlendirme gerekir.'
    return result
