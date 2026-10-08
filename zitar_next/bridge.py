"""Read-only contract for later ZITAR integration; no production imports."""
import json
from zitar_next.store import Registry,workspace


def summary(root):
    root=workspace(root)
    registry=Registry(root).all()
    path=root/'status.json'
    status=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(state='NOT_STARTED')
    return dict(schema='ZITAR_NEXT_READONLY_BRIDGE_V1',coordinator='ZITAR',scope='NEXT_RESEARCH_ONLY',
                real_orders=False,production_connected=False,status=status,
                proposals=[dict(id=p['id'],market=p['body']['market'],symbol=p['body']['symbol'],
                                state=p['state'],eligible=p['body']['eligible'],issues=p['body']['issues'],
                                human_approval_required=True) for p in registry['proposals']],active_paper=registry['active'],
                instruction='Research evidence only. Never report automatic promotion or real execution.')
