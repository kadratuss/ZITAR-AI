from __future__ import annotations
import json, urllib.request
from pathlib import Path

BASE=Path(__file__).resolve().parent
BRIDGE=BASE/"zitar_finance_unified_bridge_v1_1.json"
OUT=BASE/"zitar_finance_qwen_synthesis_test_v1_1.json"
OLLAMA="http://127.0.0.1:11434/api/chat"
MODEL="qwen2.5:7b"

def load():
    return json.loads(BRIDGE.read_text(encoding="utf-8-sig"))

def ask_qwen(bundle):
    ev=bundle["evidence"]; t=bundle["temporal"]; pol=bundle["policy"]
    facts=f"""BTCUSDT doğrulanmış Finance evidence:
funding={ev['funding']}
basis_bps={ev['basis_bps']}
oi24h_pct={ev['oi24h_pct']}
long_short_ratio={ev['long_short_ratio']}
taker_ratio={ev['taker_ratio']}
temporal_status={t.get('status')}
observations={t.get('observations')}
agreement={bundle.get('agreement')}
source_conclusion={bundle.get('source_conclusion')}
directional_allowed={pol.get('directional_allowed')}
"""
    system="""Sen ZITAR Finance Specialist'ın konuşma sentez katmanısın.
Yalnızca verilen kanıta dayan. Eksik veri uydurma.
LONG/SHORT, al/sat veya yükselir/düşer sonucu üretme; directional_allowed=False ise yön sonucu çıkarmak kesinlikle yasaktır.
Funding, basis, OI, long/short account ratio ve taker buy/sell ratio tek başına işlem sinyali değildir.
Bu ölçümlerden fiyatın düşme/yükselme eğilimi, alıcı/satıcı üstünlüğü, bullish/bearish durum veya gelecekteki yön hakkında çıkarım yapma.
Long/short account ratio yalnızca ölçülen hesap oranıdır; "daha fazla long tutucu" gibi genelleme yapma.
Taker ratio yalnızca ölçülen orandır; "satıcılar daha aktif" gibi yönsel yorum yapma.
Funding negatifse yalnızca "funding negatif"; basis negatifse yalnızca "basis negatif"; OI değişimi negatifse yalnızca "OI 24 saatlik değişimi negatif" de.
Kısa, doğal ve düzgün Türkçe cevap ver. Sayısal değerleri koru.
Kanıt yetersizse bunu açıkça söyle."""
    payload={"model":MODEL,"stream":False,"messages":[
        {"role":"system","content":system},
        {"role":"user","content":facts+"\nSoru: BTC hakkında şu an ne görüyorsun?"}
    ],"options":{"temperature":0.1}}
    req=urllib.request.Request(OLLAMA,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=120) as r:
        return json.loads(r.read().decode())["message"]["content"].strip()

def main():
    b=load()
    answer=ask_qwen(b)
    low=answer.lower()
    forbidden=("long aç","short aç","satın al","satmal","alım yap","yükselir","düşer","bullish","bearish")
    checks={
      "bridge_evidence_available":b.get("status")=="EVIDENCE_AVAILABLE",
      "bridge_direction_blocked":b["policy"].get("directional_allowed") is False,
      "answer_nonempty":bool(answer),
      "no_trade_or_direction_claim":not any(x in low for x in forbidden),
      "no_measurement_to_direction_upgrade":not any(x in low for x in (
          "düşme eğilim","düşüş eğilim","yükselme eğilim","yükseliş eğilim",
          "satıcıların daha fazla","alıcıların daha fazla","satıcılar daha aktif",
          "alıcılar daha aktif","uzun tutuculuğun","long tutucu",
          "belirli bir eğilim","fiyatının düş","fiyatının yüks"
      )),
      "mentions_evidence_limit":any(x in low for x in ("yetersiz","yeterli değil","2 gözlem","iki gözlem","yön","sonuç")),
    }
    passed=sum(checks.values())
    result={"schema":"ZITAR_FINANCE_QWEN_SYNTHESIS_TEST_V1_1","question":"BTC hakkında şu an ne görüyorsun?",
            "answer":answer,"checks":checks,"passed":passed,"total":len(checks)}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("ZITAR FINANCE QWEN SYNTHESIS V1")
    print("GROUNDED FINANCE EVIDENCE • NO ORDER • NO DIRECTION UPGRADE")
    print("ZITAR:",answer)
    print(f"\nvalidation: {passed}/{len(checks)}")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(checks) else "FAIL")

if __name__=="__main__":
    main()
