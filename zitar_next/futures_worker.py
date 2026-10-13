"""Futures-only production research entrypoint; original protocol modules remain frozen."""
from zitar_next.worker import *
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--init',action='store_true')
    parser.add_argument('--steps',type=int,default=2048)
    parser.add_argument('--symbol',default='BTCUSDT')
    parser.add_argument('--cycles',type=int,default=1,help='0: ongoing; positive: bounded rounds')
    parser.add_argument('--pause',type=float,default=300)
    args = parser.parse_args()
    if args.cycles<0 or not 60 <= args.pause <= 86400:
        parser.error('cycles >=0 and pause 60..86400 required')
    root = init(args.root) if args.init else workspace(args.root)
    with WorkerLock(root):
        cycle = 0
        market_path=root/'market_status.json'
        market_status=json.loads(market_path.read_text(encoding='utf-8')) if market_path.exists() else {}
        while args.cycles==0 or cycle<args.cycles:
            for market in ('futures',):
                try:
                    snapshot = fetch(market,args.symbol)
                    from zitar_next.paper import tick
                    paper = tick(root,market,args.symbol,snapshot)
                    body = train_round(root,market,args.symbol,args.steps,snapshot=snapshot)
                    market_status[market]=dict(state='COMPLETED' if body else 'WAITING_NEW_CANDLE',updated=stamp(),paper=paper['state'],error=None)
                    print(json.dumps(dict(market=market,state='COMPLETED' if body else 'WAITING_NEW_CANDLE',issues=body['issues'] if body else [])),flush=True)
                except Exception as exc:
                    market_status[market]=dict(state='ERROR',updated=stamp(),error=str(exc))
                    atomic(root/'status.json',dict(state='ERROR',market=market,error=str(exc),updated=stamp(),real_orders=False))
                    print(json.dumps(dict(market=market,error=str(exc))),flush=True)
                atomic(market_path,market_status)
            from zitar_next.bridge import summary
            atomic(root/'next_summary.json',summary(root))
            cycle += 1
            if args.cycles==0 or cycle<args.cycles:
                time.sleep(args.pause)


if __name__ == '__main__':
    main()
