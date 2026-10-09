"""Isolated USDT perpetual simulation. No credentials, order endpoints or spot writes."""
from decimal import Decimal, ROUND_DOWN
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import hashlib,json
D=Decimal
TZ=ZoneInfo('Europe/Istanbul')
POLICY={'version':'FUTURES_PAPER_V1','leverage':3,'initial_usdt':'10000','slots':10,'fee_rate':'0.0005','slippage_rate':'0.0002','maintenance_rate':'0.005','liquidation_fee_rate':'0.005','trailing_stop_price_pct':'0.02','max_spread_bps':'20','max_abs_funding_rate':'0.001','signal_interval':'1h','real_orders':False,'margin_mode':'ISOLATED','fees_and_liquidation':'EXPLICIT_MODEL_ASSUMPTIONS_NOT_ACCOUNT_SPECIFIC_EXCHANGE_RULES'}
NAMES=('BASELINE','SMA20_50','EMA12_26','RSI14','ZITAR_V1')
def number(v):
 x=D(str(v))
 if not x.is_finite():raise ValueError('NONFINITE_NUMBER')
 return x

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest()
def iso(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()
def day(ms):return datetime.fromtimestamp(ms/1000,TZ).date().isoformat()
def fresh(ms,universe):
 return dict(schema='ZITAR_FUTURES_PAPER_V1',policy=POLICY,policy_hash=digest(POLICY),started_ms=ms,heartbeat_ms=ms,state='INITIALIZED',universe=universe,last_candles={},books={name:dict(cash='10000',positions={},closed=[],funding_total='0',fees_total='0',equity='10000',realized='0',peak='10000',max_drawdown_pct='0',period=day(ms),period_start='10000',slot='1000',daily=[],quality=['PARTIAL_FIRST_DAY']) for name in NAMES},decisions=[],errors=[],authorities={'real_orders':False,'spot_write':False},limitations=['Komisyon, maintenance ve tasfiye oranlarÃ„Â± model varsayÃ„Â±mÃ„Â±dÃ„Â±r.','Tasfiye ve stop kontrolÃƒÂ¼ periyodik fiyat ÃƒÂ¶rneklerindedir; aradaki fiyat yolu bilinmez.','Sinyaller vadeli 1 saatlik kapanmÃ„Â±Ã…Å¸ mumlardan hesaplanÃ„Â±r; spot V3 iÃ…Å¸lemleri kopyalanmaz.','Ã„Â°lk gÃƒÂ¼n/hafta/ay kÃ„Â±smidir. USDT tutarlarÃ„Â± TRY hesaplarla doÃ„Å¸rudan karÃ…Å¸Ã„Â±laÃ…Å¸tÃ„Â±rÃ„Â±lmaz.'])
def pnl(p,price):return number(p['quantity'])*(number(price)-number(p['entry']))*p['direction']
def mark(book,quotes):
 total=number(book['cash']);up=D(0);margin=D(0)
 for symbol,p in book['positions'].items():
  q=quotes[symbol];u=pnl(p,q['mark']);p.update(mark=str(q['mark']),bid=str(q['bid']),ask=str(q['ask']),quote_ms=q['time'],unrealized=str(u));up+=u;margin+=number(p['margin']);total+=max(D(0),number(p['margin'])+u)
 if total<0:raise ValueError('NEGATIVE_EQUITY')
 book.update(equity=str(total),unrealized=str(up),margin=str(margin))
 peak=max(number(book['peak']),total);book['peak']=str(peak);book['max_drawdown_pct']=str(max(number(book['max_drawdown_pct']),(1-total/peak)*100 if peak else D(0)))
def open_position(book,symbol,direction,quote,contract,ms,reason):
 if book.get('entries_paused'):return 'ENTRIES_PAUSED'
 if book.get('reset_pending'):return 'RESET_PENDING'
 if book.get('retired_ms'):return 'RETIRED'
 if book.get('entries_disabled'):return 'ENTRIES_DISABLED_BY_REVIEW'
 if book.get('accounting_pending'):return 'ACCOUNTING_PENDING'
 if direction not in (-1,1):raise ValueError('INVALID_DIRECTION')
 if symbol in book['positions']:return 'ALREADY_OPEN'
 if len(book['positions'])>=POLICY['slots']:return 'MAX_POSITIONS'
 execution=book.get('execution_policy',POLICY);lev=number(execution['leverage']);fee=number(execution['fee_rate']);slip=number(execution['slippage_rate']);price=number(quote['ask' if direction==1 else 'bid'])*(1+slip*direction)
 budget=min(number(book['slot']),number(book['cash'])/(1+lev*fee))
 step=number(contract['step'])
 if step<=0:raise ValueError('INVALID_QUANTITY_STEP')
 qty=(budget*lev/price/step).to_integral_value(rounding=ROUND_DOWN)*step
 notional=qty*price
 if qty<=0 or qty<number(contract['min_qty']) or qty>number(contract['max_qty']) or notional<number(contract['min_notional']):return 'SIZE_FILTER'
 margin=notional/lev;charge=notional*fee
 book['cash']=str(number(book['cash'])-margin-charge);book['fees_total']=str(number(book['fees_total'])+charge)
 book['positions'][symbol]=dict(symbol=symbol,direction=direction,quantity=str(qty),entry=str(price),best_price=str(price),trailing_stop=str(price*(1-number(POLICY['trailing_stop_price_pct'])*direction)),margin=str(margin),initial_margin=str(margin),entry_fee=str(charge),funding='0',funding_events=[],opened_ms=ms,next_funding_ms=quote['next_funding'],reason=reason)
 return 'OPENED'
def close_position(book,symbol,quote,ms,reason):
 p=book['positions'][symbol];side=p['direction'];execution=book.get('execution_policy',POLICY);price=number(quote['bid' if side==1 else 'ask'])*(1-number(execution['slippage_rate'])*side)
 fee=number(p['quantity'])*price*(number(execution['fee_rate'])+(number(POLICY['liquidation_fee_rate']) if reason=='MODEL_LIQUIDATION' else D(0)))
 raw=number(p['margin'])+pnl(p,price)-fee;payout=max(D(0),raw)
 realized=payout-number(p['initial_margin'])-number(p['entry_fee'])
 book['cash']=str(number(book['cash'])+payout);book['fees_total']=str(number(book['fees_total'])+fee);book['realized']=str(number(book['realized'])+realized)
 book['closed'].append(dict(p,closed_ms=ms,exit=str(price),exit_fee=str(fee),net_pnl=str(realized),exit_reason=reason,uncovered_model_deficit=str(max(D(0),-raw))))
 del book['positions'][symbol]
def settle_funding(book,symbol,events,ms):
 p=book['positions'][symbol]
 for e in sorted(events,key=lambda x:x['fundingTime']):
  t=int(e['fundingTime'])
  if t<=p['opened_ms'] or t>ms or t in p['funding_events']:continue
  payment=-p['direction']*number(p['quantity'])*number(e['markPrice'])*number(e['fundingRate'])
  p['margin']=str(number(p['margin'])+payment);p['funding']=str(number(p['funding'])+payment);p['funding_events'].append(t);book['funding_total']=str(number(book['funding_total'])+payment)

def signals(candles,ms,interval_ms=3600000):
 rows=sorted([r for r in candles if int(r[6])<ms],key=lambda r:int(r[0]))
 if len(rows)<60:raise ValueError('INSUFFICIENT_CLOSED_CANDLES')
 rows=rows[-150:]
 if len({r[0] for r in rows})!=len(rows) or any(int(b[0])-int(a[0])!=interval_ms for a,b in zip(rows,rows[1:])):raise ValueError('CANDLE_GAP')
 if ms-int(rows[-1][6])>interval_ms:raise ValueError('STALE_CANDLES')
 c=[number(r[4]) for r in rows]
 if min(c)<=0:raise ValueError('INVALID_CANDLES')
 def direction(x):return 1 if x>0 else -1 if x<0 else 0
 def ema(n):
  value=c[0];alpha=D(2)/D(n+1)
  for x in c[1:]:value=alpha*x+(1-alpha)*value
  return value
 sma=direction(sum(c[-20:])/20-sum(c[-50:])/50);em=direction(ema(12)-ema(26))
 deltas=[b-a for a,b in zip(c[-15:],c[-14:])];gain=sum(max(D(0),x) for x in deltas);loss=sum(max(D(0),-x) for x in deltas)
 rsi=D(100) if loss==0 and gain>0 else D(50) if gain==loss==0 else 100-100/(1+gain/loss)
 rs=1 if rsi<30 else -1 if rsi>70 else 0
 votes=sma+em+rs;baseline=1 if votes>=2 else -1 if votes<=-2 else 0
 candidate=sma if sma==em and ((sma==1 and 45<=rsi<=70) or (sma==-1 and 30<=rsi<=55)) else 0
 return {'SMA20_50':sma,'EMA12_26':em,'RSI14':rs,'BASELINE':baseline,'ZITAR_V1':candidate,'candle_close_ms':int(rows[-1][6]),'rsi_simple':str(rsi)}

def apply_cycle(state,market,ms,signal_interval_ms=3600000):
 if state['policy_hash']!=digest(POLICY):raise ValueError('POLICY_CHANGED_NEW_EXPERIMENT_REQUIRED')
 from zitar_futures_shared_v1 import ensure_book, evaluate
 ensure_book(state,ms)
 from zitar_strategy_lab_v1 import ensure_experiment, summarize
 ensure_experiment(state,ms)
 from zitar_trigger_lab_v2 import ensure_trigger, report_trigger
 ensure_trigger(state,ms)
 from zitar_discovery_futures_v1 import ensure as ensure_discovery, evaluate as evaluate_discovery
 ensure_discovery(state,ms)
 from zitar_confluence_v1 import ensure as ensure_confluence, risk as confluence_risk, evaluate as evaluate_confluence, NAMES as CONFLUENCE_NAMES
 ensure_confluence(state,ms)
 from zitar_pivot_atr_v1 import ensure as ensure_pivot, evaluate as evaluate_pivot, NAMES as PIVOT_NAMES
 ensure_pivot(state,ms)
 for name,b in state['books'].items():
  if state.get('active_strategy_names') and name not in state['active_strategy_names']:b.setdefault('retired_ms',ms)
 errors=[];quotes={};valid={};closed_now=set()
 for symbol,data in market.items():
  try:
   q=data['quote']
   if not -5000<=ms-int(q['time'])<=30000 or not -5000<=ms-int(q['book_time'])<=30000:raise ValueError('STALE_QUOTE')
   if number(q['bid'])<=0 or number(q['ask'])<number(q['bid']) or number(q['mark'])<=0:raise ValueError('INVALID_QUOTE')
   quotes[symbol]=q;valid[symbol]=data
  except (KeyError,ValueError) as exc:errors.append(symbol+':'+str(exc))
 for name,book in state['books'].items():
  from zitar_futures_funding_recovery_v1 import reconcile_closed, update_pending
  reconcile_closed(book,valid,ms)
  book['accounting_pending']=any(p.get('funding_pending') for p in book['closed'])
  if ms-state['heartbeat_ms']>120000 and 'MONITORING_GAP' not in book['quality']:book['quality'].append('MONITORING_GAP')
  for symbol,p in list(book['positions'].items()):
   if symbol not in quotes:errors.append(symbol+':MISSING_POSITION_QUOTE');continue
   q=quotes[symbol];events=valid[symbol].get('funding',[])
   settle_funding(book,symbol,events,ms)
   update_pending(p,events,ms)
   if p.get('funding_pending'):
    errors.append(name+':'+symbol+':FUNDING_PENDING');book['accounting_pending']=True
   elif int(q['next_funding'])>ms:p['next_funding_ms']=int(q['next_funding'])
   value=number(p['margin'])+pnl(p,q['mark']);maintenance=number(p['quantity'])*number(q['mark'])*(number(POLICY['maintenance_rate'])+number(POLICY['liquidation_fee_rate']))
   if book.get('retired_ms') or book.get('reset_pending'):
    close_position(book,symbol,q,ms,'MODEL_LIQUIDATION' if value<=maintenance else ('USER_RESET' if book.get('reset_pending') else 'USER_STRATEGY_RETIRED'));closed_now.add((name,symbol));continue
   from zitar_profit_lock_v1 import update as update_profit_lock
   profit_hit=update_profit_lock(p,q,book.get('execution_policy',POLICY))
   if profit_hit:
    close_position(book,symbol,q,ms,'MODEL_LIQUIDATION' if value<=maintenance else 'PROFIT_LOCK_5PCT_80PCT');closed_now.add((name,symbol));continue
   if name in CONFLUENCE_NAMES or name in PIVOT_NAMES:
    if confluence_risk(book,symbol,q,ms,value,maintenance):closed_now.add((name,symbol))
    continue
   best=max(number(p.get('best_price',p['entry'])),number(q['mark'])) if p['direction']==1 else min(number(p.get('best_price',p['entry'])),number(q['mark']))
   stop=best*(1-number(POLICY['trailing_stop_price_pct'])*p['direction'])
   if p.get('profit_lock_active'):stop=max(stop,number(p['profit_lock_stop'])) if p['direction']==1 else min(stop,number(p['profit_lock_stop']))
   p.update(best_price=str(best),trailing_stop=str(stop))
   hit=number(q['mark'])<=stop if p['direction']==1 else number(q['mark'])>=stop
   reason='MODEL_LIQUIDATION' if value<=maintenance else 'TRAILING_STOP_2PCT' if hit else None
   if reason:
    close_position(book,symbol,q,ms,reason);closed_now.add((name,symbol))
  if not set(book['positions']).issubset(quotes):
   if 'MISSING_MARK_OR_FUNDING' not in book['quality']:book['quality'].append('MISSING_MARK_OR_FUNDING')
   continue
  mark(book,quotes)
  book['valuation_ms']=ms
  if book.get('accounting_pending') and 'FUNDING_PROVISIONAL' not in book['quality']:book['quality'].append('FUNDING_PROVISIONAL')
  today=day(ms)
  if today!=book['period']:
   book['daily'].append(dict(date=book['period'],start=book['period_start'],end=book['equity'],return_pct=str((number(book['equity'])/number(book['period_start'])-1)*100) if number(book['period_start']) else '0',quality=book['quality'],actual_rollover_ms=ms))
   book.update(period=today,period_start=book['equity'],slot=str(max(D(0),number(book['equity']))/10),quality=['MODEL_LIMITATIONS'])
 for symbol,data in valid.items():
  if symbol not in quotes:continue
  try:
   if symbol not in state['universe']:continue
   sig=signals(data['candles'],ms,signal_interval_ms);candle=sig['candle_close_ms'];old=state['last_candles'].get(symbol)
   if old is None or candle<=state['started_ms']:
    state['last_candles'][symbol]=candle;continue
   if candle<=old:continue
   if ms-candle>120000:
    state['last_candles'][symbol]=candle;state['decisions'].append(dict(ms=ms,symbol=symbol,result='SKIPPED_LATE_SIGNAL',reason='KapanÃ„Â±Ã…Å¸tan 120 saniyeden fazla gecikme'));continue
   q=quotes[symbol]
   for name,book in state['books'].items():
    if not set(book['positions']).issubset(quotes):continue
    if (name,symbol) in closed_now:continue
    if name not in NAMES or book.get('retired_ms'):continue
    target=sig[name];p=book['positions'].get(symbol)
    if p and p['direction']!=target:close_position(book,symbol,q,ms,'SIGNAL_CHANGED')
    reason='SIGNAL_'+str(target)
    if name=='ZITAR_V1' and target:
     spread=(number(q['ask'])-number(q['bid']))/((number(q['ask'])+number(q['bid']))/2)*10000
     if spread>number(POLICY['max_spread_bps']):target=0;reason='WIDE_SPREAD'
     elif abs(number(q['funding_rate']))>number(POLICY['max_abs_funding_rate']):target=0;reason='HIGH_FUNDING'
    outcome=open_position(book,symbol,target,q,data['contract'],ms,reason) if target else 'NO_ENTRY'
    state['decisions'].append(dict(ms=ms,book=name,symbol=symbol,candle_close_ms=candle,direction=target,reason=reason,result=outcome))
   state['last_candles'][symbol]=candle
  except (ValueError,KeyError) as exc:errors.append(symbol+':'+str(exc))
 evaluate(state,valid,quotes,ms,closed_now,errors)
 for experiment_name in ('ZITAR_CONTROL_V1','ZITAR_SELECTIVE_V1','ZITAR_CONTROL_V2','ZITAR_TRIGGER_V2'):
  evaluate(state,valid,quotes,ms,closed_now,errors,name=experiment_name)
 evaluate_discovery(state,valid,quotes,ms,closed_now,errors)
 evaluate_confluence(state,valid,quotes,ms,closed_now,errors)
 evaluate_pivot(state,valid,quotes,ms,closed_now,errors)
 for book in state['books'].values():
  if set(book['positions']).issubset(quotes):
   mark(book,quotes);book['valuation_ms']=ms
  if book.get('accounting_pending'):errors.append('ACCOUNTING_PENDING')
 state['strategy_lab']=summarize(state,ms,errors)
 state['trigger_lab']=report_trigger(state,ms,errors)
 state.update(heartbeat_ms=ms,state='DEGRADED' if errors else 'RUNNING',errors=errors)
 return state
