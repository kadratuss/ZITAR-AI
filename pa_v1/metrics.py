import statistics as st
from collections import defaultdict

def summary(b,initial=10000):
 groups=defaultdict(list)
 for p in b['closed']:groups[p.get('signal_id',str(p.get('opened_ms')))+p.get('symbol','')].append(p)
 open_ids={p.get('signal_id','')+symbol for symbol,p in b['positions'].items()}
 trades=[]
 for sid,parts in sorted(groups.items(),key=lambda item:max(p['closed_ms'] for p in item[1])):
  if sid in open_ids:continue
  first=parts[0];net=sum(float(x['net_pnl']) for x in parts);risk=float(first.get('initial_risk',0))
  trades.append(dict(first.get('evidence',{}),net=net,R=net/risk if risk else 0,hold=(max(x['closed_ms'] for x in parts)-first['opened_ms'])/60000))
 values=[x['net'] for x in trades];wins=[v for v in values if v>0];loss=[v for v in values if v<0]
 days=[x['return_pct'] for x in b['daily'] if not x.get('partial',False)]
 def group(field,keyfn):
  out={}
  for x in trades:
   key=keyfn(x.get(field));out.setdefault(key,[]).append(x)
  return {k:dict(trades=len(v),win_rate=sum(x['net']>0 for x in v)/len(v),net_pnl=sum(x['net'] for x in v),expectancy=st.mean(x['net'] for x in v),avg_R=st.mean(x['R'] for x in v),net_R=sum(x['R'] for x in v),profit_factor=sum(max(0,x['net']) for x in v)/abs(sum(min(0,x['net']) for x in v)) if any(x['net']<0 for x in v) else None) for k,v in out.items()}
 consecutive={True:0,False:0};best={True:0,False:0}
 for v in values:
  sign=v>0;consecutive[sign]+=1;consecutive[not sign]=0;best[sign]=max(best[sign],consecutive[sign])
 return dict(total_trades=len(trades),winning_trades=len(wins),losing_trades=len(loss),win_rate=len(wins)/len(values) if values else None,gross_profit=sum(wins),gross_loss=sum(loss),net_profit=float(b['equity'])-initial,closed_net=sum(values),fees=float(b['fees_total']),slippage='EMBEDDED_IN_FILL_PRICE',profit_factor=sum(wins)/abs(sum(loss)) if loss else None,expectancy_per_trade=st.mean(values) if values else None,average_R=st.mean(x['R'] for x in trades) if trades else None,median_R=st.median(x['R'] for x in trades) if trades else None,max_drawdown_pct=float(b['max_drawdown_pct']),consecutive_wins=best[True],consecutive_losses=best[False],average_hold_minutes=st.mean(x['hold'] for x in trades) if trades else None,daily_return_mean=st.mean(days) if days else None,daily_return_median=st.median(days) if days else None,daily_return_std=st.pstdev(days) if days else None,best_day=max(days) if days else None,worst_day=min(days) if days else None,full_days=len(days),positive_days_pct=100*sum(x>0 for x in days)/len(days) if days else None,target_hit_days=sum(x>=3 for x in days),target_hit_rate=sum(x>=3 for x in days)/len(days) if days else None,day_threshold_rates={str(k):sum(x>=k if k>0 else x<=k for x in days)/len(days) if days else None for k in [1,2,3,4,5,-1,-2,-3]},setup=group('setup_type',lambda x:x or 'REFERENCE'),score=group('PA_SCORE',lambda x:'NA' if x is None else '90+' if x>=90 else str(int(x)//5*5)+'-'+str(int(x)//5*5+4)),volume=group('volume_ratio',lambda x:'NA' if x is None else '<1' if x<1 else '1-1.2' if x<1.2 else '1.2-1.5' if x<1.5 else '1.5-2' if x<=2 else '>2'),regime=group('regime',lambda x:x or 'NA'))

