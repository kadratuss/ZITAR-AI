import math,hashlib,json
from .config import duration

def candles(raw,ms,tf,c):
 step=duration(tf);rows=sorted([r for r in raw if len(r)>=7 and int(r[6])<ms],key=lambda r:int(r[0]))[-max(c.history,120):]
 if len(rows)<c.history:raise ValueError('INSUFFICIENT_HISTORY')
 out=[]
 for r in rows:
  t=int(r[0]);end=int(r[6]);o,h,l,cl,v=map(float,r[1:6])
  if t%step or end!=t+step-1 or not all(math.isfinite(x) for x in (o,h,l,cl,v)) or min(o,h,l,cl)<=0 or v<0 or not l<=min(o,cl)<=max(o,cl)<=h:raise ValueError('INVALID_OHLCV')
  out.append(dict(t=t,end=end,o=o,h=h,l=l,c=cl,v=v))
 if any(b['t']-a['t']!=step for a,b in zip(out,out[1:])):raise ValueError('CANDLE_GAP')
 if ms-out[-1]['end']>step:raise ValueError('STALE_DATA')
 return out

def atr(rows,n):
 tr=[max(r['h']-r['l'],abs(r['h']-rows[i-1]['c']),abs(r['l']-rows[i-1]['c'])) for i,r in enumerate(rows) if i]
 return sum(tr[-n:])/n

def swings(rows,c):
 out=[]
 for i in range(c.swing_left,len(rows)-c.swing_right):
  r=rows[i];others=rows[i-c.swing_left:i]+rows[i+1:i+c.swing_right+1]
  for key,kind in [('h','HIGH'),('l','LOW')]:
   if all(r[key]>x[key] if kind=='HIGH' else r[key]<x[key] for x in others):out.append(dict(kind=kind,price=r[key],timestamp=r['end'],confirmed_at=rows[i+c.swing_right]['end'],index=i))
 return out

def structure(rows,c):
 ss=swings(rows,c);hi=[s for s in ss if s['kind']=='HIGH'];lo=[s for s in ss if s['kind']=='LOW'];a=atr(rows,c.atr_period);tol=a*c.zone_atr
 hh=len(hi)>=2 and hi[-1]['price']>hi[-2]['price']+tol;hl=len(lo)>=2 and lo[-1]['price']>lo[-2]['price']+tol
 lh=len(hi)>=2 and hi[-1]['price']<hi[-2]['price']-tol;ll=len(lo)>=2 and lo[-1]['price']<lo[-2]['price']-tol
 state='BULLISH' if hh and hl else 'BEARISH' if lh and ll else 'RANGE' if len(hi)>=2 and len(lo)>=2 else 'UNKNOWN'
 broken=bool(hi and rows[-2]['c']<=hi[-1]['price']<rows[-1]['c'])
 zones=[dict(kind=s['kind'],low=s['price']-tol,high=s['price']+tol,center=s['price'],timestamp=s['timestamp'],confirmed_at=s['confirmed_at']) for s in ss[-16:]]
 return dict(state=state,swings=ss,higher_high=hh,higher_low=hl,lower_high=lh,lower_low=ll,structure_break=broken,possible_change_of_character=broken and state=='BEARISH',zones=zones,atr=a,timestamp=rows[-1]['end'])

def trendline(st,rows,c):
 lows=[s for s in st['swings'] if s['kind']=='LOW'][-c.trend_touches:]
 if len(lows)<c.trend_touches:return dict(state='INVALID')
 first,last=lows[0],lows[-1];slope=(last['price']-first['price'])/(last['index']-first['index'])
 if slope<=0:return dict(state='INVALID')
 at=lambda i:first['price']+slope*(i-first['index']);tol=st['atr']*c.zone_atr
 if any(abs(s['price']-at(s['index']))>tol for s in lows):return dict(state='INVALID')
 level=at(len(rows)-1)
 return dict(state='BROKEN' if any(r['c']<at(i)-tol for i,r in enumerate(rows) if i>=first['index']) else 'SUPPORT',level=level,slope=slope,touches=len(lows))

def patterns(rows,support,c):
 x=rows[-1];p=rows[-2];f=rows[-3];rg=x['h']-x['l'];body=abs(x['c']-x['o']);lower=min(x['o'],x['c'])-x['l'];upper=x['h']-max(x['o'],x['c']);bull=x['c']>x['o'];fr=f['h']-f['l'];pr=p['h']-p['l'];pb=abs(p['c']-p['o'])
 tests={'HAMMER':rg>0 and body>0 and body/rg<=c.hammer_body and lower>=c.lower_shadow_body*body and upper/rg<=c.upper_shadow_range,
 'LONG_LOWER_SHADOW':rg>0 and lower/rg>=c.long_shadow,
 'BULLISH_ENGULFING':bull and p['c']<p['o'] and x['o']<=p['c'] and x['c']>=p['o'],
 'MORNING_STAR':fr>0 and f['c']<f['o'] and abs(f['c']-f['o'])/fr>=c.min_body and pr>0 and pb/pr<=c.star_body and bull and x['c']>(f['o']+f['c'])/2 and min(p['o'],p['c'])<=f['c'],
 'MORNING_DOJI_STAR':fr>0 and f['c']<f['o'] and pr>0 and pb/pr<=c.doji_body and bull and x['c']>(f['o']+f['c'])/2 and min(p['o'],p['c'])<=f['c'],
 'PIERCING_LINE':p['c']<p['o'] and bull and x['o']<=p['c'] and (p['o']+p['c'])/2<x['c']<p['o'],
 'TWEEZER_BOTTOM':p['c']<p['o'] and bull and abs(p['l']-x['l'])<=atr(rows,c.atr_period)*c.zone_atr}
 return [dict(pattern_name=k,timestamp=x['end'],valid=bool(v and support),reason='CONFIRMED' if v and support else 'NO_SUPPORT_CONTEXT' if v else 'PATTERN_NOT_MATCHED',components=dict(body=body,range=rg,lower_shadow=lower,upper_shadow=upper),context={'at_support':support}) for k,v in tests.items()]

def evaluate(symbol,raw,ms,c):
 result=dict(strategy_id=c.strategy_id,symbol=symbol,decision='NO_TRADE',reasons=[])
 try:
  c.validate();r=candles(raw[c.regime_tf],ms,c.regime_tf,c);s=candles(raw[c.structure_tf],ms,c.structure_tf,c);e=candles(raw[c.entry_tf],ms,c.entry_tf,c)
 except (ValueError,KeyError,TypeError) as exc:result['reasons']=[str(exc)];return result
 if ms-e[-1]['end']>c.max_signal_age_ms:result['reasons']=['STALE_SIGNAL'];return result
 rs=structure(r,c);st=structure(s,c);a=atr(e,c.atr_period);x=e[-1];price=x['c'];regime={'BULLISH':'UPTREND','BEARISH':'DOWNTREND','RANGE':'RANGE','UNKNOWN':'UNCERTAIN'}[rs['state']]
 result.update(regime=regime,structure=st,signal_timestamp=x['end'],atr=a,trendline=trendline(st,s,c))
 if regime in ('DOWNTREND','UNCERTAIN'):result['reasons']=['BEARISH_REGIME' if regime=='DOWNTREND' else 'REGIME_UNKNOWN'];return result
 if a<=0 or a/price>c.max_atr_pct:result['reasons']=['ABNORMAL_VOLATILITY'];return result
 lows=[z for z in st['swings'] if z['kind']=='LOW'];highs=[z for z in st['swings'] if z['kind']=='HIGH'];tol=a*c.zone_atr
 support=max([z['price'] for z in lows if z['price']<=price]+[0]);near=bool(support and x['l']<=support+tol and x['c']>=support)
 pat=patterns(e,near,c);trigger=next((p['pattern_name'] for p in pat if p['valid']),None);setup=None;level=support;event=None
 # Retest requires an earlier CLOSED entry bar above an already-confirmed level.
 for h in reversed(highs):
  prior=[v for v in e[-9:-1] if v['end']>h['confirmed_at'] and v['c']>h['price']+tol]
  if prior and x['l']<=h['price']+tol and x['c']>h['price'] and regime=='UPTREND':setup='BREAKOUT_RETEST';level=h['price'];event=h['timestamp'];near=True;break
 if len(lows)>=2:
  l1,l2=lows[-2:];between=[h for h in highs if l1['timestamp']<h['timestamp']<l2['timestamp']]
  if between and l2['index']-l1['index']>=3 and abs(l1['price']-l2['price'])<=st['atr']*c.zone_atr:
   neck=max(h['price'] for h in between)
   if e[-2]['c']<=neck<x['c']:setup='DOUBLE_BOTTOM_BREAKOUT';level=min(l1['price'],l2['price']);event=l2['timestamp'];near=True;result['neckline']=neck
 if not setup and near and regime=='UPTREND' and st['state']=='BULLISH':setup='TREND_PULLBACK';event=lows[-1]['timestamp']
 if not setup and near and trigger and regime=='RANGE':setup='BULLISH_REVERSAL_AT_SUPPORT';event=lows[-1]['timestamp']
 if setup in ('BREAKOUT_RETEST','DOUBLE_BOTTOM_BREAKOUT') and x['c']>x['o'] and x['h']>x['l'] and (x['h']-x['c'])/(x['h']-x['l'])<=.25:trigger='BULLISH_CLOSE_CONFIRMATION'
 avg=sum(v['v'] for v in e[-c.volume_lookback-1:-1])/c.volume_lookback
 vr=x['v']/avg if avg>0 else 0;stop=level-a*c.stop_atr;R=price-stop
 resistance=min([h['price'] for h in highs if h['price']>price]+[float('inf')]);rr=(resistance-price)/R if R>0 else 0
 reasons=[]
 if not setup:reasons.append('NO_SETUP')
 if not trigger:reasons.append('NO_CONTEXT_TRIGGER')
 if vr<c.volume_ratio:reasons.append('VOLUME_TOO_LOW')
 if not 0<stop<price or R>a*c.max_stop_atr:reasons.append('STOP_INVALID')
 if not math.isfinite(rr) or rr<c.min_rr:reasons.append('INSUFFICIENT_RR')
 components=dict(regime=25 if regime=='UPTREND' else 15,structure=20 if st['state']=='BULLISH' or setup in ('DOUBLE_BOTTOM_BREAKOUT','BREAKOUT_RETEST') else 10,trigger=20 if trigger else 0,volume=20 if vr>=c.volume_ratio else 0,risk_reward=15 if math.isfinite(rr) and rr>=c.min_rr else 0)
 score=sum(components.values())
 if score<c.min_score:reasons.append('SCORE_TOO_LOW')
 result.update(setup_type=setup,trigger=trigger,patterns=pat,volume_ratio=vr,volume_expansion=vr,volume_contraction=sum(v['v'] for v in e[-4:-1])/3/avg if avg else None,support=level,resistance=resistance if math.isfinite(resistance) else None,stop_price=stop,R=R,targets=[price+R,price+2*R],expected_RR=rr if math.isfinite(rr) else None,PA_SCORE=score,score_components=components,breakout_quality=min(100,max(0,(price-level)/a*25)+min(50,vr*20)),structural_event=event,reasons=reasons)
 result['signal_id']=hashlib.sha256(json.dumps([c.strategy_id,symbol,c.entry_tf,setup,x['end'],event]).encode()).hexdigest()
 result['decision']='PAPER_BUY' if not reasons else 'NO_TRADE'
 return result
