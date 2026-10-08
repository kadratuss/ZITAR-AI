"""HMAC key permission checks only. Fixed HTTPS hosts, redirects forbidden; no orders."""
import hashlib,hmac,json,time,urllib.request,urllib.parse,urllib.error,socket,ssl
from zitar_public_exchange_v1 import NoRedirect


SAFE_ERRORS={
 'CLOCK': 'EXCHANGE_CLOCK_SKEW · Borsa istek zamanını reddetti (-1021). Windows saatini eşitleyin.',
 'SIGNATURE': 'EXCHANGE_INVALID_SIGNATURE · İmza geçersiz (-1022). Anahtar ve secret eşleşmesini kontrol edin.',
 'KEY': 'EXCHANGE_KEY_IP_PERMISSION · Anahtar, izin verilen IP veya yetki reddedildi (-2015). Borsa bu üçünü ayırmıyor.',
 'FORMAT': 'EXCHANGE_KEY_FORMAT · Borsa anahtar biçimini reddetti (-2014).',
 'NETWORK': 'EXCHANGE_NETWORK_ERROR · Borsaya ağ bağlantısı kurulamadı.',
 'TIMEOUT': 'EXCHANGE_TIMEOUT · Borsa yanıtı zaman aşımına uğradı.',
 'TLS': 'EXCHANGE_TLS_ERROR · Güvenli bağlantı sertifikası doğrulanamadı.',
 'RATE': 'EXCHANGE_RATE_LIMIT · İstek sınırı veya geçici IP engeli; bekleyip tekrar deneyin.',
 'HTTP': 'EXCHANGE_HTTP_REJECTED · Borsa HTTP isteğini reddetti; bilinen hata kodu yok.',
 'RESPONSE': 'EXCHANGE_INVALID_RESPONSE · Beklenen borsa yanıtı alınamadı.',
 'BYBIT': 'BYBIT_REQUEST_REJECTED · Bybit isteği reddetti; okuma yetkisi henüz doğrulanamadı.'
}
def rejection(data):
 code=data.get('code') if isinstance(data,dict) else None
 return SAFE_ERRORS.get({-1021:'CLOCK',-1022:'SIGNATURE',-2015:'KEY',-2014:'FORMAT',-1003:'RATE'}.get(code,'')) if isinstance(code,int) else None

def verify(exchange,key,secret):
 timestamp=str(int(time.time()*1000));window='5000'
 if exchange=='binance':
  query=urllib.parse.urlencode(dict(timestamp=timestamp,recvWindow=window));signature=hmac.new(secret.encode(),query.encode(),hashlib.sha256).hexdigest()
  url='https://api.binance.com/sapi/v1/account/apiRestrictions?'+query+'&signature='+signature
  headers={'X-MBX-APIKEY':key}
 elif exchange=='bybit':
  signature=hmac.new(secret.encode(),(timestamp+key+window).encode(),hashlib.sha256).hexdigest()
  url='https://api.bybit.com/v5/user/query-api';headers={'X-BAPI-API-KEY':key,'X-BAPI-TIMESTAMP':timestamp,'X-BAPI-RECV-WINDOW':window,'X-BAPI-SIGN':signature}
 else:raise ValueError('UNSUPPORTED_EXCHANGE')
 try:
  with urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(url,headers=headers),timeout=8) as r:
   raw=r.read(65537)
   if len(raw)>65536:raise ValueError()
   data=json.loads(raw)
 except urllib.error.HTTPError as exc:
  try:
   raw=exc.read(65537);body=json.loads(raw) if len(raw)<=65536 else {}
  except Exception:body={}
  finally:exc.close()
  raise ValueError(rejection(body) or SAFE_ERRORS['RATE' if exc.code in (418,429) else 'HTTP']) from None
 except (TimeoutError,socket.timeout):raise ValueError(SAFE_ERRORS['TIMEOUT']) from None
 except urllib.error.URLError as exc:
  cause='TLS' if isinstance(exc.reason,ssl.SSLError) else 'TIMEOUT' if isinstance(exc.reason,(TimeoutError,socket.timeout)) else 'NETWORK'
  raise ValueError(SAFE_ERRORS[cause]) from None
 except Exception:raise ValueError(SAFE_ERRORS['RESPONSE']) from None
 if not isinstance(data,dict):raise ValueError(SAFE_ERRORS['RESPONSE'])
 error=rejection(data)
 if error:raise ValueError(error)
 if exchange=='binance' and isinstance(data.get('code'),int) and data['code']<0:raise ValueError(SAFE_ERRORS['HTTP'])
 if exchange=='bybit' and data.get('retCode')!=0:raise ValueError(SAFE_ERRORS['BYBIT'])
 if exchange=='binance':
  prohibited=['enableWithdrawals','enableInternalTransfer','permitsUniversalTransfer','enableMargin','enableFutures','enableVanillaOptions','enableFixApiTrade','enableSpotAndMarginTrading','enablePortfolioMarginTrading']
  if data.get('enableReading') is not True or any(data.get(k) is not False for k in prohibited):raise ValueError('REQUIRE_STRICT_READ_ONLY_KEY')
  if data.get('ipRestrict') is not True:raise ValueError('IP_ALLOWLIST_REQUIRED')
 else:
  d=data.get('result',{});perms=d.get('permissions',{})
  if data.get('retCode')!=0 or d.get('readOnly')!=1:raise ValueError('REQUIRE_STRICT_READ_ONLY_KEY')
  if any(x in {'Withdraw','AccountTransfer','SubMemberTransfer','SpotTrade','Order'} for v in perms.values() for x in v):raise ValueError('UNSAFE_PERMISSIONS')
  ips=d.get('ips',[])
  if not ips or '*' in ips or '0.0.0.0/0' in ips:raise ValueError('IP_ALLOWLIST_REQUIRED')
 return dict(status='READ_ONLY_VERIFIED',verified_ms=int(time.time()*1000),real_orders=False,withdrawals=False)
