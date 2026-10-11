"""Risk-sized diagnostic scalping; does not approve strategies or send orders."""
from decimal import Decimal as D
from zitar_futures_paper_engine_v1 import open_position

RULES={'version':'SCALP_RISK_V1','risk_per_trade':'0.0025','portfolio_risk':'0.01',
       'daily_loss':'0.01','daily_fees':'0.0025','max_positions':3,'cooldown_bars':3,
       'interval':'1m','stop_price_pct':'0.005','leverage':20,'paper_only':True,
       'limitations':'Estimated risk includes modeled fees, slippage and spread; gaps may exceed it.'}

def number(value):
    x=D(str(value))
    if not x.is_finite():raise ValueError('NONFINITE_RISK_INPUT')
    return x

def cost_fraction(book,quote):
    bid,ask=number(quote['bid']),number(quote['ask'])
    if bid<=0 or ask<bid:raise ValueError('INVALID_SPREAD')
    policy=book['execution_policy']
    return 2*number(policy['fee_rate'])+2*number(policy['slippage_rate'])+(ask-bid)/bid

def planned_risk(book):
    total=D(0)
    for p in book['positions'].values():
        total+=max(D(0),number(p.get('planned_risk',number(p['initial_margin'])*D('.15'))))
    return total

def enter(book,symbol,direction,quote,contract,ms,candle):
    rules=RULES
    equity=number(book['equity'])
    if equity<=0:return 'NO_EQUITY'
    if len(book['positions'])>=rules['max_positions']:return 'RISK_SLOTS_FULL'
    closed=[p['closed_ms'] for p in book.get('closed',[]) if p['symbol']==symbol]
    if closed and candle<=((max(closed)//60000)+rules['cooldown_bars'])*60000:
        return 'SCALP_COOLDOWN_3_BARS'
    used_fees=number(book['fees_total'])-number(book.get('period_fees_start','0'))
    if used_fees>=number(book['period_start'])*number(rules['daily_fees']):return 'DAILY_FEE_BUDGET'
    risk=min(equity*number(rules['risk_per_trade']),equity*number(rules['portfolio_risk'])-planned_risk(book))
    if risk<=0:return 'PORTFOLIO_RISK_BUDGET'
    fraction=number(book['stop_pct'])+cost_fraction(book,quote)
    if fraction<=0:raise ValueError('INVALID_RISK_FRACTION')
    leverage=number(book['execution_policy']['leverage'])
    if leverage<=0:raise ValueError('INVALID_LEVERAGE')
    margin=risk/fraction/leverage
    # Reserve round-trip fees against today's remaining budget before opening.
    fee_remaining=number(book['period_start'])*number(rules['daily_fees'])-used_fees
    if margin*leverage*number(book['execution_policy']['fee_rate'])*2>fee_remaining:
        return 'DAILY_FEE_BUDGET'
    original_slot=book['slot']
    try:
        book['slot']=str(min(number(original_slot),margin))
        result=open_position(book,symbol,direction,quote,contract,ms,'SCALP_RISK_V1')
    finally:book['slot']=original_slot
    if result=='OPENED':
        p=book['positions'][symbol]
        p.update(planned_risk=str(number(p['quantity'])*number(p['entry'])*fraction),risk_version=rules['version'])
    return result
