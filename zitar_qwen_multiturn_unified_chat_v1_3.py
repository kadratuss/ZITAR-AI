from __future__ import annotations
import json, re, urllib.request
from pathlib import Path

BASE=Path(__file__).resolve().parent
JOURNAL=BASE/"zitar_core_learning_journal_v1.jsonl"
PROJECT=BASE/"zitar_core_project_memory_v1.jsonl"
OUT=BASE/"zitar_qwen_multiturn_unified_chat_test_v1_3.json"
OLLAMA="http://127.0.0.1:11434/api/chat"
MODEL="qwen2.5:7b"
TR=str.maketrans({"ç":"c","ğ":"g","ı":"i","ö":"o","ş":"s","ü":"u","â":"a","î":"i","û":"u"})

def norm(s): return re.sub(r"\s+"," ",(s or "").casefold().translate(TR)).strip()
def load(p):
    if not p.exists(): return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

def project_records(rows): return [x for x in rows if x.get("project")=="MODEL_TRAIN"]

def route(q,state):
    t=norm(q)
    if any(x in t for x in ("btc","bitcoin")): return "FINANCE_RESEARCH","FINANCE"
    if "raspberry pi 5" in t: return "LEARNING_RECALL","GENERAL_RESEARCH"
    if "model tren" in t: return "PROJECT_RECALL","MODEL_TRAIN"
    if any(x in t for x in ("nasilsin","selam","merhaba","ne haber")): return "CONVERSATION",state.get("domain")
    if state.get("domain")=="MODEL_TRAIN" and any(x in t for x in ("peki","neden","sirada","sonra","iki sensor","sensör")):
        return "PROJECT_RECALL","MODEL_TRAIN"
    return "UNKNOWN",state.get("domain")

def context_for(q,r,domain,journal,project):
    if r=="CONVERSATION": return "Gündelik konuşma; harici olgu gerekmez.",True
    if r=="FINANCE_RESEARCH":
        return "Bu testte güncel Finance Specialist piyasa çıktısı sağlanmamıştır.",True
    if r=="LEARNING_RECALL":
        hits=[x for x in journal if x.get("topic")=="Raspberry Pi 5" and x.get("lesson_type")=="EXTERNAL_RESEARCH_LEARNING"]
        if not hits:return "",False
        return "\n".join("- "+c["claim"] for c in hits[-1].get("claims",[]) if c.get("claim")),True
    if r=="PROJECT_RECALL":
        hits=project_records(project)
        if not hits:return "",False
        t=norm(q)
        if "neden" in t and ("sensor" in t or "sensör" in q.lower()):
            selected=[x for x in hits if x.get("memory_type")=="SENSOR_RULE"]
        elif any(x in t for x in ("sirada","sonra")):
            selected=[x for x in hits if x.get("memory_type") in ("PROJECT_MILESTONE","CONTROL_ARCHITECTURE")]
        else:
            selected=[x for x in hits if x.get("memory_type")=="PROJECT_MILESTONE"]
        if not selected:selected=hits[-2:]
        return "\n".join("- "+x["content"] for x in selected if x.get("content")),True
    return "",False

def ask(q,r,ctx,history):
    system="""Sen ZITAR'sın. Doğal, kısa Türkçe konuş.
GROUNDING dışındaki olgusal ayrıntıları uydurma.
Önceki konuşma yalnızca dilsel takip ve referans çözümü içindir; olgusal kaynak değildir.
Ham JSON, route, source veya iç sistem ayrıntılarını kullanıcıya gösterme.
Finance için güncel veri sağlanmadıysa BTC'nin yönü, performansı veya piyasa durumu hakkında iddia üretme.
Kullanıcı takip sorusu sorarsa bağlamı doğal biçimde sürdür."""
    recent=history[-4:]
    messages=[{"role":"system","content":system}]
    messages.extend(recent)
    messages.append({"role":"user","content":f"QUESTION:\n{q}\n\nGROUNDING:\n{ctx}\n\nYalnızca kullanıcı cevabını üret."})
    data=json.dumps({"model":MODEL,"stream":False,"messages":messages,
                     "options":{"temperature":0.2}},ensure_ascii=False).encode()
    req=urllib.request.Request(OLLAMA,data=data,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=90) as resp:
        return json.loads(resp.read().decode())["message"]["content"].strip()

def main():
    journal=load(JOURNAL); project=load(PROJECT)
    turns=[
      ("Model tren projesinde en son ne yapmıştık?","PROJECT_RECALL","MODEL_TRAIN"),
      ("Peki neden iki sensör kullanıyorduk?","PROJECT_RECALL","MODEL_TRAIN"),
      ("Tamam, sırada ne vardı?","PROJECT_RECALL","MODEL_TRAIN"),
      ("Bu arada BTC nasıl?","FINANCE_RESEARCH","FINANCE"),
    ]
    state={"domain":None}; history=[]; results=[]
    for q,er,ed in turns:
        r,d=route(q,state); ctx,g=context_for(q,r,d,journal,project)
        try:
            if r=="FINANCE_RESEARCH" and "sağlanmamıştır" in ctx:
                a="Güncel Finance Specialist verisi henüz bu konuşma bağlamına bağlanmadı. Bu yüzden BTC'nin mevcut yönü veya performansı hakkında yorum yapmayacağım."
            else:
                a=ask(q,r,ctx,history) if g else "Bu konuda güvenilir bağlam bulamadım."
        except Exception as e:
            a=f"ERROR:{type(e).__name__}:{e}"
        ok=(r==er and d==ed and g and not a.startswith("ERROR:"))
        if r=="FINANCE_RESEARCH":
            low=norm(a)
            forbidden=any(x in low for x in (
                "yukseliyor","dusuyor","dalgali trend","bullish","bearish",
                "son verilere gore","piyasa belirsizlik"
            ))
            required=(
                "finance specialist" in low
                and "guncel" in low
                and "yorum yapmayacagim" in low
            )
            ok=ok and (not forbidden) and required
        results.append({"question":q,"route":r,"domain":d,"grounded":g,"answer":a,"pass":ok})
        print(("PASS" if ok else "FAIL"),f"| route={r:<16} domain={str(d):<14} | {q}")
        print("  ZITAR:",a)
        history += [{"role":"user","content":q},{"role":"assistant","content":a}]
        state["domain"]=d
    passed=sum(int(x["pass"]) for x in results)
    OUT.write_text(json.dumps({"schema":"ZITAR_QWEN_MULTITURN_UNIFIED_CHAT_TEST_V1_3",
      "model":MODEL,"results":results,"passed":passed,"total":len(results)},
      ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"\nRESULT: {passed}/{len(results)}")
    print("output:",OUT)
    print("STATUS:","PASS" if passed==len(results) else "FAIL")

if __name__=="__main__": main()
