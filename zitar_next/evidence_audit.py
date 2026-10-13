"""Read-only research evidence inventory; never trains or promotes a model."""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from urllib.request import urlopen


def audit(state):
    rows=[]
    issues=Counter()
    for proposal in state.get('proposals', []):
        body=proposal['body']
        failures=body.get('issues', [])
        issues.update(failures)
        seeds=body.get('combination', {}).get('seed_results', body.get('seed_results', []))
        metrics=[s['test'] for s in seeds]
        partition=body.get('split', {}).get('partitions', {}).get('test', {})
        policy=body.get('policy', {})
        eligible=body.get('eligible') is True and not failures
        rows.append(dict(id=proposal['id'], run=body.get('run'), market=body.get('market'),
            symbol=body.get('symbol'), interval=body.get('interval'), state=proposal['state'],
            eligible=eligible, test_bars=partition.get('retained_rows'),
            test_start_utc=partition.get('first_date'), test_end_utc=partition.get('last_date'),
            seeds=[dict(seed=s['seed'], **s['test']) for s in seeds],
            zero_trade=bool(metrics) and all(m.get('trades', 0)==0 for m in metrics),
            seed_returns_disagree=bool(metrics) and min(m['return_pct'] for m in metrics)<0<max(m['return_pct'] for m in metrics),
            reused_test='TEST_PERIOD_OVERLAPS_PREVIOUS_ROUND' in failures,
            history_insufficient='LONGER_WALK_FORWARD_HISTORY_REQUIRED' in failures,
            policy=policy, issues=failures,
            assessment='HISTORICAL_GATES_PASSED_NOT_LIVE_PROOF' if eligible else 'NOT_ELIGIBLE'))
    return dict(schema='ZITAR_EVIDENCE_AUDIT_V1', generated_utc=datetime.now(timezone.utc).isoformat(),
        scope='READ_ONLY_RESEARCH_INVENTORY', real_orders=False, automatic_activation=False,
        proposal_count=len(rows), eligible_count=sum(r['eligible'] for r in rows),
        zero_trade_count=sum(r['zero_trade'] for r in rows),
        mixed_seed_return_count=sum(r['seed_returns_disagree'] for r in rows),
        reused_test_count=sum(r['reused_test'] for r in rows),
        active_paper_count=len(state.get('active', [])), issues=dict(issues), candidates=rows,
        limits=['Registry view contains up to 50 recent candidates plus active/accepted/archived versions.',
                'No live performance conclusion or capacity certification follows from this inventory.',
                'Displayed combined seed metrics do not replace evidence for the deployed unanimous ensemble.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    args=parser.parse_args()
    with urlopen(f'http://127.0.0.1:{args.port}/zitar-next/api/state', timeout=30) as response:
        state=json.load(response)
    print(json.dumps(audit(state), ensure_ascii=False, indent=2, allow_nan=False))
