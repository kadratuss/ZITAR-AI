from __future__ import annotations
import json, re, urllib.request
from pathlib import Path

BASE=Path(__file__).resolve().parent
PROJECT=BASE/"zitar_core_project_memory_v1.jsonl"
JOURNAL=BASE/"zitar_core_learning_journal_v1.jsonl"
FINANCE=BASE/"zitar_finance_unified_bridge_v1_1.json"
OUT=BASE/"zitar_unified_chat_finance_bridge_test_v1.json"
OLLAMA="http://127.0.0.1:11434/api/chat"
MODEL="qwen2.5:7b"
TR=str.maketrans({"ç":"c","ğ":"g","ı":"i","ö":"o","ş":"s","ü":"u","â":"a","î":"i","û":"u"})

def norm(s): return re.sub(r"\s+"," ",(s or "").casefold().translate(TR)).strip()
def load_jsonl(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def load_json(p): return json.loads(p.read_text(encoding="utf-8-sig"))

def route(q,state):
    t=norm(q)
    if "btc" in t or "bitcoin" in t: return "FINANCE_RESEARCH","FINANCE"
    if "model tren" in t: return "PROJECT_RECALL","MODEL_TRAIN"
    if state=="MODEL_TRAIN" and any(x in t for x in ("peki","neden","sirada","sonra")):
        return "PROJECT_RECALL","MODEL_TRAIN"
    return "CONVERSATION",state

def finance_render(b):
    e=b["evidence"]; t=b["temporal"]
    return (
      "BTCUSDT için mevcut doğrulanmış Finance ölçümleri:\n"
      f"- Funding: {e['funding']}\n"
      f"- Basis: {e['basis_bps']:.4f} bps\n"
      f"- OI 24 saat değişimi: %{e['oi24h_pct']:.4f}\n"
      f"- Long/Short hesap oranı: {e['long_short_ratio']}\n"
      f"- Taker buy/sell oranı: {e['taker_ratio']}.\n"
      f"Temporal değerlendirme için yalnızca {t.get('observations')} gözlem var; "
      f"durum {t.get('status')}. Agreement {b.get('agreement')} ve kaynak sonucu "
      f"{b.get('source_conclusion')}. Bu nedenle mevcut kanıttan yönsel sonuç "
      "veya işlem sinyali çıkarmıyorum."
    )

def project_context(q,rows):
    hits=[x for x in rows if x.get("project")=="MODEL_TRAIN"]
    t=norm(q)
    if "neden" in t:
        hits=[x for x in hits if x.get("memory_type")=="SENSOR_RULE"]
    elif any(x in t for x in ("sirada","sonra")):
        hits=[x for x in hits if x.get("memory_type") in ("PROJECT_MILESTONE","CONTROL_ARCHITECTURE")]
    else:
        hits=[x for x in hits if x.get("memory_type")=="PROJECT_MILESTONE"]
    return "\n".join(x["content"] for x in hits)

def qwen(q,ctx):
    system="""Sen ZITAR'sın. Yalnızca verilen proje hafızasına dayanarak kısa ve düzgün Türkçe cevap ver.
Teknik terimleri doğru kullan: turnout=makas, route logic=rota mantığı, magnet=mıknatıs.
Yeni olgu uydurma."""
    data=json.dumps({"model":MODEL,"stream":False,"messages":[
      {"role":"system","content":system},
      {"role":"user","content":f"PROJE HAFIZASI:\n{ctx}\n\nSORU:\n{q}"}
    ],"options":{"temperature":0.1}},ensure_ascii=False).encode()
    req=urllib.request.Request(OLLAMA,data=data,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as r:
        return json.loads(r.read().decode())["message"]["content"].strip()

def main():
    project=load_jsonl(PROJECT); finance=load_json(FINANCE)
    turns=[
      "Model tren projesinde en son ne yapmıştık?",
      "Peki neden iki sensör kullanıyorduk?",
      "Bu arada BTC hakkında şu an ne görüyorsun?"
    ]
    state=None; results=[]
    for q in turns:
        r,d=route(q,state)
        if r=="FINANCE_RESEARCH":
            a=finance_render(finance); source="FINANCE_DETERMINISTIC_RENDERER"
        elif r=="PROJECT_RECALL":
            a=qwen(q,project_context(q,project)); source="PROJECT_MEMORY_QWEN"
        else:
            a="Buradayım."; source="CORE"
        low=norm(a)
        ok=True
        if r=="FINANCE_RESEARCH":
            ok=(finance.get("status")=="EVIDENCE_AVAILABLE"
                and finance["policy"]["directional_allowed"] is False
                and "yon" in low and "sinyali cikarmiyorum" in low
                and not any(x in low for x in ("bullish","bearish","fiyat duser","fiyat yukselir")))
        results.append({"question":q,"route":r,"domain":d,"source":source,"answer":a,"pass":ok})
        print(("PASS" if ok else "FAIL"),f"| {r:<16} source={source:<30} | {q}")
        print("  ZITAR:",a)
        state=d
    passed=sum(x["pass"] for x in results)
    OUT.write_text(json.dumps({"schema":"ZITAR_UNIFIED_CHAT_FINANCE_BRIDGE_TEST_V1",
      "results":results,"passed":passed,"total":len(results)},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"\nRESULT: {passed}/{len(results)}")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(results) else "FAIL")

if __name__=="__main__": main()
