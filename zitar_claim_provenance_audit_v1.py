from __future__ import annotations
import json, re, urllib.request
from pathlib import Path
from datetime import datetime, timezone

BASE=Path(__file__).resolve().parent
URL="http://127.0.0.1:5016/api/chat"
OUT=BASE/"zitar_claim_provenance_audit_v1.json"

TESTS=[
 ("BTC hakkında şu an ne görüyorsun?","BTCTRY"),
 ("BTC hakkındaki görüşün değişti mi?","BTCTRY"),
 ("Bu haberler BTC'yi düşürdü mü?","BTCTRY"),
]

RULES=[
 ("DERIVED_ANALYSIS","zitar_mtf_research_v2.py",
  lambda s: any(x in s for x in ["kısa=","orta=","uzun=","zaman dilimleri","momentum"])),
 ("MEMORY","zitar_research_memory_v1.jsonl",
  lambda s: any(x in s for x in ["Memory v","BASELINE_ONLY","durable_change","görüş değiş"])),
 ("EXTERNAL_EVIDENCE","News Intelligence / Event Radar",
  lambda s: any(x in s for x in ["İlgili kayıt","Haber/fiyat","nedensellik","zamansal"])),
 ("INFERENCE","ZITAR Chat canonical synthesis",
  lambda s: any(x in s for x in ["Mevcut kanıt","Çelişkiler korunur","tahmini değildir"])),
]

def ask(q):
    b=json.dumps({"question":q,"use_qwen":True},ensure_ascii=False).encode()
    r=urllib.request.Request(URL,data=b,headers={"Content-Type":"application/json; charset=utf-8"},method="POST")
    with urllib.request.urlopen(r,timeout=120) as x:
        return json.loads(x.read().decode())

def main():
    registry=json.loads((BASE/"zitar_provenance_registry_v1.json").read_text(encoding="utf-8"))
    known={(x["category"],x["producer"]) for x in registry["entries"]}
    runs=[]; errors=[]
    for q,expected in TESTS:
        r=ask(q); ans=str(r.get("answer") or "")
        claims=[]
        for cat,producer,matcher in RULES:
            if matcher(ans):
                claims.append({"category":cat,"producer":producer,"supported":(cat,producer) in known})
        bad=[x for x in claims if not x["supported"]]
        if r.get("symbol")!=expected: errors.append(f"SYMBOL:{q}:{r.get('symbol')}")
        if not claims: errors.append(f"NO_PROVENANCE:{q}")
        if bad: errors.append(f"UNKNOWN_PRODUCER:{q}:{bad}")
        runs.append({
            "question":q,"symbol":r.get("symbol"),"intent":r.get("intent"),
            "mode":r.get("mode"),"guard":r.get("guard"),
            "claims":claims,"answer_sha256":__import__("hashlib").sha256(ans.encode()).hexdigest()
        })
        print("\nQUESTION:",q)
        print("symbol:",r.get("symbol"),"| intent:",r.get("intent"),"| mode:",r.get("mode"))
        for c in claims: print(" ",c["category"],"->",c["producer"],"|", "OK" if c["supported"] else "FAIL")
    payload={"schema":"ZITAR_CLAIM_PROVENANCE_AUDIT_V1","created_utc":datetime.now(timezone.utc).isoformat(),
             "tests":runs,"errors":errors}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print("\nerrors:",len(errors)); [print(" ",e) for e in errors]
    print("output:",OUT)
    print("STATUS:","PASS" if not errors else "FAIL")

if __name__=="__main__": main()
