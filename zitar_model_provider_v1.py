"""Single model boundary for ZITAR conversation and research roles."""
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit

BASE=Path(__file__).resolve().parent

def settings(base=BASE):
    config=json.loads((Path(base)/'zitar_model_config_v1.json').read_text(encoding='utf-8-sig'))
    if config.get('provider') != 'ollama':
        raise ValueError('UNSUPPORTED_MODEL_PROVIDER')
    url=urlsplit(config['base_url'])
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1','localhost') or url.username or url.password or url.query or url.fragment:
        raise ValueError('MODEL_ENDPOINT_MUST_BE_LOCAL')
    identity_path=Path(base)/config['identity_file']
    if identity_path.resolve().parent != Path(base).resolve():
        raise ValueError('INVALID_IDENTITY_PATH')
    identity=identity_path.read_text(encoding='utf-8')
    identity+='\nTemel model: '+config['base_model']+'. İnce ayar yapılmış: '+str(config['fine_tuned'])+'.'
    return config,identity

def chat(messages,role='conversation',json_mode=False,temperature=0.3,max_tokens=450,base=BASE):
    config,identity=settings(base)
    model=config.get('roles',{}).get(role,config['model'])
    content=[dict(role='system',content=identity)]+list(messages)
    payload=dict(model=model,messages=content,stream=False,keep_alive='30m',
                 options=dict(temperature=temperature,num_predict=min(max_tokens,300) if role=='conversation' else max_tokens,num_ctx=4096 if role in ('conversation','tool_planner') else 8192))
    if json_mode:payload['format']='json'
    request=urllib.request.Request(config['base_url'].rstrip('/')+'/api/chat',
          data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=max(180,config['timeout_seconds'])) as response:
        text=json.load(response).get('message',{}).get('content','').strip()
    if not text:raise ValueError('EMPTY_MODEL_RESPONSE')
    if json_mode:
        value=json.loads(text)
        if not isinstance(value,dict):raise ValueError('INVALID_AGENT_OUTPUT')
        return value
    return text
