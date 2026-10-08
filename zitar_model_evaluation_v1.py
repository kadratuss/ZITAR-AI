"""Behavior smoke evaluation; heuristic checks do not replace human quality review."""
import argparse
import hashlib
import json
import time
import unicodedata
from datetime import datetime,timezone
from pathlib import Path
from zitar_model_provider_v1 import chat,settings,BASE

def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',value.casefold().replace('ı','i')) if not unicodedata.combining(c))

def score(case,answer):
    text=norm(answer)
    missing=[group for group in case['required'] if not any(norm(word) in text for word in group)]
    forbidden=[word for word in case['forbidden'] if norm(word) in text]
    return dict(heuristic_pass=not missing and not forbidden,missing=missing,forbidden=forbidden,
                human_review_required=True,rubric=case['rubric'])

def run(base=BASE):
    path=Path(base)/'zitar_training'/'evaluation.jsonl'
    data=path.read_bytes()
    config,_=settings(base)
    rows=[]
    for line in data.decode().splitlines():
        case=json.loads(line);start=time.monotonic()
        try:
            answer=chat(case['messages'],temperature=0,max_tokens=300,base=base)
            result=dict(id=case['id'],question=case['messages'],answer=answer,**score(case,answer))
        except Exception as exc:
            result=dict(id=case['id'],error=type(exc).__name__+': '+str(exc),heuristic_pass=False,human_review_required=True)
        result['seconds']=round(time.monotonic()-start,2)
        rows.append(result)
        print(case['id'],'PASS' if result['heuristic_pass'] else 'REVIEW',flush=True)
    return dict(schema='ZITAR_MODEL_EVALUATION_V1',created_utc=datetime.now(timezone.utc).isoformat(),
                model=config['model'],base_model=config['base_model'],fine_tuned=config['fine_tuned'],
                evaluation_sha256=hashlib.sha256(data).hexdigest(),
                config_sha256=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),
                identity_sha256=hashlib.sha256((Path(base)/config['identity_file']).read_bytes()).hexdigest(),
                passed=sum(r['heuristic_pass'] for r in rows),total=len(rows),
                quality_approved=False,limitation='Heuristic smoke checks; not factual accuracy, tool-use success, or training approval.',results=rows)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=run();args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(str(result['passed'])+'/'+str(result['total']),flush=True)
