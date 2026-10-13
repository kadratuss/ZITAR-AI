"""Bounded real-data integration trial; previous observed holdouts stay ineligible."""
import json
from pathlib import Path
from zitar_next.store import init,atomic
from zitar_next.market import fetch
from zitar_next.worker import train_round

root=init('research_artifacts/hosting-validation-v2')
cursor=json.loads(Path('research_artifacts/next-release/cursor.json').read_text(encoding='utf-8'))
atomic(root/'heldout_anchors.json',{key:value['test_end'] for key,value in cursor.items()})
for market in ('spot','futures'):
    snapshot=fetch(market,'BTCUSDT')
    body=train_round(root,market,'BTCUSDT',2048,snapshot=snapshot)
    print(json.dumps(dict(market=market,run=body['run'],strategy=body['strategy'],
                         folds=len(body['walk_forward']['folds']),
                         returns={key:value['return_pct'] for key,value in body['combination']['test'].items()},
                         eligible=body['eligible'],issues=body['issues'])),flush=True)
