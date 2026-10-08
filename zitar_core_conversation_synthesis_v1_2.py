from __future__ import annotations
import json, re
from pathlib import Path

BASE=Path(__file__).resolve().parent
JOURNAL=BASE/"zitar_core_learning_journal_v1.jsonl"
PROJECT=BASE/"zitar_core_project_memory_v1.jsonl"
OUT=BASE/"zitar_core_conversation_synthesis_test_v1_2.json"

TESTS=[
 ("Nasılsın?","CONVERSATION"),
 ("Raspberry Pi 5 hakkında ne öğrendin?","LEARNING_RECALL"),
 ("Model tren projesinde en son ne yapmıştık?","PROJECT_RECALL"),
 ("BTC hakkında şu an ne görüyorsun?","FINANCE_RESEARCH"),
]

TR=str.maketrans("çğıöşüâîû","cgiosuaiu")
def norm(s):
    return re.sub(r"\s+"," ",(s or "").casefold().translate(TR)).strip()

def load_jsonl(path):
    if not path.exists(): return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def route(q):
    t=norm(q)
    if any(x in t for x in ("nasilsin","selam","merhaba","ne haber")): return "CONVERSATION"
    if "raspberry pi 5" in t and any(x in t for x in ("ogrendin","hatirliyor","biliyor")): return "LEARNING_RECALL"
    if "model tren" in t and any(x in t for x in ("en son","hatirliyor","yapmistik","nerede kal")): return "PROJECT_RECALL"
    if any(x in t for x in ("btc","bitcoin")) and any(x in t for x in ("goruyorsun","nasil","analiz")): return "FINANCE_RESEARCH"
    return "UNKNOWN"

def learning_answer(rows):
    hits=[r for r in rows if r.get("topic")=="Raspberry Pi 5" and r.get("lesson_type")=="EXTERNAL_RESEARCH_LEARNING"]
    if not hits: return "Bu konuda doğrulanmış bir öğrenme kaydım yok.","LEARNING_JOURNAL",False
    claims=[c.get("claim") for c in hits[-1].get("claims",[]) if c.get("claim")]
    return "Araştırıp doğruladığım kayda göre: "+" ".join(claims),"LEARNING_JOURNAL",bool(claims)

def project_answer(rows):
    # Real Project Memory V1 schema uses `project`, not `domain`.
    hits=[r for r in rows if r.get("project")=="MODEL_TRAIN"]
    if not hits:
        return "Model tren proje hafızasında kayıt bulunamadı.","PROJECT_MEMORY",False
    milestones=[r for r in hits if r.get("memory_type")=="PROJECT_MILESTONE" and r.get("content")]
    chosen=milestones[-1] if milestones else hits[-1]
    return "Model tren projesinde son doğrulanmış kilometre taşım: "+chosen["content"],"PROJECT_MEMORY",True

def answer(q,journal,project):
    r=route(q)
    if r=="CONVERSATION": return r,"İyiyim. Buradayım; kaldığımız yerden devam edebiliriz.","CORE_SELF",True
    if r=="LEARNING_RECALL":
        a,s,g=learning_answer(journal); return r,a,s,g
    if r=="PROJECT_RECALL":
        a,s,g=project_answer(project); return r,a,s,g
    if r=="FINANCE_RESEARCH":
        return r,"Bu soru Finance uzmanlık katmanına yönlendirilmeli; Core piyasa verisi uydurmaz.","FINANCE_SPECIALIST",True
    return r,"Sorunun bağlamını henüz güvenilir biçimde belirleyemedim.","CORE_ROUTER",False

def main():
    journal=load_jsonl(JOURNAL); project=load_jsonl(PROJECT)
    results=[]
    for q,expected in TESTS:
        r,a,s,grounded=answer(q,journal,project)
        ok=(r==expected and grounded)
        results.append({"question":q,"expected":expected,"route":r,"source":s,
                        "grounded":grounded,"answer":a,"pass":ok})
        print(("PASS" if ok else "FAIL"),
              f"| route={r:<16} source={s:<18} grounded={str(grounded):<5} | {q}")
        print("  ZITAR:",a)
    passed=sum(int(x["pass"]) for x in results)
    OUT.write_text(json.dumps({
        "schema":"ZITAR_CORE_CONVERSATION_SYNTHESIS_TEST_V1_2",
        "journal_records":len(journal),"project_records":len(project),
        "model_train_records":sum(r.get("project")=="MODEL_TRAIN" for r in project),
        "results":results,"passed":passed,"total":len(results)
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"\nRESULT: {passed}/{len(results)}")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(results) else "FAIL")

if __name__=="__main__":
    main()
