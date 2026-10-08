"""Candidate only: closed 5m pullback recovery confirmed by 1h trend. No order authority."""
def signal(previous_rsi, rsi, close, ema_fast, ema_slow, volume_ratio, spread_bps):
 values=[previous_rsi,rsi,close,ema_fast,ema_slow,volume_ratio,spread_bps]
 import math
 if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values):return 0
 if close<=0 or ema_fast<=0 or ema_slow<=0 or volume_ratio<1.2 or not 0<=spread_bps<=10:return 0
 if close>ema_fast>ema_slow and previous_rsi<=40<rsi<=60:return 1
 if close<ema_fast<ema_slow and previous_rsi>=60>rsi>=40:return -1
 return 0
