"""Paper futures profit protection, measured against original collateral."""
from decimal import Decimal

D = Decimal

def update(position, quote, execution):
    side = position['direction']
    qty = D(position['quantity'])
    entry = D(position['entry'])
    margin = D(position['initial_margin'])
    fee = D(execution['fee_rate'])
    slip = D(execution['slippage_rate'])
    funding = D(position.get('funding', '0'))
    entry_fee = D(position['entry_fee'])
    reference = D(str(quote['bid' if side == 1 else 'ask']))
    fill = reference * (1 - slip * side)
    net = qty * (fill - entry) * side + funding - entry_fee - qty * fill * fee
    peak = max(D(position.get('profit_lock_peak_net', '0')), net)
    position['profit_lock_peak_net'] = str(peak)
    if peak < margin * D('0.05') and not position.get('profit_lock_active'):
        return False
    target = peak * D('0.8')
    if side == 1:
        stop = (target + entry_fee - funding + qty * entry) / (qty * (1-slip) * (1-fee))
    else:
        stop = (qty * entry - entry_fee + funding - target) / (qty * (1+slip) * (1+fee))
    previous = position.get('profit_lock_stop')
    if previous is not None:
        stop = max(stop, D(previous)) if side == 1 else min(stop, D(previous))
    position.update(profit_lock_active=True, profit_lock_stop=str(stop),
                    profit_lock_target_net=str(target), profit_lock_threshold=str(margin * D('0.05')))
    return reference <= stop if side == 1 else reference >= stop
