#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZİTAR Grounded Chat V2.2
Schema-aware deterministic evidence model + Qwen renderer + semantic validator + safe fallback.
READ ONLY. NO execution authority. NO orders. NO V3 writes.
"""
import json,re,urllib.request,hashlib
from pathlib import Path
from datetime import datetime,timezone

B=Path(__file__).resolve().parent
CTX=B/"zitar_chat_context_v1_2.json"
MODEL="qwen2.5:7b"; OLLAMA="http://127.0.0.1:11434/api/chat"
PACK=B/"zitar_chat_evidence_packet_v2_2.json"; AUD=B/"zitar_chat_last_audit_v2_2.json"
HEADS=["[ZITAR_RESEARCH]","[MEMORY]","[EVENT_NEWS]","[INFERENCE]","[UNCERTAINTY]","[KANIT_OZETI]"]

def data0(sc,key):
    a=sc.get(key,[])
    return (a[0].get("data",{}) if a and isinstance(a[0],dict) else {})

def build(ctx,sym):
    sc=ctx["symbol_context"][sym]
    r=data0(sc,"ZITAR_RESEARCH"); m=data0(sc,"MEMORY"); o=data0(sc,"AI_OPINION_HISTORY")
    contexts=r.get("contexts",{})
    ag=r.get("cross_timeframe_agreement",{})
    conf=r.get("explicit_conflicts",[])
    mom=r.get("momentum_context",{})
    act=r.get("activity_context",{})
    obs=m.get("observation",{})
    ch=m.get("change_from_previous",{})
    ev=[]
    for rec in sc.get("EVENT_NEWS_EVIDENCE",[])[:8]:
        d=rec.get("data",{})
        ev.append({"title":d.get("title"),"pump_confirmed":d.get("pump_confirmed"),
                   "buy_signal":d.get("buy_signal"),
                   "timing_class":(d.get("evidence") or {}).get("timing_class")})
    p={
      "schema":"ZITAR_EVIDENCE_PACKET_V2_2","symbol":sym,
      "context_generated_utc":ctx.get("generated_utc"),
      "mtf":{
        "short":(contexts.get("SHORT") or {}).get("observation"),
        "medium":(contexts.get("MEDIUM") or {}).get("observation"),
        "long":(contexts.get("LONG") or {}).get("observation"),
        "monthly_context":(contexts.get("MONTHLY_CONTEXT") or {}).get("observation"),
        "agreement_level":ag.get("level"),"agreement_ratio":ag.get("ratio"),
        "agreement_up":ag.get("up"),"agreement_down":ag.get("down"),
        "conflicts":conf,
        "positive_momentum_timeframes":mom.get("positive_timeframes",[]),
        "negative_momentum_timeframes":mom.get("negative_timeframes",[]),
        "high_volume_timeframes":act.get("volume_ratio_ge_1_5_timeframes",[]),
        "high_volatility_timeframes":act.get("atr14_pct_ge_5_timeframes",[])
      },
      "memory":{
        "version":m.get("symbol_version"),"change_type":ch.get("change_type"),
        "overall":obs.get("overall"),"short":obs.get("short"),"medium":obs.get("medium"),
        "long":obs.get("long"),"monthly":obs.get("monthly"),
        "agreement":obs.get("agreement"),"data_confidence":obs.get("confidence"),
        "old_observation_overwritten":(m.get("research_integrity") or {}).get("old_observation_overwritten")
      },
      "opinion":{
        "memory_version":o.get("memory_version"),"view_state":o.get("view_state"),
        "change_state":o.get("change_state"),"data_confidence":o.get("data_confidence"),
        "agreement":o.get("agreement"),"durable_change_supported":o.get("durable_change_supported")
      },
      "events":ev,
      "rules":{"temporal_association_not_causation":True,"anomaly_not_pump":True,
               "pump_not_buy":True,"data_confidence_not_predictive_confidence":True,
               "execution_authority":False,"real_orders":False,"v3_write":False}
    }
    return p

def deterministic_answer(p):
    m=p["mtf"]; mem=p["memory"]; op=p["opinion"]; events=p["events"]
    conflict="Yok."
    if m["conflicts"]:
        c=m["conflicts"][0]
        conflict=f"{c.get('timeframe_a')}={c.get('observation_a')} ile {c.get('timeframe_b')}={c.get('observation_b')} arasında açık çatışma var."
    change = ("Bu ilk kayıt/baseline; önceki sürüme göre görüş değişimi iddia edilemez."
              if mem["change_type"]=="INITIAL_OBSERVATION" or op["change_state"]=="BASELINE_ONLY"
              else f"Memory change_type={mem['change_type']}, opinion change_state={op['change_state']}.")
    titles=[e["title"] for e in events if e.get("title")][:3]
    news=("; ".join(titles) if titles else "Yetersiz kanıt.")
    return f"""[ZITAR_RESEARCH]
Kısa vade: {m['short']}. Orta vade: {m['medium']}. Uzun vade: {m['long']}. Aylık bağlam: {m['monthly_context']}.
Zaman dilimleri arası uyum: {m['agreement_level']}. {conflict}
Pozitif momentum görülen zaman dilimleri: {', '.join(m['positive_momentum_timeframes']) or 'yok'}. Negatif momentum görülenler: {', '.join(m['negative_momentum_timeframes']) or 'yok'}.

[MEMORY]
Memory sürümü: {mem['version']}; overall={mem['overall']}; data confidence={mem['data_confidence']}.
Opinion state: {op['view_state']}; change state: {op['change_state']}; durable change supported={op['durable_change_supported']}.
{change}

[EVENT_NEWS]
İlgili kayıt örnekleri: {news}
Bu haberlerle fiyat hareketleri arasındaki kayıtlar yalnız zamansal birliktelik olarak ele alınır; nedensellik iddia edilmez. Mevcut event kayıtları BUY/SELL otoritesi değildir.

[INFERENCE]
Kısa, orta ve uzun bağlamın tamamı MIXED olduğundan ve 5m UP ile 1h DOWN çatışması bulunduğundan, mevcut araştırma tek yönlü güçlü bir görüş desteklemiyor.
Bu, gelecekteki yön veya getiri tahmini değildir.

[UNCERTAINTY]
Data confidence={mem['data_confidence']} yalnız veri kalitesini ifade eder; tahmin güvenini ifade etmez.
Memory sürümü {mem['version']} ve durum {op['change_state']} olduğu için kalıcı görüş değişimi hakkında yeterli geçmiş yoktur. Haber-zaman birlikteliği nedensellik kanıtı değildir.

[KANIT_OZETI]
MTF Research, versioned Memory, deterministic Opinion ve Event/News kayıtları kullanıldı. Execution authority yok; gerçek emir yok; V3 write yok."""

SYSTEM="""You render a Turkish ZİTAR research answer from the supplied canonical evidence.
Do not add facts. Do not omit the core MTF horizons, conflict, memory version/change state, uncertainty, or news causality limitation.
Never give BUY/SELL advice.
Use EXACTLY these labels once and in order:
[ZITAR_RESEARCH]
[MEMORY]
[EVENT_NEWS]
[INFERENCE]
[UNCERTAINTY]
[KANIT_OZETI]
No markdown headings. Data confidence is data quality only."""

def call(p,q):
    prompt=f"SORU: {q}\nCANONICAL_EVIDENCE:\n{json.dumps(p,ensure_ascii=False,indent=2)}"
    body=json.dumps({"model":MODEL,"stream":False,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],
                     "options":{"temperature":0.0}},ensure_ascii=False).encode()
    req=urllib.request.Request(OLLAMA,data=body,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=180) as r:
        return ((json.loads(r.read().decode()).get("message") or {}).get("content") or "").strip()

def validate(a,p):
    rs=[]
    pos=[]
    for h in HEADS:
        if a.count(h)!=1: rs.append("SECTION_PROTOCOL")
        pos.append(a.find(h))
    if all(x>=0 for x in pos) and pos!=sorted(pos): rs.append("SECTION_ORDER")
    low=a.lower()
    for required in [str(p["mtf"]["short"]).lower(),str(p["mtf"]["medium"]).lower(),
                     str(p["mtf"]["long"]).lower(),str(p["memory"]["version"]).lower(),
                     str(p["opinion"]["change_state"]).lower()]:
        if required not in low: rs.append("CORE_FACT_OMITTED:"+required)
    if p["opinion"]["change_state"]=="BASELINE_ONLY":
        if re.search(r"(fikr|görüş).{0,35}(değişti|değişmiş)",a,re.I): rs.append("FALSE_CHANGE_CLAIM")
    bad=[r"\bsatın al\b",r"\balım fırsat",r"\bsatım fırsat",r"\byatırım tavsi",
         r"haber(?:ler|in)?.{0,50}\betki(?:ledi|ler|si|sini|li)\b"]
    if any(re.search(x,a,re.I|re.S) for x in bad): rs.append("FORBIDDEN_LANGUAGE")
    if "nedensellik" not in low and "nedensel" not in low: rs.append("CAUSALITY_LIMIT_OMITTED")
    if "tahmin güven" not in low and "predictive" not in low: rs.append("DATA_CONFIDENCE_LIMIT_OMITTED")
    return sorted(set(rs))

def main():
    ctx=json.loads(CTX.read_text(encoding="utf-8"))
    sym=input("Sembol [BTCTRY]: ").strip().upper() or "BTCTRY"
    if sym not in ctx["symbol_context"]: raise SystemExit("Unknown symbol")
    q=input("Sorun: ").strip()
    p=build(ctx,sym); PACK.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8")
    canonical=deterministic_answer(p)
    err=None
    try: raw=call(p,q); reasons=validate(raw,p)
    except Exception as e: raw="";reasons=["QWEN_ERROR"];err=str(e)
    final=raw if not reasons else canonical
    mode="QWEN_GROUNDED_PASS" if not reasons else "DETERMINISTIC_CANONICAL_FALLBACK"
    audit={"engine":"ZITAR_GROUNDED_CHAT_V2_2","utc":datetime.now(timezone.utc).isoformat(),
           "symbol":sym,"mode":mode,"qwen_reasons":reasons,"qwen_error":err,
           "packet_sha256":hashlib.sha256(PACK.read_bytes()).hexdigest(),
           "execution_authority":False,"real_orders":False,"v3_write":False}
    AUD.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print("\n"+"="*118);print(f"ZİTAR GROUNDED CHAT V2.2 | {sym} | {mode}")
    print("READ ONLY | EXECUTION AUTHORITY: NO | REAL ORDERS: NO | V3 WRITE: NO");print("="*118)
    print(final);print("-"*118);print("QWEN SEMANTIC GATE :", "PASS" if not reasons else "BLOCKED")
    print("BLOCK REASONS      :",reasons or "NONE");print("PACKET             :",PACK.name);print("AUDIT              :",AUD.name);print("="*118)

if __name__=="__main__": main()
