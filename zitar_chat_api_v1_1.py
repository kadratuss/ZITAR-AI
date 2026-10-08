#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Chat API V1.1
Standalone READ-ONLY chat service for ZİTAR Control Center integration.

Port: 5014
Reads: zitar_chat_context_v1_2.json
Optional narrator: local Ollama qwen2.5:7b
Writes only: zitar_chat_api_audit_v1.jsonl
NEVER writes V3 state, NEVER places orders, NEVER mutates scheduler.
"""

import json, re, hashlib, urllib.request, unicodedata
from pathlib import Path
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

BASE = Path(__file__).resolve().parent
CONTEXT_FILE = BASE / "zitar_chat_context_v1_2.json"
AUDIT_FILE = BASE / "zitar_chat_api_audit_v1.jsonl"
HOST, PORT = "127.0.0.1", 5016
OLLAMA = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:7b"

HEADS = ["[ZITAR_RESEARCH]","[MEMORY]","[EVENT_NEWS]","[INFERENCE]","[UNCERTAINTY]","[KANIT_OZETI]"]

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def load_context():
    return json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))

def d0(sc, key):
    a = sc.get(key, [])
    return a[0].get("data", {}) if a and isinstance(a[0], dict) else {}

def aliases(symbols):
    out = {}
    for s in symbols:
        u=s.upper()
        out[u]=u
        if u.endswith("TRY"):
            asset=u[:-3]
            out[asset]=u
    out["BTC"]="BTCTRY"; out["BITCOIN"]="BTCTRY"
    out["ETH"]="ETHTRY"; out["ETHEREUM"]="ETHTRY"
    out["SOL"]="SOLTRY"; out["SOLANA"]="SOLTRY"
    out["DOGE"]="DOGETRY"; out["DOGECOIN"]="DOGETRY"
    return out

def detect_symbol(question, ctx, requested=None):
    symbols=list(ctx.get("symbol_context",{}))
    if requested:
        r=str(requested).upper().strip()
        if r in symbols: return r
    amap=aliases(symbols)
    q=question.upper()
    # exact pair first
    for k in sorted(amap, key=len, reverse=True):
        if re.search(r"(?<![A-Z0-9])"+re.escape(k)+r"(?![A-Z0-9])", q):
            return amap[k]
    return "BTCTRY" if "BTCTRY" in symbols else (symbols[0] if symbols else None)

def intent(question):
    q=question.lower()
    if any(x in q for x in ["almalı","satmalı","al mı","sat mı","buy","sell","işlem aç","pozisyon aç"]): return "TRADE_REQUEST"
    if any(x in q for x in ["sebep oldu","neden oldu","düşürdü mü","yükseltti mi","etkiledi mi","caused"]): return "CAUSALITY"
    if any(x in q for x in ["değişti mi","fikrin değiş","görüşün değiş","önceki","memory","hafıza"]): return "CHANGE"
    if any(x in q for x in ["haber","news","olay","event"]): return "NEWS"
    return "RESEARCH"

def evidence(ctx, sym):
    sc=ctx["symbol_context"][sym]
    r=d0(sc,"ZITAR_RESEARCH"); m=d0(sc,"MEMORY"); o=d0(sc,"AI_OPINION_HISTORY")
    c=r.get("contexts",{}); ag=r.get("cross_timeframe_agreement",{})
    mom=r.get("momentum_context",{}); conf=r.get("explicit_conflicts",[])
    obs=m.get("observation",{}); ch=m.get("change_from_previous",{})
    events=[]
    for rec in sc.get("EVENT_NEWS_EVIDENCE",[])[:6]:
        d=rec.get("data",{})
        events.append({
            "title":d.get("title"),
            "timing_class":(d.get("evidence") or {}).get("timing_class"),
            "pump_confirmed":d.get("pump_confirmed"),
            "buy_signal":d.get("buy_signal")
        })
    return {
      "symbol":sym,
      "short":(c.get("SHORT") or {}).get("observation"),
      "medium":(c.get("MEDIUM") or {}).get("observation"),
      "long":(c.get("LONG") or {}).get("observation"),
      "monthly":(c.get("MONTHLY_CONTEXT") or {}).get("observation"),
      "agreement":ag.get("level"),
      "conflicts":conf,
      "positive_momentum":mom.get("positive_timeframes",[]),
      "negative_momentum":mom.get("negative_timeframes",[]),
      "memory_version":m.get("symbol_version"),
      "change_type":ch.get("change_type"),
      "overall":obs.get("overall"),
      "data_confidence":o.get("data_confidence") or obs.get("confidence"),
      "view_state":o.get("view_state"),
      "change_state":o.get("change_state"),
      "durable_change_supported":o.get("durable_change_supported"),
      "events":events
    }

def conflict_text(e):
    if not e["conflicts"]: return "Belirgin explicit conflict kaydı yok."
    x=e["conflicts"][0]
    return f"{x.get('timeframe_a')}={x.get('observation_a')} ile {x.get('timeframe_b')}={x.get('observation_b')} arasında açık çatışma var."

def canonical(e, kind):
    first = ("Bu ilk/baseline kayıt; önceki sürüme göre görüş değişimi iddia edilemez."
             if e["change_state"]=="BASELINE_ONLY" or e["change_type"]=="INITIAL_OBSERVATION"
             else f"change_type={e['change_type']}; change_state={e['change_state']}; değişim yalnız versioned kayıt ölçüsünde yorumlanabilir.")
    titles=[x["title"] for x in e["events"] if x.get("title")][:3]
    news="; ".join(titles) if titles else "Bu sembol için mevcut context'te haber kanıtı yok."
    special=""
    if kind=="TRADE_REQUEST":
        special=" Bu sohbet katmanı BUY/SELL talimatı veya yatırım tavsiyesi üretmez; execution authority yoktur."
    elif kind=="CAUSALITY":
        special=" Haber ile piyasa hareketinin zamansal birlikteliği nedensellik kanıtı değildir."
    return f"""[ZITAR_RESEARCH]
{e['symbol']} için kısa={e['short']}, orta={e['medium']}, uzun={e['long']}, aylık bağlam={e['monthly']}. Zaman dilimleri arası uyum={e['agreement']}. {conflict_text(e)}
Pozitif momentum zaman dilimleri: {', '.join(e['positive_momentum']) or 'yok'}. Negatif momentum zaman dilimleri: {', '.join(e['negative_momentum']) or 'yok'}.

[MEMORY]
Memory v{e['memory_version']}; overall={e['overall']}; view={e['view_state']}; change={e['change_state']}; durable_change_supported={e['durable_change_supported']}.
{first}

[EVENT_NEWS]
İlgili kayıt örnekleri: {news}
Haber/fiyat ilişkisi yalnız zamansal kanıt olarak tutulur; nedensellik iddia edilmez.{special}

[INFERENCE]
Mevcut kanıt, araştırma durumunu betimler. Çelişkiler korunur; kanıtın desteklemediği tek yönlü sonuç üretilmez. Bu bir gelecek fiyat/getiri tahmini değildir.

[UNCERTAINTY]
Data confidence={e['data_confidence']} yalnız veri kalitesidir, tahmin güveni değildir. Haber birlikteliği nedensellik kanıtı değildir; versioned geçmiş sınırlıysa kalıcı görüş değişimi de iddia edilmez.

[KANIT_OZETI]
MTF Research + versioned Memory/Opinion + Event/News evidence. READ ONLY. Execution authority yok; gerçek emir yok; V3 write yok."""

SYSTEM="""ZİTAR'ın READ-ONLY Türkçe araştırma anlatıcısısın.
CANONICAL_ANSWER içindeki olguları değiştirme, yeni sayı/olgu ekleme, haber-fiyat nedenselliği kurma,
BUY/SELL tavsiyesi verme. Kullanıcının sorusuna doğal Türkçe ile cevap ver ama aşağıdaki altı etiketi
aynen birer kez ve sırayla koru:
[ZITAR_RESEARCH]
[MEMORY]
[EVENT_NEWS]
[INFERENCE]
[UNCERTAINTY]
[KANIT_OZETI]
Data confidence yalnız veri kalitesidir, tahmin güveni değildir."""

def narrate(canonical, question):
    body=json.dumps({
      "model":MODEL,"stream":False,
      "messages":[
        {"role":"system","content":SYSTEM},
        {"role":"user","content":"SORU:\n"+question+"\n\nCANONICAL_ANSWER:\n"+canonical}
      ],
      "options":{"temperature":0.0}
    },ensure_ascii=False).encode()
    req=urllib.request.Request(OLLAMA,data=body,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as r:
        return ((json.loads(r.read().decode()).get("message") or {}).get("content") or "").strip()

def _norm_text(x):
    x=unicodedata.normalize("NFKC",str(x or "")).lower()
    return x.replace("’","'").replace("‘","'").replace("–","-").replace("—","-")

def _money_facts(text):
    """Extract monetary amount+unit facts. Units are part of the fact, not decoration."""
    t=_norm_text(text)
    facts=set()
    # $84K, $280M, $16 billion
    for m in re.finditer(r"\$\s*(\d+(?:[.,]\d+)?)\s*(k|m|b|thousand|million|billion|bin|milyon|milyar)?",t,re.I):
        facts.add(("$",m.group(1).replace(",","."),(m.group(2) or "").lower()))
    # 84,000 TL / 84K USD / 280 million dollars etc.
    pat=r"(?<![\w$])(\d+(?:[.,]\d+)?)\s*(k|m|b|bin|milyon|milyar|thousand|million|billion)?\s*(tl|try|usd|dolar|dollar|dollars)\b"
    for m in re.finditer(pat,t,re.I):
        facts.add((m.group(3).lower(),m.group(1).replace(",","."),(m.group(2) or "").lower()))
    return facts

def _numbers(text):
    return set(re.findall(r"(?<![\w])\d+(?:[.,]\d+)?(?![\w])",_norm_text(text)))

def validate(a,e,canonical_text=None):
    reasons=[]
    positions=[]
    for h in HEADS:
        if a.count(h)!=1: reasons.append("SECTION_PROTOCOL")
        positions.append(a.find(h))
    if all(x>=0 for x in positions) and positions!=sorted(positions): reasons.append("SECTION_ORDER")
    low=_norm_text(a)
    for fact in [e["short"],e["medium"],e["long"],e["view_state"],e["change_state"]]:
        if fact is not None and _norm_text(fact) not in low:
            reasons.append("CORE_FACT_OMITTED:"+str(fact))
    if "nedensellik" not in low and "nedensel" not in low: reasons.append("CAUSALITY_LIMIT_OMITTED")
    if "tahmin güven" not in low: reasons.append("CONFIDENCE_LIMIT_OMITTED")
    if re.search(r"\b(satın al|alım fırsatı|satım fırsatı|yatırım tavsiyesi)\b",a,re.I):
        reasons.append("TRADING_LANGUAGE")

    # V1.1 factual-fidelity gate: narration cannot invent/relabel numbers or currencies.
    if canonical_text:
        allowed_money=_money_facts(canonical_text)
        answer_money=_money_facts(a)
        extra_money=answer_money-allowed_money
        if extra_money:
            reasons.append("MONEY_UNIT_FIDELITY:"+repr(sorted(extra_money)))

        allowed_nums=_numbers(canonical_text)
        answer_nums=_numbers(a)
        # Any new bare number is suspicious too; canonical evidence owns quantitative facts.
        extra_nums=answer_nums-allowed_nums
        if extra_nums:
            reasons.append("UNSUPPORTED_NUMBER:"+",".join(sorted(extra_nums)))

        # Explicit currency relabel guard even if punctuation/format differs.
        if re.search(r"\b(?:tl|try)\b",low):
            canon_low=_norm_text(canonical_text)
            if not re.search(r"\b(?:tl|try)\b",canon_low):
                reasons.append("CURRENCY_RELABEL_TRY")
    return sorted(set(reasons))

def audit(row):
    with AUDIT_FILE.open("a",encoding="utf-8") as f:
        f.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")

def answer(question, requested_symbol=None, use_qwen=True):
    ctx=load_context()
    sym=detect_symbol(question,ctx,requested_symbol)
    if not sym: raise ValueError("No symbols in context")
    kind=intent(question); ev=evidence(ctx,sym); can=canonical(ev,kind)
    raw=""; reasons=[]; err=None
    if use_qwen:
        try:
            raw=narrate(can,question); reasons=validate(raw,ev,can)
        except Exception as ex:
            err=str(ex); reasons=["QWEN_ERROR"]
    else:
        reasons=["QWEN_DISABLED"]
    final=raw if not reasons else can
    mode="QWEN_GROUNDED_PASS" if not reasons else "DETERMINISTIC_CANONICAL"
    rid=hashlib.sha256((utcnow()+question+sym).encode()).hexdigest()[:16]
    row={"utc":utcnow(),"request_id":rid,"symbol":sym,"intent":kind,"mode":mode,
         "qwen_reasons":reasons,"qwen_error":err,"execution_authority":False,
         "real_orders":False,"v3_write":False}
    audit(row)
    return {"ok":True,"request_id":rid,"symbol":sym,"intent":kind,"mode":mode,
            "answer":final,"guard":{"pass":not reasons,"reasons":reasons},
            "authority":{"execution":False,"real_orders":False,"v3_write":False}}

class H(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): pass
    def sendj(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(b)))
        self.send_header("Access-Control-Allow-Origin","http://127.0.0.1:5013")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","http://127.0.0.1:5013")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.end_headers()
    def do_GET(self):
        if self.path=="/api/chat/health":
            try:
                c=load_context()
                self.sendj({"ok":True,"service":"ZITAR_CHAT_API_V1_1","port":PORT,
                            "symbols":len(c.get("symbol_context",{})),"context_generated_utc":c.get("generated_utc"),
                            "model":MODEL,"execution_authority":False,"real_orders":False,"v3_write":False})
            except Exception as e:self.sendj({"ok":False,"error":str(e)},500)
        else:self.sendj({"ok":False,"error":"not_found"},404)
    def do_POST(self):
        if self.path!="/api/chat": return self.sendj({"ok":False,"error":"not_found"},404)
        try:
            n=int(self.headers.get("Content-Length","0")); data=json.loads(self.rfile.read(n) or b"{}")
            q=str(data.get("question","")).strip()
            if not q:return self.sendj({"ok":False,"error":"question_required"},400)
            self.sendj(answer(q,data.get("symbol"),bool(data.get("use_qwen",True))))
        except Exception as e:self.sendj({"ok":False,"error":str(e)},500)

if __name__=="__main__":
    if not CONTEXT_FILE.exists(): raise SystemExit(f"Missing {CONTEXT_FILE.name}")
    print("="*100)
    print("ZİTAR CHAT API V1")
    print(f"http://{HOST}:{PORT}")
    print("READ ONLY | EXECUTION AUTHORITY: NO | REAL ORDERS: NO | V3 WRITE: NO")
    print("GET  /api/chat/health")
    print("POST /api/chat")
    print("="*100)
    ThreadingHTTPServer((HOST,PORT),H).serve_forever()
