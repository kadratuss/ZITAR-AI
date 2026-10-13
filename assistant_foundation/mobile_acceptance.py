import urllib.request,urllib.error,json
for path,origin,expected in [('/api/chat-proxy/chat','http://127.0.0.1:8081',200),('/api/paper-control','http://127.0.0.1:8081',405),('/api/paper-reset','http://127.0.0.1:8081',405),('/api/chat-proxy/chat','https://example.com',403)]:
 req=urllib.request.Request('http://127.0.0.1:8081'+path,data=json.dumps(dict(question='Hesapla: 12 * 7 - 9',session_id='mobile-chat-acceptance')).encode(),headers={'Content-Type':'application/json','Origin':origin})
 try:r=urllib.request.urlopen(req,timeout=20)
 except urllib.error.HTTPError as e:r=e
 with r:
  raw=r.read();print(path,r.code);assert r.code==expected
  if expected==200:assert json.loads(raw)['answer']=='Sonuç: 75'
