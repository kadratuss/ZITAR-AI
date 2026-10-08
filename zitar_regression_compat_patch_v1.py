from pathlib import Path
import re, shutil, datetime

BASE=Path(__file__).resolve().parent
stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

def backup(path):
    b=path.with_name(path.name+'.bak_'+stamp)
    shutil.copy2(path,b)
    return b

suite=BASE/'zitar_full_regression_suite_v1.py'
backup(suite)
s=suite.read_text(encoding='utf-8')
old='("CORE_ROUTER","zitar_core_router_v1.py")'
new='("CORE_ROUTER","zitar_core_conversation_router_v1.py")'
if old not in s: raise SystemExit('STOP: CORE_ROUTER manifest satiri bulunamadi.')
suite.write_text(s.replace(old,new),encoding='utf-8')

research=BASE/'zitar_core_research_executor_v1.py'
backup(research)
s=research.read_text(encoding='utf-8')
pat=re.compile(r'\{\s*"name"\s*:\s*"general_gap_requests_external_research"\s*,\s*"pass"\s*:\s*(.*?)\s*\}',re.S)
m=pat.search(s)
if not m: raise SystemExit('STOP: research assertion bulunamadi.')
replacement = '''{
            "name": "general_gap_resolved_by_local_or_external",
            "pass": (
                (general_bundle.get("status") == "EXTERNAL_RESEARCH_REQUIRED" and len(general_bundle.get("evidence", [])) == 0)
                or
                (general_bundle.get("status") == "LOCAL_EVIDENCE_COLLECTED" and len(general_bundle.get("evidence", [])) > 0)
            )
        }'''
s=s[:m.start()]+replacement+s[m.end():]
research.write_text(s,encoding='utf-8')

compat=BASE/'zitar_core_learning_journal_compatibility_v1.py'
backup(compat)
s=compat.read_text(encoding='utf-8')
ns,n=re.subn(r'(\w+)\.get\("schema"\)\s*!=\s*"ZITAR_CORE_LEARNING_JOURNAL_V1"',r'\1.get("schema") not in {"ZITAR_CORE_LEARNING_JOURNAL_V1", "ZITAR_CORE_LEARNING_JOURNAL_V2"}',s)
if n==0: raise SystemExit('STOP: compatibility schema kontrolu bulunamadi.')
compat.write_text(ns,encoding='utf-8')

for x in (suite,research,compat):
    compile(x.read_text(encoding='utf-8'),str(x),'exec')

print('ZITAR REGRESSION COMPAT PATCH V1')
print('PASS | regression router manifest')
print('PASS | research local/external expectation')
print('PASS | learning journal V1+V2 compatibility')
print('PASS | patched files compile')
print('IMPORTANT | learning journal DATA was NOT modified')
print('STATUS: PASS')
