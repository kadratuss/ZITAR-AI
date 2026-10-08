"""Spot-only early movement observation. Hypothesis, not pump certainty."""
import statistics

def observe(rows,ms):
 bars=[r for r in rows if int(r[6])<ms]
 if len(bars)<25:return dict(stage='WAITING_DATA')
 last=bars[-1];prior=bars[-21:-1];close=float(last[4]);volume=float(last[5]);baseline=statistics.median(float(r[5]) for r in prior)
 ratio=volume/baseline if baseline>0 else 0
 buy=float(last[9])/volume if volume>0 and len(last)>9 else 0
 width=(max(float(r[2]) for r in prior[-5:])-min(float(r[3]) for r in prior[-5:]))/close
 move=(close/float(bars[-2][4])-1)*100
 return dict(candle_ms=int(last[6]),close=close,volume_ratio=ratio,buy_fraction=buy,range_pct=width*100,move_pct=move,ceiling=max(float(r[2]) for r in prior[-5:]),early=ratio>=1.5 and buy>=.6 and width<=.02 and 0<move<1)

def advance(previous,observation,ms):
 if 'candle_ms' not in observation:return dict(observation,updated_ms=ms)
 old=previous or {};o=dict(observation,updated_ms=ms)
 if old.get('stage')=='CONFIRMED' and observation['candle_ms']==old['candle_ms']:return dict(old,updated_ms=ms)
 if old.get('stage')=='EARLY' and ms-old['identified_ms']<=1800000:
  if observation['candle_ms']>old['candle_ms'] and observation['close']>old['ceiling'] and observation['buy_fraction']>=.6 and observation['volume_ratio']>=1.8:
   return dict(o,stage='CONFIRMED',identified_ms=old['identified_ms'],confirmed_ms=ms)
  return dict(old,updated_ms=ms,last_observation=observation)
 if observation.get('early'):return dict(o,stage='EARLY',identified_ms=ms)
 return dict(o,stage='WATCH')
