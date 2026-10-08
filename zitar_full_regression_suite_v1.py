from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path
from datetime import datetime, timezone

BASE=Path(__file__).resolve().parent
OUT=BASE/"zitar_full_regression_suite_v1.json"

TESTS=[
 ("CORE_ROUTER","zitar_core_conversation_router_v1.py"),
 ("CORE_CONTEXT","zitar_core_context_v1_2.py"),
 ("PROJECT_MEMORY_RETRIEVAL","zitar_core_project_memory_retrieval_v2.py"),
 ("LEARNING_JOURNAL_RETRIEVAL","zitar_core_learning_journal_retrieval_v1.py"),
 ("UNIFIED_RECALL","zitar_core_unified_recall_v1.py"),
 ("DOMAIN_LEARNING_RECALL","zitar_core_domain_learning_recall_v1.py"),
 ("KNOWLEDGE_GAP","zitar_core_knowledge_gap_v1.py"),
 ("RESEARCH_PLANNER","zitar_core_research_planner_v1.py"),
 ("RESEARCH_EXECUTOR","zitar_core_research_executor_v1.py"),
 ("LEARNING_JOURNAL_COMPATIBILITY","zitar_core_learning_journal_compatibility_v1.py"),
 ("QWEN_LANGUAGE_QUALITY","zitar_qwen_language_quality_guard_v2.py"),
 ("FINANCE_BRIDGE","zitar_finance_unified_bridge_v1_1.py"),
 ("FINANCE_GROUNDED_RENDERER","zitar_finance_grounded_renderer_v1.py"),
 ("UNIFIED_CHAT_FINANCE","zitar_unified_chat_finance_bridge_v1.py"),
]

def run_one(name,filename):
    path=BASE/filename
    if not path.exists():
        return {"name":name,"file":filename,"status":"MISSING","returncode":None,"seconds":0}
    t=time.time()
    try:
        cp=subprocess.run([sys.executable,"-u",str(path)],cwd=BASE,
                          capture_output=True,text=True,encoding="utf-8",
                          errors="replace",timeout=180)
        text=(cp.stdout or "")+"\n"+(cp.stderr or "")
        # Require both successful process exit and explicit application PASS.
        explicit_pass="STATUS: PASS" in text
        status="PASS" if cp.returncode==0 and explicit_pass else "FAIL"
        return {"name":name,"file":filename,"status":status,
                "returncode":cp.returncode,"seconds":round(time.time()-t,2),
                "tail":"\n".join(text.strip().splitlines()[-12:])}
    except subprocess.TimeoutExpired:
        return {"name":name,"file":filename,"status":"TIMEOUT","returncode":None,
                "seconds":round(time.time()-t,2)}
    except Exception as e:
        return {"name":name,"file":filename,"status":"ERROR","returncode":None,
                "seconds":round(time.time()-t,2),"error":f"{type(e).__name__}:{e}"}

def main():
    print("ZITAR FULL REGRESSION SUITE V1")
    print("READ/TEST ORCHESTRATION • NO REAL ORDER • NO MEMORY PROMOTION\n")
    results=[]
    for name,filename in TESTS:
        r=run_one(name,filename); results.append(r)
        print(f"{r['status']:<8} | {name:<32} | {filename} | {r['seconds']}s")
    counts={s:sum(r["status"]==s for r in results)
            for s in ("PASS","FAIL","MISSING","TIMEOUT","ERROR")}
    overall="PASS" if counts["PASS"]==len(results) else "FAIL"
    report={"schema":"ZITAR_FULL_REGRESSION_SUITE_V1",
            "generated_utc":datetime.now(timezone.utc).isoformat(),
            "overall_status":overall,"counts":counts,"total":len(results),
            "results":results,
            "authorities":{"real_order":False,"automatic_memory_promotion":False}}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("\nSUMMARY")
    print("total:",len(results))
    for k,v in counts.items(): print(f"{k.lower()}: {v}")
    print("report:",OUT)
    print("STATUS:",overall)

if __name__=="__main__":
    main()
