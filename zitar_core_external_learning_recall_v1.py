from __future__ import annotations
import json, re
from pathlib import Path

BASE=Path(__file__).resolve().parent
JOURNAL=BASE/"zitar_core_learning_journal_v1.jsonl"
OUT=BASE/"zitar_core_learning_journal_recall_external_test_v1.json"

QUESTIONS=[
    "Raspberry Pi 5 hakkında ne öğrendin?",
    "Raspberry Pi 5 ne zaman duyuruldu?",
    "Raspberry Pi 5 işlemcisi hakkında ne öğrendin?",
]

def load():
    return [json.loads(x) for x in JOURNAL.read_text(encoding="utf-8").splitlines() if x.strip()]

def tokens(s):
    return set(re.findall(r"[a-z0-9]+",(s or "").lower()))

def score(q,r):
    qtok=tokens(q)
    hay=" ".join([
        str(r.get("topic","")), str(r.get("observation","")),
        " ".join(str(c.get("claim","")) for c in (r.get("claims") or []))
    ])
    ht=tokens(hay)
    overlap=len(qtok & ht)
    topic_bonus=5 if "raspberry" in qtok and "raspberry" in ht else 0
    external_bonus=2 if r.get("lesson_type")=="EXTERNAL_RESEARCH_LEARNING" else 0
    return overlap+topic_bonus+external_bonus

def main():
    rows=load()
    results=[]
    for q in QUESTIONS:
        ranked=sorted(((score(q,r),i,r) for i,r in enumerate(rows)),key=lambda x:(x[0],x[1]),reverse=True)
        s,i,top=ranked[0]
        claims=[c.get("claim") for c in (top.get("claims") or []) if c.get("claim")]
        passed=(top.get("lesson_type")=="EXTERNAL_RESEARCH_LEARNING"
                and top.get("topic")=="Raspberry Pi 5"
                and len(claims)>=2)
        results.append({"question":q,"score":s,"record":i+1,"topic":top.get("topic"),
                        "lesson_type":top.get("lesson_type"),"claims":claims,"pass":passed})

    passed=sum(int(r["pass"]) for r in results)
    OUT.write_text(json.dumps({"schema":"ZITAR_CORE_EXTERNAL_LEARNING_RECALL_TEST_V1",
        "journal_records":len(rows),"results":results,"passed":passed,"total":len(results)},
        ensure_ascii=False,indent=2),encoding="utf-8")

    print("ZITAR CORE EXTERNAL LEARNING RECALL V1")
    print("LEARNING JOURNAL READ ONLY • NO WEB • NO MEMORY WRITE")
    print("journal records:",len(rows))
    for r in results:
        print(("PASS" if r["pass"] else "FAIL"),
              f"| record={r['record']} topic={r['topic']} | {r['question']}")
        if r["pass"]:
            for c in r["claims"]: print("   ->",c)
    print(f"RESULT: {passed}/{len(results)}")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(results) else "FAIL")

if __name__=="__main__":
    main()
