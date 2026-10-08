"""Performance summaries for isolated paper books; no trading authority."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Istanbul')

def moment(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))

def day(value):
    return moment(value).astimezone(TZ).date().isoformat()

def flag(state,date,reason):
    reasons=state.setdefault('quality_days',{}).setdefault(date,[])
    if reason not in reasons: reasons.append(reason)

def update_quality(state, now):
    today=now.astimezone(TZ).date()
    previous=state.get('last_success_utc',state['started_utc'])
    if (now-moment(previous)).total_seconds()>120:
        current=moment(previous).astimezone(TZ).date()
        while current<=today:
            flag(state,current.isoformat(),'MONITORING_GAP_OVER_120S')
            current+=timedelta(days=1)
    if state.get('valuation_state')!='OK':
        flag(state,today.isoformat(),'STALE_QUOTES')
    # Delayed fills alter subsequent holdings, so the series stays tainted.
    if state.get('has_delayed_replay'):
        flag(state,today.isoformat(),'DELAYED_REPLAY_IN_SERIES')
    for sample in state.get('samples',[]):
        if sample.get('valuation_state')!='OK':
            flag(state,day(sample['utc']),'STALE_QUOTES')

def performance(state):
    first=day(state['started_utc'])
    all_reports={}
    for name,book in state['books'].items():
        records=book.get('runtime_daily_records',[])
        days=[]
        previous_bad_close=False
        for record in sorted(records,key=lambda r:r['period_id']):
            date=record['period_id']
            reasons=list(state.get('quality_days',{}).get(date,[]))
            if date==first: reasons.append('PARTIAL_FIRST_DAY')
            expected=(datetime.fromisoformat(date)+timedelta(days=1)).date().isoformat()
            if record.get('next_period_id')!=expected: reasons.append('MULTIDAY_GAP')
            quote=record.get('last_mtm_utc'); actual=record.get('actual_rollover_utc')
            bad_close=not quote or not actual or (moment(actual)-moment(quote)).total_seconds()>120
            if bad_close: reasons.append('STALE_OR_UNKNOWN_CLOSING_QUOTE')
            if previous_bad_close: reasons.append('UNRELIABLE_START_VALUE')
            previous_bad_close=bad_close
            value=float(record['equity_return_pct'])
            days.append(dict(date=date,return_pct=value,eligible=not reasons,reasons=sorted(set(reasons)),
                start_equity_try=record['start_equity_try'],closing_equity_try=record['closing_equity_try']))
        valid=[d['return_pct'] for d in days if d['eligible']]
        # Preserve every-cycle peak/drawdown once enabled. Seed with retained samples.
        risks=state.setdefault('risk_observations',{})
        seed=name not in risks
        risk=risks.setdefault(name,{'peak_equity_try':10000.,'max_drawdown_pct':0.})
        for sample in (state.get('samples',[]) if seed else []):
            if sample.get('valuation_state')=='OK' and name in sample['returns']:
                eq=10000*(1+float(sample['returns'][name])/100)
                risk['peak_equity_try']=max(risk['peak_equity_try'],eq)
                risk['max_drawdown_pct']=max(risk['max_drawdown_pct'],(1-eq/risk['peak_equity_try'])*100)
        equity=float(book['account']['equity_try'])
        if state.get('valuation_state')=='OK':
            risk['peak_equity_try']=max(risk['peak_equity_try'],equity)
            risk['max_drawdown_pct']=max(risk['max_drawdown_pct'],(1-equity/risk['peak_equity_try'])*100)
        all_reports[name]=dict(eligible_days=len(valid),excluded_days=len(days)-len(valid),
            days_at_least_3=sum(v>=3 for v in valid),days_at_least_4=sum(v>=4 for v in valid),
            loss_days=sum(v<0 for v in valid),average_daily_pct=sum(valid)/len(valid) if valid else None,
            worst_daily_pct=min(valid) if valid else None,best_daily_pct=max(valid) if valid else None,
            observed_max_drawdown_pct=round(risk['max_drawdown_pct'],6),days=days,
            today_reasons=state.get('quality_days',{}).get(book['current_period']['period_id'],[]))
    return dict(schema='ZITAR_COMPARISON_PERFORMANCE_V1',target_daily_pct=[3,4],books=all_reports,
                decision='AWAITING_REVIEW' if all_reports['MASTER']['eligible_days'] else 'INSUFFICIENT_CLOSED_DAYS',
                automatic_release_approval=False,drawdown_scope='Observed BID samples; not tick-by-tick maximum')
