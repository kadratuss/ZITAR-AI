"""Freeze comparison conditions and report existing evidence without model changes."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen
from zitar_next.store import digest, stamp, workspace

PROTOCOL=dict(version=1, name='ZITAR_COMPARISON_FROZEN_V1', interval='1h',
    initial_equity_usdt=10000, seeds=[42,73],
    arms=['zitar_hourly','learned_ppo','combined','cash','long','sma'],
    spot=dict(fee_per_side=.001,slippage_per_side=.001,sizing='full_equity_long_flat'),
    futures=dict(fee_per_side=.0005,slippage_per_side=.0002,leverage=3,
        margin_mode='ISOLATED',collateral_fraction=.1,funding='recorded_public_history'),
    stress_cost_multiplier=2, blend_selection='validation_only_fixed_grid',
    evaluation='all_seeds_and_unanimous_ensemble_no_best_seed_selection',
    promotion='human_only_independent_paper',real_orders=False,
    minimum_test_bars=150,minimum_trades=20,maximum_drawdown_pct=5,
    minimum_advantage_percentage_points=1,minimum_seeds=2)


def comparison(body):
    combined=body.get('combination')
    if not combined or combined.get('rule_name')!='RSI14':
        raise ValueError('RSI14 combined evidence required')
    arms={**body['baselines'],**combined['test']}
    if any(arm not in arms for arm in PROTOCOL['arms']):
        raise ValueError('complete comparison arms required')
    test=body['split']['partitions']['test']
    baseline=arms['zitar_hourly']['return_pct']
    return dict(run=body['run'],market=body['market'],symbol=body['symbol'],interval=body['interval'],
        test=test,selected_ai_weight=combined['selected_ai_weight'],
        arms={arm:{k:arms[arm][k] for k in ('return_pct','max_drawdown_pct','trades')}
            for arm in PROTOCOL['arms']},
        stress={arm:{k:v[k] for k in ('return_pct','max_drawdown_pct','trades')}
            for arm,v in combined['stress'].items()},
        delta_vs_rsi_percentage_points={arm:arms[arm]['return_pct']-baseline
            for arm in ('learned_ppo','combined')},
        fresh_validation=False, classification='HISTORICAL_REPLAY_NOT_NEW_EVIDENCE',
        eligible=body.get('eligible') is True and not body.get('issues'),issues=body.get('issues',[]),
        scope='independent hourly simulator; not full production runtime parity')


def freeze(root,state,output):
    root=workspace(root)
    selected={}
    for proposal in state['proposals']:
        body=proposal['body'];market=body['market']
        if market in selected or not body.get('combination') or body['interval']!='1h':continue
        run=body['run']
        if not re.fullmatch('(spot|futures)-[a-f0-9]{32}',run):raise ValueError('invalid run')
        folder=root/'runs'/run
        if folder.is_symlink():raise ValueError('symlink run')
        artifacts={}
        for name in ['snapshot.json','scaler.json','report.json']+[
                'ppo-'+str(s['seed'])+'.zip' for s in body['seed_results']]:
            path=folder/name
            if path.is_symlink():raise ValueError('symlink artifact')
            artifacts[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot=json.loads((folder/'snapshot.json').read_text())
        if digest(snapshot)!=body['snapshot_sha256']:raise ValueError('snapshot mismatch')
        if digest(json.loads((folder/'scaler.json').read_text()))!=body['scaler_sha256']:
            raise ValueError('scaler mismatch')
        for seed in body['seed_results']:
            if artifacts['ppo-'+str(seed['seed'])+'.zip']!=seed['model_sha256']:
                raise ValueError('model mismatch')
        saved=json.loads((folder/'report.json').read_text())
        saved.pop('proposal_id',None)
        def public(value):
            if isinstance(value,dict):return {k:public(v) for k,v in value.items() if k!='decisions'}
            if isinstance(value,list):return [public(v) for v in value]
            return value
        if digest(saved)!=proposal['id'] or public(saved)!=body:raise ValueError('report mismatch')
        report=comparison(body)
        selected[market]=dict(proposal=proposal['id'],artifacts=artifacts,report=report,
            future_evaluation_must_start_after_utc=report['test']['last_date'])
    if set(selected)!= {'spot','futures'}:raise ValueError('both markets required')
    manifest=dict(protocol=PROTOCOL,protocol_sha256=digest(PROTOCOL),created_utc=stamp(),
        candidates=selected,automatic_activation=False,real_orders=False,
        warning='Existing candidates are not eligible. Freeze is for research only; no paper promotion.')
    output=Path(output)
    output.mkdir(parents=False,exist_ok=False)
    (output/'protocol.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    lines=['# Sabit koşullarla mevcut deney karşılaştırması','',
        'Bu rapor yeni bağımsız test değildir. Mevcut adaylar etkinleştirilmedi.', '',
        '| Piyasa | Kol | Net getiri % | En büyük düşüş % | Dolum sayısı |',
        '|---|---|---:|---:|---:|']
    for market,item in selected.items():
        for arm,metric in item['report']['arms'].items():
            lines.append(f"| {market} | {arm} | {metric['return_pct']:.2f} | {metric['max_drawdown_pct']:.2f} | {metric['trades']} |")
    lines+=['','Pozitif fark tek başına uygunluk değildir. Tüm eşikler ve yeni veri gerekir.',
        'Üretim motoruyla tam eşlik henüz kanıtlanmadı. Gerçek emirler kapalı.']
    (output/'comparison.md').write_text('\n'.join(lines),encoding='utf-8')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    with urlopen('http://127.0.0.1:8080/zitar-next/api/state',timeout=30) as response:
        state=json.load(response)
    result=freeze(args.root,state,args.output)
    print(json.dumps(dict(protocol_sha256=result['protocol_sha256'],markets=list(result['candidates']),
                         output=args.output,real_orders=False)))
