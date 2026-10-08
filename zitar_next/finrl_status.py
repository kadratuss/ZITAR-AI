"""Read-only, bounded FinRL-X report summaries for the console."""
import json
import re
from zitar_next.store import workspace


def reports(root):
    root=workspace(root)
    folder=root/'finrlx_reports'
    if not folder.exists():
        return []
    if folder.is_symlink():
        raise ValueError('report directory symlink rejected')
    result=[]
    for path in sorted(folder.glob('*.json'))[-20:]:
        if not re.fullmatch(r'(spot|futures)-[a-f0-9]{32}',path.stem):
            continue
        if path.is_symlink() or path.stat().st_size>5_000_000:
            raise ValueError('invalid report file')
        value=json.loads(path.read_text(encoding='utf-8'))
        result.append({k:value[k] for k in ('run','market','symbol','status','backend','weight_backtest',
                                           'authoritative_net_metrics','eligible','assumptions')})
    return result

