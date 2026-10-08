"""Pure paper adapter: reuses existing fills/accounting, no exchange methods."""
import copy,math
from decimal import Decimal as D,ROUND_DOWN
from zitar_futures_paper_engine_v1 import fresh,open_position,close_position,mark,day,POLICY
from zitar_discovery_spot_v1 import RULES
from zitar_market_discovery_v1 import liquidity

def create(ms,c):
 c.validate();books={}
 for variant in ('A_BE','B_STRUCTURAL'):
  b=copy.deepcopy(fresh(ms,[])['books']['BASELINE']);b.update(cash=str(c.initial),equity=str(c.initial),peak=str(c.initial),period_start=str(c.initial),seen=[],decisions=[],samples=[],streak=0,halted=False,execution_policy=dict(POLICY,leverage=1,fee_rate=RULES['fee'],slippage_rate=RULES['slippage']),variant=variant)
  books[variant]=b
 return dict(strategy_id=c.strategy_id,mode='PAPER',market='SPOT',real_orders=False,config_hash=c.hash(),started_ms=ms,books=books,heartbeat_ms=ms)

def partial(b,symbol,q,ms,reason,amount=None):
 p=b['positions'][symbol];whole=D(p['quantity']);take=whole if amount is None else min(whole,D(amount))
 if take<=0:return
 piece=copy.deepcopy(p);fraction=take/whole;piece['quantity']=str(take)
 for k in ('margin','initial_margin','entry_fee','funding'):piece[k]=str(D(p[k])*fraction)
 b['positions'][symbol]=piece;close_position(b,symbol,q,ms,reason)
 if take<whole:
  p['quantity']=str(whole-take)
  for k in ('margin','initial_margin','entry_fee','funding'):p[k]=str(D(p[k])-D(piece[k]))
  b['positions'][symbol]=p
 else:
  net=sum(D(x['net_pnl']) for x in b['closed'] if x.get('signal_id')==p['signal_id'])
  b['streak']=b['streak']+1 if net<0 else 0

def manage(b,quotes,features,ms,c):
 for symbol,p in list(b['positions'].items()):
  if symbol not in quotes:continue
  q=quotes[symbol];price=D(q['bid']);stop=D(p['pa_stop'])
  # Sampled quote stop; never infer unobserved intrabar fills.
  if price<=stop:partial(b,symbol,q,ms,'STRUCTURAL_STOP');continue
  for idx,fraction in [(1,c.tp1_fraction),(2,c.tp2_fraction)]:
   if not p.get('tp'+str(idx)) and price>=D(p['entry'])+D(p['risk_price'])*idx:
    step=D(p['lot_step']);amount=(D(p['original_qty'])*D(str(fraction))/step).to_integral_value(rounding=ROUND_DOWN)*step
    if amount<D(p['min_qty']) or amount*price<D(p['min_notional']):continue
    residual=D(p['quantity'])-amount
    if residual and (residual<D(p['min_qty']) or residual*price<D(p['min_notional'])):amount=D(p['quantity'])
    partial(b,symbol,q,ms,'TP'+str(idx),amount)
    if symbol not in b['positions']:break
    p=b['positions'][symbol];p['tp'+str(idx)]=True
    if idx==1 and b['variant']=='A_BE':
     fee=D(b['execution_policy']['fee_rate']);slip=D(b['execution_policy']['slippage_rate'])
     p['pa_stop']=str(max(D(p['pa_stop']),D(p['entry'])*(1+fee)/((1-fee)*(1-slip))))
  if symbol not in b['positions']:continue
  p=b['positions'][symbol];f=features.get(symbol,{})
  if p.get('tp1') and b['variant']=='B_STRUCTURAL' or p.get('tp2'):
   level=f.get('support');a=f.get('atr')
   if level and a and f.get('signal_timestamp',0)>p['opened_ms']:
    proposed=D(str(level-c.stop_atr*a))
    if proposed<price:p['pa_stop']=str(max(D(p['pa_stop']),proposed))
 if set(b['positions']).issubset(quotes):mark(b,quotes);b['valuation_ms']=ms

def tick(state,market,features,ms,c,paused=False,historical=False):
 c.validate()
 if state.get('mode')!='PAPER' or state.get('market')!='SPOT' or state.get('real_orders') is not False:raise ValueError('PAPER_MODE_NOT_CONFIRMED')
 if state['config_hash']!=c.hash():raise ValueError('CONFIG_CHANGED_NEW_EXPERIMENT_REQUIRED')
 quotes={s:v['quote'] for s,v in market.items() if 0<=ms-int(v['quote']['time'])<=30000 and 0<float(v['quote']['bid'])<=float(v['quote']['ask']) and math.isfinite(float(v['quote']['ask']))}
 for b in state['books'].values():
  # Midnight baseline uses previous committed equity; mark belongs to new day.
  if b['period']!=day(ms):
   b['daily'].append(dict(date=b['period'],start=b['period_start'],end=b['equity'],partial=b['period']==day(state['started_ms']),return_pct=(float(b['equity'])/float(b['period_start'])-1)*100))
   b.update(period=day(ms),period_start=b['equity'],halted=False,streak=0)
  manage(b,quotes,features,ms,c)
  if float(b['equity'])<=float(b['period_start'])*(1-c.max_daily_loss) or b['streak']>=c.max_consecutive_losses:b['halted']=True
  b['samples'].append([ms,float(b['equity'])]);b['entries_paused']=paused or b['halted']
  for symbol,f in sorted(features.items()):
   rejection=list(f.get('reasons',[]));sid=f.get('signal_id')
   if not sid or f.get('decision')!='PAPER_BUY':
    b['decisions'].append(dict(ms=ms,symbol=symbol,result='NO_TRADE',reasons=rejection));continue
   if sid in b['seen']:continue
   b['seen'].append(sid)
   if b['entries_paused']:rejection.append('PA_V1_TRADING_HALTED_FOR_DAY' if b['halted'] else 'ENTRIES_PAUSED')
   if not set(b['positions']).issubset(quotes):rejection.append('MISSING_POSITION_QUOTE')
   if symbol not in quotes:rejection.append('STALE_DATA')
   if symbol in b['positions']:rejection.append('DUPLICATE_POSITION')
   if sum(len(x['positions']) for x in state['books'].values())>=min(c.cap,POLICY['slots']):rejection.append('POSITION_LIMIT')
   if not historical and ms-f['signal_timestamp']>c.max_signal_age_ms:rejection.append('STALE_SIGNAL')
   if rejection:b['decisions'].append(dict(ms=ms,symbol=symbol,result='TRADE_REJECTED',reasons=rejection));continue
   data=market[symbol];q=quotes[symbol];fee=D(b['execution_policy']['fee_rate']);slip=D(b['execution_policy']['slippage_rate']);entry=D(q['ask'])*(1+slip);stop=D(str(f['stop_price']));risk=entry-stop
   if risk<=0 or not f.get('resistance') or (D(str(f['resistance']))-entry)/risk<D(str(c.min_rr)):rejection.append('INSUFFICIENT_RR')
   else:
    perunit=risk+entry*fee+stop*(fee+slip);budget=min(D(b['equity'])*D(str(c.risk_per_trade))/perunit*entry,D(b['cash'])/(1+fee))
    b['slot']=str(max(D(0),budget))
    if not historical:
     try:
      if not liquidity(data['depth'],float(budget))['eligible']:rejection.append('LIQUIDITY_INSUFFICIENT')
     except (KeyError,ValueError):rejection.append('LIQUIDITY_UNAVAILABLE')
   if rejection:b['decisions'].append(dict(ms=ms,symbol=symbol,result='TRADE_REJECTED',reasons=rejection));continue
   outcome=open_position(b,symbol,1,q,data['contract'],ms,'ZITAR_PA_V1')
   if outcome=='OPENED':
    p=b['positions'][symbol];p.update(signal_id=sid,evidence=copy.deepcopy(f),pa_stop=str(stop),risk_price=str(D(p['entry'])-stop),original_qty=p['quantity'],initial_risk=str(D(p['quantity'])*perunit),lot_step=data['contract']['step'],min_qty=data['contract']['min_qty'],min_notional=data['contract']['min_notional'])
   b['decisions'].append(dict(ms=ms,symbol=symbol,result=outcome,signal=f))
  if set(b['positions']).issubset(quotes):mark(b,quotes)
  b['decisions']=b['decisions'][-2000:]
 state['heartbeat_ms']=ms
 return state
