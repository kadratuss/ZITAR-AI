"""Public dashboard scope for the user-selected futures-only deployment."""
def public(value):
    if isinstance(value,list):
        return [public(v) for v in value if not isinstance(v,dict) or
                (v.get('market')!='spot' and v.get('body',{}).get('market')!='spot')]
    if isinstance(value,dict):
        return {k:public(v) for k,v in value.items()
                if k not in ('spot','master','comparison') and not k.endswith('_SPOT')
                and not (isinstance(v,dict) and v.get('market')=='spot')}
    return value
