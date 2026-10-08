"""Keep quote marking independent from provisional funding accounting."""
from zitar_futures_paper_engine_v1 import number, pnl, settle_funding

def update_pending(pos, events, ms):
    due = int(pos['next_funding_ms'])
    # A quote may still carry the just-expired funding forecast at entry.
    # Match settle_funding's holding interval: opened_ms < settlement <= exit.
    if due <= int(pos['opened_ms']):
        pos['funding_pending'] = False
        return
    # Exchange forecasts are not guaranteed to match settlement timestamps exactly.
    settled = any(abs(int(t)-due) <= 1000 for t in pos['funding_events'])
    pos['funding_pending'] = ms >= due and not settled

def reconcile_closed(book, market, ms):
    for pos in book['closed']:
        if not pos.get('funding_pending') or pos['symbol'] not in market:
            continue
        data = market[pos['symbol']]
        before = number(pos['funding'])
        wrapper = {'positions': {pos['symbol']: pos}, 'funding_total': '0'}
        settle_funding(wrapper, pos['symbol'], data.get('funding', []), pos['closed_ms'])
        update_pending(pos, data.get('funding', []), pos['closed_ms'])
        payment = number(pos['funding'])-before
        book['funding_total'] = str(number(book['funding_total'])+payment)
        raw = number(pos['margin'])+pnl(pos,pos['exit'])-number(pos['exit_fee'])
        net = max(number(0),raw)-number(pos['initial_margin'])-number(pos['entry_fee'])
        adjustment = net-number(pos['net_pnl'])
        book['cash'] = str(number(book['cash'])+adjustment)
        book['realized'] = str(number(book['realized'])+adjustment)
        pos.update(net_pnl=str(net),uncovered_model_deficit=str(max(number(0),-raw)))
        if payment or adjustment:
            book.setdefault('funding_adjustments',[]).append(dict(ms=ms,symbol=pos['symbol'],closed_ms=pos['closed_ms'],funding=str(payment),cash_adjustment=str(adjustment)))
