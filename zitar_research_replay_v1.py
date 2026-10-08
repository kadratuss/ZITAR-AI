"""Replay recorded forward inputs into a NEW output file; never modify live state.
This is reproducibility validation, NOT unseen historical performance evidence.
Usage: python -B zitar_research_replay_v1.py --inputs DIR --output NEW.json
"""
import argparse,gzip,json
from pathlib import Path
from zitar_research_experiment_v1 import initial,advance,HASH,metrics

def replay(folder):
 state=None;last=0
 for path in sorted(Path(folder).glob('*.jsonl.gz')):
  with gzip.open(path,'rt',encoding='utf-8') as stream:
   for line in stream:
    row=json.loads(line)
    if row['manifest_hash']!=HASH:raise ValueError('REPLAY_MANIFEST_MISMATCH')
    if row['ms']<=last:raise ValueError('REPLAY_DUPLICATE_OR_UNORDERED_INPUT')
    if state is None:
     state=initial(row['started_ms'],row['universe'])
     if row['ms']-row['started_ms']>30000:raise ValueError('REPLAY_START_INPUT_MISSING')
    signals={(x['market'],x['symbol'],x['interval']):x['analysis'] for x in row['signals']}
    advance(state,row['snapshots'],signals,row['ms'],row['paused']);last=row['ms']
 if state is None:raise ValueError('NO_RECORDED_INPUTS')
 return dict(replay=True,unseen_validation=False,state=state,evaluation={k:metrics(b,last) for k,b in state['books'].items()})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--inputs',required=True);p.add_argument('--output',required=True);args=p.parse_args()
 result=replay(args.inputs)
 # Exclusive creation prevents overwriting a live account or an older experiment.
 with open(args.output,'x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
