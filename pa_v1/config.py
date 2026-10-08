from dataclasses import dataclass,asdict
from hashlib import sha256
import json,math
@dataclass(frozen=True)
class Config:
 strategy_id:str='ZITAR_PA_V1'
 mode:str='PAPER'
 market:str='SPOT'
 leverage:int=1
 short:bool=False
 regime_tf:str='1h'
 structure_tf:str='15m'
 entry_tf:str='5m'
 top_n:int=20
 history:int=80
 atr_period:int=14
 swing_left:int=2
 swing_right:int=2
 zone_atr:float=.35
 stop_atr:float=.3
 max_stop_atr:float=4.
 trend_touches:int=3
 volume_lookback:int=20
 volume_ratio:float=1.5
 min_score:float=75.
 min_rr:float=2.
 risk_per_trade:float=.0025
 max_daily_loss:float=.01
 max_consecutive_losses:int=3
 cap:int=10
 initial:float=10000.
 tp1_fraction:float=.3
 tp2_fraction:float=.4
 runner_atr:float=2.
 max_atr_pct:float=.08
 hammer_body:float=.35
 lower_shadow_body:float=2.
 upper_shadow_range:float=.2
 long_shadow:float=.65
 doji_body:float=.1
 star_body:float=.3
 min_body:float=.5
 max_signal_age_ms:int=120000
 daily_target:float=.03
 def validate(self):
  if any(isinstance(v,(int,float)) and not math.isfinite(v) for v in asdict(self).values()):raise ValueError('NONFINITE_CONFIG')
  if not 0<=self.min_score<=100 or self.min_rr<=0 or self.volume_ratio<=0 or self.initial<=0:raise ValueError('INVALID_CONFIG')
  if self.mode!='PAPER' or self.market!='SPOT' or self.leverage!=1 or self.short:raise ValueError('PAPER_MODE_NOT_CONFIRMED')
  if not 0<self.risk_per_trade<=self.max_daily_loss<1 or self.cap<1:raise ValueError('INVALID_RISK_CONFIG')
  if not 0<self.tp1_fraction<1 or not 0<self.tp2_fraction<1-self.tp1_fraction:raise ValueError('INVALID_PARTIALS')
  if min(self.swing_left,self.swing_right,self.trend_touches,self.atr_period,self.volume_lookback)<1:raise ValueError('INVALID_CONFIG')
  if self.history<max(self.atr_period,self.volume_lookback)+5:raise ValueError('INVALID_HISTORY')
  for tf in (self.regime_tf,self.structure_tf,self.entry_tf):duration(tf)
  return self
 def hash(self):return sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()
def duration(tf):return {'1m':60000,'5m':300000,'15m':900000,'1h':3600000,'4h':14400000}[tf]
