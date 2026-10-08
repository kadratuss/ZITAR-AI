from __future__ import annotations
import json, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROJECT_MEMORY = BASE / "zitar_core_project_memory_v1.jsonl"
LEARNING_JOURNAL = BASE / "zitar_core_learning_journal_v1.jsonl"
OUT = BASE / "zitar_core_unified_recall_test_v1.json"

def norm(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())

def toks(s):
    return set(re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9_]+", norm(s)))

def load_jsonl(path):
    if not path.exists():
        raise FileNotFoundError(path)
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def route(text):
    t=norm(text)

    if any(x in t for x in ("ne öğrendin","neler öğrendin","öğrendiğin","gelişiminden ne")):
        return "LEARNING_RECALL"

    if any(x in t for x in ("model tren","tren projes","zitar core","projesinde en son","ne yapmıştık","hatırlıyor musun")):
        return "PROJECT_RECALL"

    if any(x in t for x in ("btc","eth","sol","xrp","doge")) and any(
        x in t for x in ("görüyorsun","araştır","analiz","görüş")
    ):
        return "FINANCE_RESEARCH"

    if any(x in t for x in ("nasılsın","selam","merhaba","ne haber")):
        return "CONVERSATION"

    return "UNKNOWN"

def score(query, text):
    q=toks(query); d=toks(text)
    return len(q & d)

def project_recall(query, rows):
    q=norm(query)
    scored=[]
    for r in rows:
        text=" ".join([
            r.get("project",""), r.get("memory_type",""),
            r.get("content",""), r.get("source","")
        ])
        s=score(query,text)
        if r.get("project")=="MODEL_TRAIN" and any(x in q for x in ("model tren","tren projes","lokomotif","ray")):
            s += 8
        if r.get("project")=="ZITAR_CORE" and "zitar" in q:
            s += 8
        if s>0:
            scored.append((s,r))
    scored.sort(key=lambda x:(x[0],x[1].get("created_utc","")),reverse=True)
    return scored[:3]

def learning_recall(query, rows, active_domain=None):
    q=norm(query)
    scored=[]
    for r in rows:
        text=" ".join([
            r.get("domain",""),r.get("lesson_type",""),r.get("observation",""),
            " ".join(map(str,r.get("evidence") or [])),
            r.get("prior_state",""),r.get("updated_state",""),r.get("source","")
        ])
        s=score(query,text)
        if any(x in q for x in ("ne öğrendin","neler öğrendin")):
            s += 4
        if active_domain=="ZITAR_CORE" and r.get("domain")=="ZITAR_CORE":
            s += 3
        if s>0:
            scored.append((s,r))
    scored.sort(key=lambda x:(x[0],x[1].get("created_utc","")),reverse=True)
    return scored[:3]

class CoreSession:
    def __init__(self):
        self.active_domain=None
        self.last_route=None

    def resolve(self,text):
        raw=route(text)
        resolved=raw
        inherited=False

        # Generic learning follow-up: inherit the active domain, but keep the
        # semantic route as LEARNING_RECALL.
        if raw=="LEARNING_RECALL" and self.active_domain:
            inherited=True

        if raw=="PROJECT_RECALL":
            t=norm(text)
            if "tren" in t:
                self.active_domain="MODEL_TRAIN"
            elif "zitar" in t:
                self.active_domain="ZITAR_CORE"

        elif raw=="FINANCE_RESEARCH":
            self.active_domain="FINANCE"

        elif raw=="LEARNING_RECALL" and self.active_domain is None:
            self.active_domain="ZITAR_CORE"

        self.last_route=resolved
        return {"raw_route":raw,"resolved_route":resolved,
                "active_domain":self.active_domain,"context_inherited":inherited}

def answer(text, session, projects, learning):
    r=session.resolve(text)
    route_=r["resolved_route"]

    if route_=="PROJECT_RECALL":
        hits=project_recall(text,projects)
        return r, "PROJECT_MEMORY", hits

    if route_=="LEARNING_RECALL":
        hits=learning_recall(text,learning,r["active_domain"])
        return r, "LEARNING_JOURNAL", hits

    if route_=="FINANCE_RESEARCH":
        return r, "FINANCE_SPECIALIST", []

    if route_=="CONVERSATION":
        return r, "CONVERSATION", []

    return r, "NONE", []

SCENARIOS=[
    {
        "name":"project_then_learning_followup",
        "turns":[
            ("Model tren projesinde en son ne yapmıştık?","PROJECT_RECALL","PROJECT_MEMORY","MODEL_TRAIN",False),
            ("Peki bundan ne öğrendin?","LEARNING_RECALL","LEARNING_JOURNAL","MODEL_TRAIN",True),
        ]
    },
    {
        "name":"core_learning_direct",
        "turns":[
            ("ZİTAR Core geliştirmelerinden ne öğrendin?","LEARNING_RECALL","LEARNING_JOURNAL","ZITAR_CORE",False),
        ]
    },
    {
        "name":"finance_is_separate",
        "turns":[
            ("BTC hakkında şu an ne görüyorsun?","FINANCE_RESEARCH","FINANCE_SPECIALIST","FINANCE",False),
        ]
    },
    {
        "name":"conversation_not_hijacked",
        "turns":[
            ("Nasılsın?","CONVERSATION","CONVERSATION",None,False),
        ]
    }
]

def main():
    projects=load_jsonl(PROJECT_MEMORY)
    learning=load_jsonl(LEARNING_JOURNAL)
    results=[]; passed=0; total=0

    print("ZİTAR CORE UNIFIED RECALL V1")
    print("ROUTER + CONTEXT + PROJECT MEMORY + LEARNING JOURNAL")
    print("READ ONLY • NO LLM • NO ORDER • NO MEMORY WRITE")

    for sc in SCENARIOS:
        session=CoreSession()
        print(f"\n[{sc['name']}]")
        for text,exp_route,exp_source,exp_domain,exp_inherited in sc["turns"]:
            total+=1
            r,source,hits=answer(text,session,projects,learning)
            ok=(r["resolved_route"]==exp_route and source==exp_source and
                r["active_domain"]==exp_domain and r["context_inherited"]==exp_inherited)
            # Recall routes must actually retrieve something.
            if exp_source in ("PROJECT_MEMORY","LEARNING_JOURNAL"):
                ok = ok and bool(hits)
            passed += int(ok)
            print(
                f"{'PASS' if ok else 'FAIL':4} | route={r['resolved_route']:16} "
                f"source={source:18} domain={str(r['active_domain']):11} "
                f"inherited={str(r['context_inherited']):5} | {text}"
            )
            results.append({"scenario":sc["name"],"text":text,"routing":r,
                            "source":source,"hit_count":len(hits),"pass":ok})

    payload={
        "schema":"ZITAR_CORE_UNIFIED_RECALL_TEST_V1",
        "project_memory_records":len(projects),
        "learning_journal_records":len(learning),
        "results":results,
        "passed":passed,"total":total,
        "llm_used":False,"memory_write":False,"execution_authority":False,
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    print(f"\nRESULT: {passed}/{total} PASS")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==total else "FAIL")

if __name__=="__main__":
    main()
