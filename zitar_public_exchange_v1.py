"""Isolated public order-book adapters for paper experiments. No credentials or orders."""
import json,ssl,time,urllib.request,urllib.parse,urllib.error
from decimal import Decimal

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('REDIRECT_BLOCKED')

class PublicExchange:
 def __init__(self,name):
  if name not in ('binance','bybit'):raise ValueError('UNSUPPORTED_EXCHANGE')
  self.name=name
  self.opener=urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
  self.next_request=0
 def orderbook(self,symbol):
  import re
  if not isinstance(symbol,str) or not re.fullmatch('[A-Z0-9]{3,24}',symbol):raise ValueError('INVALID_SYMBOL')
  if time.monotonic()<self.next_request:raise ValueError('RATE_LIMIT_BACKOFF')
  self.next_request=time.monotonic()+1
  if self.name=='binance':url='https://data-api.binance.vision/api/v3/depth?'+urllib.parse.urlencode(dict(symbol=symbol,limit=100))
  else:url='https://api.bybit.com/v5/market/orderbook?'+urllib.parse.urlencode(dict(category='spot',symbol=symbol,limit=50))
  try:
   with self.opener.open(urllib.request.Request(url,headers={'User-Agent':'ZITAR-Paper-Public/1','Accept':'application/json'}),timeout=8) as response:
    raw=response.read(1000001)
    if len(raw)>1000000:raise ValueError('RESPONSE_TOO_LARGE')
    data=json.loads(raw)
  except urllib.error.HTTPError as exc:
   if exc.code in (418,429):self.next_request=time.monotonic()+60
   raise ValueError('EXCHANGE_HTTP_'+str(exc.code)) from None
  if self.name=='bybit':
   if data.get('retCode')!=0:raise ValueError('EXCHANGE_REJECTED')
   data=dict(bids=data['result']['b'],asks=data['result']['a'])
  book={side:[[str(Decimal(str(p))),str(Decimal(str(q)))] for p,q,*rest in data[side]] for side in ('bids','asks')}
  for levels in book.values():
   if not levels:raise ValueError('EMPTY_BOOK')
   for p,q in levels:
    if not Decimal(p).is_finite() or not Decimal(q).is_finite() or Decimal(p)<=0 or Decimal(q)<0:raise ValueError('INVALID_BOOK')
  if Decimal(book['asks'][0][0])<Decimal(book['bids'][0][0]):raise ValueError('CROSSED_BOOK')
  return dict(book,exchange=self.name,symbol=symbol,received_ms=int(time.time()*1000),mode='PAPER',real_orders=False)
 def place_order(self,*args,**kwargs):raise PermissionError('REAL_ORDERS_DISABLED')
 def withdraw(self,*args,**kwargs):raise PermissionError('WITHDRAWALS_DISABLED')
