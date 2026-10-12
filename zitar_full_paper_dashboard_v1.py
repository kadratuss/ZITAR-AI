"""Read-only loopback dashboard for the full paper runtime. No execution routes."""
import json
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def snapshot(base):
    def read(name):
        return json.loads((base / name).read_text(encoding='utf-8-sig'))
    runtime = read('zitar_full_paper_runtime_v1.json')
    master = read('zitar_master_portfolio_v1.json')
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(runtime['heartbeat_utc'])).total_seconds()
    cycle = runtime.get('cycle_started_utc')
    cycle_age = (datetime.now(timezone.utc) - datetime.fromisoformat(cycle)).total_seconds() if cycle else None
    runtime['heartbeat_age_seconds'] = round(age, 1)
    runtime['live_health'] = ('STALE' if age > 30 or (cycle_age is not None and cycle_age > 90)
                              else runtime['state'])
    research = []
    for label, name in [('Project Memory','zitar_core_project_memory_v1.jsonl'),
                        ('Learning Journal','zitar_core_learning_journal_v1.jsonl'),
                        ('Research Memory','zitar_research_memory_v1.jsonl'),
                        ('Evidence','zitar_core_research_evidence_v1.jsonl'),
                        ('Knowledge Gaps','zitar_core_knowledge_gap_v1.jsonl'),
                        ('Finance Bridge','zitar_finance_unified_bridge_v1_1.json')]:
        path = base / name
        research.append(dict(module=label, present=path.exists(),
                             modified_utc=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if path.exists() else None,
                             health='FILE_PRESENT_RUNTIME_NOT_VERIFIED' if path.exists() else 'MISSING'))
    try:
        comparison = read('zitar_comparison_runtime_v1.json')
    except FileNotFoundError:
        comparison = None
    except (OSError, ValueError) as exc:
        comparison = {'error': str(exc)}
    return {'runtime': runtime, 'master': master, 'research': research, 'comparison': comparison,
            'served_utc': datetime.now(timezone.utc).isoformat()}


# Reuses the verified 5017 Control Center data endpoints; this module never writes state.
import concurrent.futures
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import parse_qs, urlencode

MODULES = [
    ('cost_study','İşlem Maliyeti ve Likidite','zitar_cost_liquidity_study_v1.json','intelligence','Master maliyet modeli, canlı spread gözlemleri ve tarihli likidite örnekleri.','Master cost model, live spread observations and dated liquidity samples.'),
    ('research_runtime','Araştırma Döngüsü','zitar_research_runtime_v1.json','memory','Yerel kanıt kuyruğu, doğrulama ve kontrollü öğrenme durumu.','Local evidence queue, validation and controlled learning status.'),
    ('mtf','Multi-Timeframe Research','zitar_mtf_research_v2.json','intelligence','Zaman dilimleri, piyasa yapısı ve kanıtlar.','Timeframe structure and evidence.'),
    ('research','AI Research + Memory/RAG','zitar_research_memory_v1.jsonl','intelligence','Versiyonlu araştırma gözlemleri ve provenance.','Versioned research observations and provenance.'),
    ('radar','Event & Pump Radar','zitar_event_news_radar_v2_4.json','intelligence','Kaydedilmiş haber ve anomali araştırması.','Saved news and anomaly research.'),
    ('futures','Futures Intelligence','zitar_futures_evidence_v1.json','intelligence','OI, funding ve futures kanıtları; execution kapalı.','OI, funding and futures evidence; execution off.'),
    ('voice','Voice ZİTAR','zitar_voice_end_to_end_lab_v2.py','intelligence','Yerel ses bileşeni mevcut; bu panelden başlatılmaz.','Local voice component; not started from this panel.'),
    ('integrity','Research Integrity','zitar_claim_provenance_audit_v1_1.json','intelligence','Claim ve provenance denetim kayıtları.','Saved claim and provenance audits.'),
    ('liquidity','Liquidity Intelligence','zitar_liquidity_profile_v1.json','intelligence','Spread, derinlik ve likidite gözlemleri.','Spread, depth and liquidity observations.'),
    ('agents','Multi-Agent Intelligence','agent_runner_state.db','intelligence','Agent state dosyası; servis sağlığı ayrıca doğrulanmalıdır.','Agent state file; service health requires separate verification.'),
    ('project_memory','Project Memory','zitar_core_project_memory_v1.jsonl','memory','Kalıcı proje bilgileri ve kaynakları.','Persistent project facts and sources.'),
    ('learning','Learning Journal','zitar_core_learning_journal_v1.jsonl','memory','Öğrenme kayıtları, kanıt ve önceki durum.','Learning records, evidence and prior state.'),
    ('gaps','Knowledge Gaps','zitar_core_knowledge_gap_v1.jsonl','memory','Araştırılması gereken bilgi eksikleri.','Knowledge gaps awaiting research.'),
    ('plans','Research Plans','zitar_core_research_plans_v1.jsonl','memory','Kayıtlı araştırma planları.','Saved research plans.'),
    ('evidence','Evidence','zitar_core_research_evidence_v1.jsonl','memory','Araştırma kanıtları ve dayanakları.','Research evidence and supporting sources.'),
    ('finance','Finance Bridge','zitar_finance_unified_bridge_v1_1.json','memory','Finans bağlamı ve birleşik kanıt paketi.','Financial context and unified evidence packet.'),
    ('regression','ZİTAR Full Regression','zitar_full_regression_suite_v1.json','experiments','Mevcut tam regression sonuçları ve kayıt zamanı.','Existing full regression results and record time.'),
    ('market_cycle','Market Intelligence Cycle','zitar_market_intelligence_cycle_v1.json','experiments','Araştırma döngüsünün kaydedilmiş aşama sonuçları.','Saved research-cycle stage results.'),
    ('selection','Selection Engine','zitar_selection_engine_v1.json','experiments','Kaydedilmiş seçim/risk gözlemleri; emir üretmez.','Saved selection/risk observations; no orders.'),
    ('strategy_eval','Strategy Evaluation','strategy_evaluation_v3.json','experiments','Kaydedilmiş strateji değerlendirmesi.','Saved strategy evaluation.'),
    ('chat_regression','Chat Regression','zitar_chat_regression_v1.json','experiments','Grounded chat test kayıtları.','Grounded chat test records.'),
]


def module_data(base, module_id, include_data=False):
    row = next((r for r in MODULES if r[0] == module_id), None)
    if row is None:
        raise KeyError('Unknown module')
    id_, title, filename, group, desc, desc_en = row
    path = base / filename
    available = path.is_file()
    data, count = None, None
    if available and path.suffix in ('.json', '.jsonl'):
        if path.stat().st_size > 4_000_000:
            raise ValueError('Module data exceeds preview size limit')
        text = path.read_text(encoding='utf-8-sig')
        if path.suffix == '.jsonl':
            lines = [x for x in text.splitlines() if x.strip()]
            count = len(lines)
            if include_data:
                data = [json.loads(x) for x in lines[-30:]]
        elif include_data:
            data = json.loads(text)
    elif available and include_data:
        data = {'component_exists': True, 'service_health': 'UNVERIFIED',
                'note': 'Component metadata only; no source execution or database mutation.'}
    result = dict(id=id_, title=title, group=group, description=desc, description_en=desc_en,
                  available=available, record_count=count,
                  modified_utc=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if available else None)
    if include_data:
        if not available:
            raise FileNotFoundError('Module record is unavailable: ' + title)
        result['data'] = data
    return result


def fetch_local(url, payload=None, timeout=15):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={'Content-Type':'application/json', 'User-Agent':'ZITAR-Unified-Control/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def services():
    endpoints = [('Research / RAG', 'http://127.0.0.1:5012/api/research/health'),
                 ('ZİTAR Chat', 'http://127.0.0.1:5016/api/chat/health'),
                 ('Ollama / Qwen', 'http://127.0.0.1:11434/api/tags')]
    def probe(item):
        name, url = item
        try:
            data = fetch_local(url, timeout=3)
            if name.startswith('Research'):
                ok = data.get('chain_valid') is True
                detail = 'Memory chain: '+('OK' if ok else 'FAIL')+' · '+str(data.get('record_count', '?'))+' records'
            elif name == 'ZİTAR Chat':
                ok = data.get('ok') is True
                detail = 'API health · '+str(data.get('symbols', '?'))+' symbols'
            else:
                names = [x.get('name', '') for x in data.get('models', [])]
                ok = True
                detail = 'Installed models: '+', '.join(names) if names else 'Service reachable; no installed models'
            return dict(name=name, status='ONLINE' if ok else 'DEGRADED', detail=detail,
                        checked_utc=datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            return dict(name=name, status='OFFLINE', detail=str(exc), checked_utc=datetime.now(timezone.utc).isoformat())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        return {'services': list(pool.map(probe, endpoints))}


def make_server(base, port=5020):
    base = Path(base)
    from zitar_indicator_lab_v1 import start_worker as start_indicator_lab
    start_indicator_lab(base)
    from pa_v1.runtime import start_worker as start_pa_v1
    if not (base/'zitar_futures_only.flag').exists():start_pa_v1(base)
    cache = {'time':0, 'data':None}
    cache_lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, value, status=200, html=False):
            body = value.encode('utf-8') if html else json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlsplit(self.path)
            route, query = parsed.path, parse_qs(parsed.query)
            try:
                if route == '/api/pa-v1':
                    from pa_v1.runtime import overview
                    return self.send(overview(base))
                if route == '/api/assistant-artifact':
                    from assistant_foundation.chat_tools import read_report
                    try:raw=read_report(base,query.get('session_id',[''])[0],query.get('task_id',[''])[0])
                    except (ValueError,KeyError):return self.send({'error':'Artifact not found'},404)
                    self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.send_header('Content-Disposition','attachment; filename=zitar-rapor.txt');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
                if route == '/api/paper-reset':
                    from zitar_reset_control_v1 import status
                    return self.send(status(base))
                if route == '/api/learning-progress':
                    from zitar_learning_progress_v1 import overview
                    return self.send(overview(base))
                if route == '/api/bollinger-pair':
                    from zitar_bollinger_pair_v1 import overview
                    return self.send(overview(base))
                if route == '/api/rsi-repair':
                    from zitar_rsi_repair_v1 import overview
                    return self.send(overview(base))
                if route == '/api/rsi-timeframes':
                    from zitar_rsi_timeframes_v1 import overview
                    return self.send(overview(base))
                if route == '/api/momentum-experiment':
                    from zitar_momentum_experiment_v2 import overview
                    return self.send(overview(base))
                if route == '/api/research-experiment':
                    from zitar_research_experiment_v1 import overview
                    return self.send(overview(base))
                if route == '/api/indicator-lab':
                    from zitar_indicator_lab_v1 import overview
                    return self.send(overview(base))
                if route == '/api/credentials/health':
                    from zitar_api_vault_v1 import health
                    return self.send(health())
                if route in ('/', '/index.html'):
                    # Load the template on each visit: later UI edits need no runtime restart.
                    return self.send((Path(__file__).with_suffix('.html')).read_text(encoding='utf-8'), html=True)
                if route in ('/api/snapshot', '/health'):
                    result = snapshot(base)
                    if route == '/health':
                        health = result['runtime']['live_health']
                        return self.send({'status':health}, 200 if health == 'RUNNING' else 503)
                    return self.send(result)
                if route == '/api/dashboard':
                    with cache_lock:
                        if cache['data'] is None or time.monotonic()-cache['time']>4:
                            result = fetch_local('http://127.0.0.1:5017/api/dashboard', timeout=15)
                            if not isinstance(result.get('strategies'), dict):
                                raise ValueError('V3 service returned invalid data')
                            cache.update(time=time.monotonic(),data=result)
                        return self.send(cache['data'])
                if route == '/api/modules':
                    return self.send({'modules':[module_data(base, r[0]) for r in MODULES]})
                if route == '/api/module':
                    return self.send(module_data(base, (query.get('id') or [''])[0], True))
                if route == '/api/services':
                    return self.send(services())
                if route == '/api/market-discovery':
                    from zitar_discovery_monitor_v1 import overview
                    return self.send(overview(base))
                if route == '/api/futures-paper':
                    from zitar_futures_paper_monitor_v1 import overview
                    return self.send(overview(base))
                if route == '/api/candidate-monitor':
                    from zitar_candidate_monitor_v1 import overview
                    return self.send(overview(base))
                if route == '/api/trade-context':
                    from zitar_trade_context_v1 import report
                    return self.send(report(base))
                if route == '/api/research-team':
                    from zitar_research_council_v1 import dashboard
                    return self.send(dashboard(base,(query.get('session_id') or [''])[0]))
                if route == '/api/research-job':
                    from zitar_research_council_v1 import get_job
                    return self.send(get_job(base,(query.get('id') or [''])[0],(query.get('session_id') or [''])[0]))
                if route == '/api/chat-proxy/history':
                    from zitar_unified_chat_v1 import history
                    return self.send({'turns': history(base, (query.get('session_id') or ['default'])[0])})
                if route == '/api/chat-proxy/health':
                    return self.send({'ok':True,'service':'ZITAR_UNIFIED_CHAT_V1','execution_authority':False})
                research_routes = {'health','symbols','context','latest','history','changes'}
                if route.startswith('/api/research-proxy/') and route.rsplit('/',1)[-1] in research_routes:
                    suffix = route.rsplit('/',1)[-1]
                    upstream = 'http://127.0.0.1:5012/api/research/'+suffix
                    if 'symbol' in query:
                        symbol = query['symbol'][0]
                        if not symbol.isalnum() or len(symbol)>30:
                            raise ValueError('Invalid symbol')
                        upstream += '?' + urlencode({'symbol':symbol})
                    result=fetch_local(upstream, timeout=5)
                    if suffix == 'context':
                        from zitar_market_memory_cycle_v1 import metadata
                        result['refresh_status']=metadata(base)
                    return self.send(result)
                self.send({'error':'Not found'},404)
            except KeyError as exc:
                self.send({'error':str(exc)},404)
            except Exception as exc:
                self.send({'error':type(exc).__name__, 'detail':str(exc), 'real_orders':False},503)

        def do_POST(self):
            if self.path == '/api/paper-reset':
                if self.headers.get('Origin') not in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'} or self.headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}:
                    return self.send({'error':'Origin or Host not allowed'},403)
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=128:raise ValueError('INVALID_SIZE')
                    from zitar_reset_control_v1 import request
                    return self.send(request(base,json.loads(self.rfile.read(size))))
                except ValueError:return self.send({'error':'RESET_CONFIRMATION_REQUIRED'},400)
            if self.path == '/api/paper-control':
                if self.headers.get('Origin') not in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'} or self.headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}:
                    return self.send({'error':'Origin or Host not allowed'},403)
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=256:raise ValueError('INVALID_SIZE')
                    payload=json.loads(self.rfile.read(size))
                    from zitar_market_controls_v1 import update
                    return self.send(update(base,payload.get('market'),payload.get('action')))
                except (ValueError,AttributeError):return self.send({'error':'Kontrol isteği geçersiz veya bu piyasa kapalı.'},400)
            if self.path == '/api/credentials/verify':
                if self.headers.get('Origin') not in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'} or self.headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}:
                    return self.send({'error':'Origin or Host not allowed'},403)
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=128:raise ValueError('INVALID_SIZE')
                    payload=json.loads(self.rfile.read(length))
                    if not isinstance(payload,dict):raise ValueError('INVALID_PAYLOAD')
                    from zitar_api_vault_v1 import verify_saved
                    return self.send(verify_saved(payload.get('exchange')))
                except ValueError as exc:return self.send({'error':str(exc)},400)
                except Exception:return self.send({'error':'VERIFICATION_FAILED'},503)
            if self.path == '/api/credentials':
                if self.headers.get('Origin') not in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'} or self.headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}:
                    return self.send({'error':'Origin or Host not allowed'},403)
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=2048:raise ValueError('INVALID_SIZE')
                    payload=json.loads(self.rfile.read(length))
                    if not isinstance(payload,dict):raise ValueError('INVALID_PAYLOAD')
                    from zitar_api_vault_v1 import save
                    return self.send(save(base,payload))
                except ValueError as exc:return self.send({'error':str(exc)},400)
                except Exception:return self.send({'error':'SECURE_STORAGE_FAILED'},503)

            if self.path == '/api/spot-control':
                allowed={f'http://127.0.0.1:{port}',f'http://localhost:{port}'}
                if self.headers.get('Origin') not in allowed or self.headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}:
                    return self.send({'error':'Origin or Host not allowed'},403)
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=256:raise ValueError('INVALID_SIZE')
                    payload=json.loads(self.rfile.read(length))
                    from zitar_spot_control_v1 import update
                    return self.send(update(base,payload.get('action')))
                except (ValueError,AttributeError):return self.send({'error':'Invalid control request'},400)

            if self.path == '/api/futures-paper/leverage':
                if self.headers.get('Origin') not in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'}:
                    return self.send({'error':'Origin not allowed'},403)
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=1024: return self.send({'error':'Invalid payload size'},400)
                    payload=json.loads(self.rfile.read(length).decode('utf-8'))
                    from zitar_futures_settings_v1 import request_change
                    return self.send(request_change(base,payload.get('leverage')))
                except (ValueError,KeyError) as exc:
                    return self.send({'error':str(exc)},409)
                except Exception as exc:
                    return self.send({'error':str(exc)},503)
            if self.path != '/api/chat-proxy/chat':
                return self.send({'error':'No order or mutation endpoint'},404)
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'}:
                return self.send({'error':'Origin not allowed'},403)
            try:
                length = int(self.headers.get('Content-Length','0'))
                if length<=0 or length>8192:
                    return self.send({'error':'Invalid message size'},400)
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                question = payload.get('question')
                if not isinstance(question,str) or not question.strip() or len(question)>4000:
                    return self.send({'error':'Invalid question'},400)
                # User-triggered local chat only. Existing service writes its own chat audit.
                from zitar_unified_chat_v1 import answer
                result = answer(base, question, payload.get('session_id', 'default'))
                self.send(result)
            except Exception as exc:
                self.send({'error':'chat_api_unavailable','detail':str(exc),'execution_authority':False},503)
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)
