"""One paper wallet, shared slots; each position retains its entry timeframe."""
from copy import deepcopy
from zitar_futures_paper_engine_v1 import fresh, signals, number, digest, open_position, close_position, POLICY

NAME = 'ZITAR_SHARED_MTF'
RULES = {'version': 'SHARED_MTF_V1', 'intervals': ['5m', '15m', '1h'],
         'slots': 10, 'rollover': '00:00 Europe/Istanbul',
         'signal': 'BASELINE majority; opposing latest closed 1h majority blocks entry',
         'priority': '1h then 15m then 5m, symbols sorted', 'exit': 'entry timeframe signal change or trailing stop'}

def ensure_book(state, ms):
    if NAME not in state['books']:
        book = deepcopy(fresh(ms, [])['books']['BASELINE'])
        book.update(started_ms=ms, rules=deepcopy(RULES), rules_hash=digest(RULES), cursors={}, evaluations={})
        state['books'][NAME] = book
    if state['books'][NAME]['rules_hash'] != digest(RULES):
        raise ValueError('SHARED_POLICY_CHANGED_NEW_EXPERIMENT_REQUIRED')

def evaluate(state, market, quotes, ms, closed_now, errors, name=NAME):
    book = state['books'][name]
    if book.get('retired_ms'):return
    if not set(book['positions']).issubset(quotes):
        return
    for interval, duration in [('1h', 3600000), ('15m', 900000), ('5m', 300000)]:
        for symbol in sorted(market):
            if symbol not in state['universe'] and state['universe']:continue
            data = market[symbol]
            if symbol not in quotes or 'timeframes' not in data:
                continue
            try:
                sig = signals(data['timeframes'][interval], ms, duration)
                candle = sig['candle_close_ms']; key = symbol + ':' + interval
                old = book['cursors'].get(key, book['started_ms'])
                if candle <= old:
                    continue
                previous = book['evaluations'].get(key)
                book['cursors'][key] = candle
                target = sig['BASELINE']; reason = 'SIGNAL_' + str(target)
                outcome = 'NO_ENTRY'; q = quotes[symbol]
                if ms - candle > 120000:
                    reason = 'LATE_SIGNAL'
                elif (name, symbol) in closed_now:
                    reason = 'STOP_CLOSED_THIS_CYCLE'
                else:
                    pos = book['positions'].get(symbol)
                    if pos and pos['timeframe'] != interval:
                        reason = 'OWNED_BY_' + pos['timeframe']
                    else:
                        if pos and pos['direction'] != target:
                            close_position(book, symbol, q, ms, 'SIGNAL_CHANGED')
                        upper = signals(data['timeframes']['1h'], ms)['BASELINE']
                        spread = (number(q['ask'])-number(q['bid'])) / ((number(q['ask'])+number(q['bid']))/2)*10000
                        if target and upper == -target:
                            reason = 'OPPOSING_1H'
                        elif spread > number(POLICY['max_spread_bps']):
                            reason = 'WIDE_SPREAD'
                        elif abs(number(q['funding_rate'])) > number(POLICY['max_abs_funding_rate']):
                            reason = 'HIGH_FUNDING'
                        elif target and name == 'ZITAR_SELECTIVE_V1' and upper != target:
                            reason = 'REQUIRE_1H_CONFIRMATION'
                        elif target and name == 'ZITAR_SELECTIVE_V1' and any(p['symbol']==symbol and ms-p['closed_ms']<900000 for p in book['closed']):
                            reason = 'REENTRY_COOLDOWN_15M'
                        elif target and name == 'ZITAR_TRIGGER_V2' and (previous is None or previous.get('candle_close_ms') != candle-duration or previous.get('direction') == target):
                            reason = 'WAIT_NEW_DIRECTION'
                        elif target and name == 'ZITAR_TRIGGER_V2' and symbol not in book['positions'] and sum(p['direction']==target for p in book['positions'].values())>=3:
                            reason = 'DIRECTION_LIMIT_3'
                        elif target:
                            outcome = open_position(book, symbol, target, q, data['contract'], ms, interval + ':' + reason)
                            if outcome == 'OPENED':
                                book['positions'][symbol].update(timeframe=interval, upper_1h_direction=upper)
                decision = dict(ms=ms, book=name, symbol=symbol, timeframe=interval, candle_close_ms=candle,
                                direction=target, reason=reason, result=outcome)
                book['evaluations'][key] = decision
                state['decisions'].append(decision)
            except (ValueError, KeyError) as exc:
                errors.append(symbol + ':' + interval + ':' + str(exc))
