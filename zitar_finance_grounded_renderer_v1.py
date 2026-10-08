from __future__ import annotations
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
BRIDGE=BASE/"zitar_finance_unified_bridge_v1_1.json"
OUT=BASE/"zitar_finance_grounded_renderer_test_v1.json"

def fmt(x,n):
    return "yok" if x is None else f"{x:.{n}f}"

def render(b):
    symbol = b.get('requested_symbol') or 'Belirtilmeyen sembol'
    if b.get('status') != 'EVIDENCE_AVAILABLE':
        return f"{symbol} için kullanılabilir finans kanıtı bulunamadı; başka bir sembolün verisini kullanmıyorum."
    e=b["evidence"]; t=b["temporal"]
    lines=[
      f"{symbol} için kayıtlı Finance ölçümleri (kaynak zamanı: {b.get('source', {}).get('latest_observed_utc') or 'bilinmiyor'}):",
      f"- Funding: {e['funding']}",
      f"- Basis: {fmt(e['basis_bps'],4)} bps",
      f"- OI 24 saat değişimi: %{fmt(e['oi24h_pct'],4)}",
      f"- Long/Short hesap oranı: {e['long_short_ratio']}",
      f"- Taker buy/sell oranı: {e['taker_ratio']}.",
    ]
    obs=t.get("observations")
    if not b["policy"]["directional_allowed"]:
        lines.append(
          f"Temporal değerlendirme için yalnızca {obs} gözlem var; durum "
          f"{t.get('status')}. Agreement {b.get('agreement')} ve kaynak sonucu "
          f"{b.get('source_conclusion')}. Bu nedenle mevcut kanıttan yönsel sonuç "
          "veya işlem sinyali çıkarmıyorum."
        )
    return "\n".join(lines)

def main():
    b=json.loads(BRIDGE.read_text(encoding="utf-8-sig"))
    a=render(b)
    low=a.lower()
    checks={
      "bridge_ready":b.get("status")=="EVIDENCE_AVAILABLE",
      "all_metrics_rendered":all(str(b["evidence"][k]) in a for k in
        ("funding","long_short_ratio","taker_ratio")),
      "temporal_limit_rendered":str(b["temporal"].get("observations")) in a,
      "direction_block_respected":b["policy"].get("directional_allowed") is False,
      "no_directional_language":not any(x in low for x in
        ("bullish","bearish","yükseliş eğil","düşüş eğil","fiyat düş","fiyat yüks",
         "satıcılar daha aktif","alıcılar daha aktif","long tutucu")),
      "no_order_authority":b["policy"].get("real_order_authority") is False,
    }
    passed=sum(checks.values())
    OUT.write_text(json.dumps({"schema":"ZITAR_FINANCE_GROUNDED_RENDERER_TEST_V1",
      "answer":a,"checks":checks,"passed":passed,"total":len(checks)},
      ensure_ascii=False,indent=2),encoding="utf-8")
    print("ZITAR FINANCE GROUNDED RENDERER V1")
    print("DETERMINISTIC FACT RENDER • NO LLM INTERPRETATION • NO ORDER")
    print("\nZITAR:",a)
    print(f"\nvalidation: {passed}/{len(checks)}")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(checks) else "FAIL")

if __name__=="__main__":
    main()
