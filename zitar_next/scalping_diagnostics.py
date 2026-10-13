"""Read-only diagnostics. Costs embedded in fills are never subtracted twice."""
from decimal import Decimal as D

def report(book):
 rows=[]
 for p in book.get('closed',[]):
  qty=D(p['quantity']);side=D(p['direction']);entry=D(p['entry']);exit=D(p['exit'])
  fee=D(p.get('entry_fee','0'))+D(p.get('exit_fee','0'))
  slip=D(book['execution_policy']['slippage_rate'])
  embedded=qty*side*(entry-entry/(1+slip*side)+exit/(1-slip*side)-exit)
  loss=max(D(0),-D(p['net_pnl']));planned=p.get('planned_risk')
  stop=p.get('trailing_stop');is_stop=p.get('exit_reason')=='TRAILING_STOP'
  overshoot=max(D(0),(D(stop)-exit)*side)*qty if is_stop and stop is not None else None
  rows.append(dict(symbol=p['symbol'],closed_ms=p['closed_ms'],reason=p['exit_reason'],
   planned_risk=planned,actual_loss=str(loss),net_pnl=p['net_pnl'],fees=str(fee),funding=p.get('funding','0'),
   embedded_slippage_estimate=str(embedded),risk_excess=str(max(D(0),loss-D(planned))) if planned is not None else None,
   stop_overshoot_usdt=str(overshoot) if overshoot is not None else None,
   stop_detection_delay_ms=None))
 return dict(closed_count=len(rows),closed_fees=str(sum((D(r['fees']) for r in rows),D(0))),
  risk_excess_count=sum(r['risk_excess'] is not None and D(r['risk_excess'])>0 for r in rows),rows=rows[-30:][::-1],
  note='Kayma tahmini gerçekleşen fiyatlara dahildir; tekrar düşülmez. Spread maliyeti ayrı kaydedilmedi. Stop aşımı çıkış fiyatıyla ölçülür; stopun ilk geçilme zamanı bilinmediği için gecikme ölçülemez.')
