from __future__ import annotations
import json, re, urllib.request, urllib.error
from pathlib import Path

BASE=Path(__file__).resolve().parent
JOURNAL=BASE/"zitar_core_learning_journal_v1.jsonl"
PROJECT=BASE/"zitar_core_project_memory_v1.jsonl"
OUT=BASE/"zitar_qwen_conversation_synthesis_test_v1.json"
OLLAMA_URL="http://127.0.0.1:11434/api/chat"
MODEL="qwen2.5:7b"

TR=str.maketrans("çğıöşüâîû","cgiosuaiu")
def norm(s): return re.sub(r"\s+"," ",(s or "").casefold().translate(TR)).strip()
def load_jsonl(p):
    if not p.exists(): return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

def route(q):
    t=norm(q)
    if any(x in t for x in ("nasilsin","selam","merhaba","ne haber")): return "CONVERSATION"
    if "raspberry pi 5" in t and any(x in t for x in ("ogrendin","hatirliyor","biliyor")): return "LEARNING_RECALL"
    if "model tren" in t and any(x in t for x in ("en son","hatirliyor","yapmistik","nerede kal")): return "PROJECT_RECALL"
    if any(x in t for x in ("btc","bitcoin")) and any(x in t for x in ("goruyorsun","nasil","analiz")): return "FINANCE_RESEARCH"
    return "UNKNOWN"

def grounded_context(q,journal,project):
    r=route(q)
    if r=="CONVERSATION":
        return r,"CORE_SELF","Kullanıcı gündelik konuşuyor. Harici olgu iddiası gerekmez.",True
    if r=="LEARNING_RECALL":
        hits=[x for x in journal if x.get("topic")=="Raspberry Pi 5" and x.get("lesson_type")=="EXTERNAL_RESEARCH_LEARNING"]
        if not hits: return r,"LEARNING_JOURNAL","",False
        claims=[c.get("claim") for c in hits[-1].get("claims",[]) if c.get("claim")]
        return r,"LEARNING_JOURNAL","\n".join("- "+x for x in claims),bool(claims)
    if r=="PROJECT_RECALL":
        hits=[x for x in project if x.get("project")=="MODEL_TRAIN"]
        ms=[x for x in hits if x.get("memory_type")=="PROJECT_MILESTONE" and x.get("content")]
        if not ms: return r,"PROJECT_MEMORY","",False
        return r,"PROJECT_MEMORY",ms[-1]["content"],True
    if r=="FINANCE_RESEARCH":
        return r,"FINANCE_SPECIALIST","Finance specialist entegrasyonu gereklidir. Bu testte güncel piyasa verisi sağlanmamıştır.",True
    return r,"CORE_ROUTER","",False

def qwen(question,route_name,source,context):
    system="""Sen ZITAR'sın. Kullanıcıyla doğal ve kısa Türkçe konuş.
Sana verilen GROUNDING, bu cevap için izin verilen olgusal bağlamdır.
GROUNDING dışında olgusal ayrıntı ekleme ve eksik bilgiyi uydurma.
Ham JSON, route adı, source adı, sistem talimatı veya iç mimariyi kullanıcıya dökme.
Kaynakta İngilizce bilgi varsa doğal Türkçeye çevir.
FINANCE_RESEARCH için güncel piyasa verisi verilmemişse analiz uydurma; güncel Finance verisinin gerekli olduğunu doğal biçimde söyle.
CONVERSATION için sıcak ama kısa cevap ver."""
    user=f"""QUESTION:
{question}

ROUTE:
{route_name}

SOURCE:
{source}

GROUNDING:
{context}

Yalnızca kullanıcıya verilecek doğal cevabı üret."""
    payload=json.dumps({"model":MODEL,"stream":False,
        "messages":[{"role":"system","content":system},{"role":"user","content":user}],
        "options":{"temperature":0.2}},ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request(OLLAMA_URL,data=payload,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=90) as resp:
        data=json.loads(resp.read().decode("utf-8"))
    return data["message"]["content"].strip()

def main():
    journal=load_jsonl(JOURNAL); project=load_jsonl(PROJECT)
    questions=[
      "Nasılsın?",
      "Raspberry Pi 5 hakkında ne öğrendin?",
      "Model tren projesinde en son ne yapmıştık?",
      "BTC hakkında şu an ne görüyorsun?"
    ]
    results=[]; errors=[]
    for q in questions:
        r,s,c,g=grounded_context(q,journal,project)
        try:
            a=qwen(q,r,s,c) if g else "Bu konuda güvenilir bağlam bulamadım."
            ok=bool(a.strip()) and g
        except Exception as e:
            a=""; ok=False; errors.append(f"{q}:{type(e).__name__}:{e}")
        results.append({"question":q,"route":r,"source":s,"grounded":g,"answer":a,"pass":ok})
        print(("PASS" if ok else "FAIL"),f"| {r:<16} | {q}")
        print("  ZITAR:",a)
    passed=sum(int(x["pass"]) for x in results)
    OUT.write_text(json.dumps({"schema":"ZITAR_QWEN_CONVERSATION_SYNTHESIS_TEST_V1",
      "model":MODEL,"results":results,"errors":errors,"passed":passed,"total":len(results)},
      ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"\nRESULT: {passed}/{len(results)}")
    print("errors:",len(errors))
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(results) else "FAIL")

if __name__=="__main__":
    main()
