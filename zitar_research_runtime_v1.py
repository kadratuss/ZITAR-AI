"""Local evidence queue and strict learning writer; no trading or automatic web queries."""
import argparse
import csv
import io
import hashlib
import json
import os
from pathlib import Path
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from decimal import Decimal
from zitar_paper_supervisor_v1 import FileLock


def sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def rows(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8-sig').splitlines() if x.strip()] if path.exists() else []


def stamp():
    return datetime.now(timezone.utc).isoformat()


def check_hash(value, field):
    body = dict(value)
    claimed = body.pop(field, None)
    if claimed != sha(body):
        raise ValueError('HASH_MISMATCH:' + field)


def check_chain(records):
    previous = None
    for row in records:
        field = 'previous_record_sha256' if row.get('schema') == 'ZITAR_CORE_LEARNING_JOURNAL_V2' else 'previous_sha256'
        if row.get(field) != previous:
            raise ValueError('CHAIN_PREVIOUS_MISMATCH')
        check_hash(row, 'record_sha256')
        previous = row['record_sha256']


def atomic(path, payload, before=None):
    tmp = path.with_suffix(path.suffix + '.research.tmp')
    with tmp.open('wb') as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    if before is not None and path.read_bytes() != before:
        raise ValueError('EXTERNAL_WRITER_CONFLICT')
    for attempt in range(8):
        try:
            os.replace(tmp, path)
            return
        except OSError as exc:
            if getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == 7:
                raise
            time.sleep(min(.025 * 2**attempt, .5))


def verify_candidate(candidate, evidence):
    check_hash(candidate, 'candidate_sha256')
    check_hash(evidence, 'bundle_sha256')
    if candidate.get('evidence_bundle_sha256') != evidence['bundle_sha256']:
        raise ValueError('EVIDENCE_LINK_MISMATCH')
    if candidate.get('status') != 'VALIDATED_CANDIDATE' or candidate.get('next_required_stage') != 'CONTROLLED_LEARNING_JOURNAL_WRITE':
        raise ValueError('CANDIDATE_NOT_READY')
    for obj, flags in [(candidate, ('real_order','silent_code_rewrite','persistent_memory_write')),
                       (evidence, ('real_order','silent_code_rewrite','memory_write'))]:
        if any(obj.get('authorities', {}).get(k) is not False for k in flags):
            raise ValueError('AUTHORITY_NOT_OFF')
    if evidence.get('learning_candidate_ready') is not True or evidence.get('corroborated') is not True:
        raise ValueError('INSUFFICIENT_EVIDENCE')
    if candidate.get('question') != evidence.get('question') or candidate.get('claims') != evidence.get('candidate_claims'):
        raise ValueError('CLAIM_OR_QUESTION_MISMATCH')
    sources = evidence.get('sources', [])
    policy_v1 = evidence.get('source_policy_schema') == 'ZITAR_SOURCE_POLICY_V1'

    if policy_v1:
        # New evidence must carry immutable source-family provenance.
        # Missing family data fails closed instead of silently falling back
        # to the legacy hostname/provider independence rule.
        for source in sources:
            if not source.get('provider_family'):
                raise ValueError('SOURCE_PROVIDER_FAMILY_REQUIRED')
            if not source.get('policy_reason'):
                raise ValueError('SOURCE_POLICY_REASON_REQUIRED')

        expected = [
            {k: s.get(k) for k in (
                'role',
                'provider',
                'url',
                'content_sha256',
                'provider_family',
                'policy_reason',
            )}
            for s in sources
        ]
    else:
        # Legacy evidence remains verifiable without rewriting old hashes
        # or mutating the append-only learning journal.
        expected = [
            {k: s.get(k) for k in ('role','provider','url','content_sha256')}
            for s in sources
        ]

    if candidate.get('source_provenance') != expected:
        raise ValueError('PROVENANCE_MISMATCH')

    # Full cached text is required: a hash alone cannot be verified.
    for source in sources:
        text = source.get('snapshot_text')
        if not isinstance(text, str) or not text:
            raise ValueError('SOURCE_SNAPSHOT_REQUIRED')
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != source.get('content_sha256'):
            raise ValueError('SOURCE_CONTENT_HASH_MISMATCH')
        parsed = urlsplit(source.get('url', ''))
        if parsed.scheme != 'https' or not parsed.hostname or source.get('error') or source.get('http_status') != 200:
            raise ValueError('INVALID_SOURCE')
    primary = [s for s in sources if s.get('role') == 'PRIMARY']
    other = [s for s in sources if s.get('role') == 'INDEPENDENT']
    if not primary or not other:
        raise ValueError('TWO_SOURCE_ROLES_REQUIRED')
    if policy_v1:
        from zitar_source_policy_v1 import corroboration_allowed

        # Independence is defined by approved provider family, not merely by
        # a different hostname or display/provider string.
        if not any(corroboration_allowed(a, b) for a in primary for b in other):
            raise ValueError('INDEPENDENT_PROVIDER_FAMILY_REQUIRED')
    else:
        # Legacy evidence retains the historical minimum provenance rule.
        if not any(urlsplit(a['url']).hostname != urlsplit(b['url']).hostname and
                   a.get('provider') != b.get('provider') for a in primary for b in other):
            raise ValueError('DISTINCT_SOURCE_REQUIRED')
    claims = candidate.get('claims', [])
    if not claims:
        raise ValueError('NO_CLAIMS')
    for claim in claims:
        text = claim.get('claim', '').strip()
        # Restrict autonomous promotion to exact source statements. Paraphrases
        # and model-generated conclusions need a separate semantic validator.
        if not text or not all(any(text in s['snapshot_text'] for s in group) for group in (primary, other)):
            raise ValueError('CLAIM_LITERAL_SUPPORT_REQUIRED')
    return True


def promote(base, candidate, evidence):
    path = base / 'zitar_core_learning_journal_v1.jsonl'
    guard = FileLock(base / 'zitar_research_memory_writer.lock')
    if not guard.acquire():
        raise ValueError('MEMORY_WRITER_BUSY')
    try:
        before = path.read_bytes() if path.exists() else b''
        records = rows(path)
        check_chain(records)
        check_hash(candidate, 'candidate_sha256')
        existing = [r for r in records if r.get('candidate_sha256') == candidate['candidate_sha256']]
        if existing:
            if len(existing) != 1 or existing[0].get('claims') != candidate.get('claims') or existing[0].get('evidence_bundle_sha256') != candidate.get('evidence_bundle_sha256'):
                raise ValueError('EXISTING_CANDIDATE_CONFLICT')
            return 'ALREADY_RECORDED_NOT_REVALIDATED'
        verify_candidate(candidate, evidence)
        record = dict(schema='ZITAR_CORE_LEARNING_JOURNAL_V2', domain=candidate['domain'],
                      lesson_type='SOURCE_STATEMENTS', topic=candidate.get('topic'), observation=candidate['question'],
                      claims=candidate['claims'], source_provenance=candidate['source_provenance'],
                      candidate_sha256=candidate['candidate_sha256'], evidence_bundle_sha256=evidence['bundle_sha256'],
                      validation_scope='HASH_CHAIN_AND_LITERAL_CORROBORATION_NOT_GENERAL_FACT_CHECK',
                      outcome='RECORDED_CORROBORATED_SOURCE_STATEMENTS', version=2, created_utc=stamp(),
                      previous_record_sha256=records[-1]['record_sha256'] if records else None,
                      execution_authority=False, silent_code_rewrite_authority=False)
        record['record_sha256'] = sha(record)
        check_chain(records + [record])
        suffix = (b'\n' if before and not before.endswith(b'\n') else b'') + (json.dumps(record, ensure_ascii=False) + '\n').encode()
        if not path.exists():
            path.touch(exist_ok=False)
        atomic(path, before + suffix, before)
        return 'RECORDED'
    finally:
        guard.close()


def local_jobs(base):
    memory = rows(base / 'zitar_core_project_memory_v1.jsonl')
    learning = rows(base / 'zitar_core_learning_journal_v1.jsonl')
    check_chain(memory)
    check_chain(learning)
    jobs = []
    from zitar_unified_chat_v1 import pending_gaps
    for gap in rows(base / 'zitar_core_knowledge_gap_v1.jsonl') + pending_gaps(base):
        if gap.get('status') != 'OPEN':
            continue
        question = gap.get('question', '')
        tokens = set(re.findall(r'\w+', question.casefold())) - {'ne','bu','bir','için','mi','mu','bundan','peki'}
        hits = [r['record_sha256'] for r in memory + learning
                if (r.get('project') or r.get('domain')) == gap.get('domain') and
                tokens & set(re.findall(r'\w+', json.dumps(r, ensure_ascii=False).casefold()))]
        vague = any(x in question.casefold() for x in ('bundan ne öğrendin', 'bilmediğim bu konu')) or len(tokens) < 3
        body = dict(gap_id=gap.get('identity_sha256'), domain=gap.get('domain'), question=question,
                    local_record_hashes=hits, status='NEEDS_CONCRETE_QUESTION' if vague else 'NEEDS_EXTERNAL_EVIDENCE',
                    evidence_sufficient=False, next_stage='DEFINE_QUESTION' if vague else 'PRIMARY_SOURCE_RESEARCH')
        body['job_id'] = sha(body)
        jobs.append(body)
    return jobs


def cost_model(fee, slippage):
    f, s = Decimal(str(fee)), Decimal(str(slippage))
    if not all(v.is_finite() and 0 <= v < 1 for v in (f, s)):
        raise ValueError('INVALID_COST_MODEL')
    factor = (1-s)*(1-f)/((1+s)*(1+f))
    return {'fee_rate': str(f), 'slippage_rate': str(s),
            'flat_reference_roundtrip_loss_pct': str((1-factor)*100),
            'reference_breakeven_rise_pct': str((1/factor-1)*100)}


def cost_study(base):
    master_path = base / 'zitar_master_portfolio_v1.json'
    raw = master_path.read_bytes()
    master = json.loads(raw.decode('utf-8-sig'))
    model = cost_model(master['rules']['fee_rate'], master['rules']['slippage_rate'])
    engine_path = base / 'zitar_master_paper_engine_v1.py'
    engine_hash = hashlib.sha256(engine_path.read_bytes()).hexdigest()
    study_id = sha({'model':model, 'engine_sha256':engine_hash, 'formula_version':1})
    observations = []
    for symbol, pos in master['account']['positions'].items():
        bid, ask = Decimal(pos.get('live_bid','0')), Decimal(pos.get('live_ask','0'))
        if not (bid.is_finite() and ask.is_finite() and 0 < bid <= ask):
            continue
        observations.append(dict(symbol=symbol, supporters=pos['strategy_support'],
            bid=str(bid), ask=str(ask), quote_received_utc=pos.get('quote_received_utc'),
            quote_age_seconds=age_seconds(pos.get('quote_received_utc')),
            spread_bps=str((ask-bid)/((ask+bid)/2)*10000),
            same_book_ask_to_bid_loss_pct=str((1-bid/ask)*100)))
    liquidity_path = base / 'zitar_liquidity_profile_v1.json'
    liquidity = read(liquidity_path) if liquidity_path.exists() else {}
    report = dict(schema='ZITAR_COST_LIQUIDITY_STUDY_V1', study_id=study_id, generated_utc=stamp(),
                  topic='ZITAR strategies: paper costs and liquidity impact', model=model,
                  model_scope='Configured Master paper model; not exchange fee schedule',
                  assumptions=['Unchanged reference price for flat-price loss',
                               'Continuous quantity; actual engine rounds quantity and TRY',
                               'Spread observations are separate; do not blindly add to modeled slippage',
                               'No profitability or strategy-ranking conclusion without matched trade replay'],
                  master_sha256=hashlib.sha256(raw).hexdigest(), engine_sha256=engine_hash,
                  open_position_observations=observations,
                  historical_liquidity={'generated_utc':liquidity.get('generated_utc'),
                    'observation_count':liquidity.get('observation_count'),
                    'coverage':{o['symbol']: liquidity.get('symbols',{}).get(o['symbol']) for o in observations},
                    'scope':'Historical sample only; not current executable depth'},
                  next_required='MATCHED_STRATEGY_TRADE_REPLAY_AND_FRESH_DEPTH',
                  execution_authority=False)
    trade_path = base/'multistrategy_live_trades_v3.csv'
    if trade_path.exists():
        trade_bytes = trade_path.read_bytes()
        trades = list(csv.DictReader(io.StringIO(trade_bytes.decode('utf-8-sig'))))
        report['v3_trade_costs'] = trade_costs(trades)
        report['v3_trades_sha256'] = hashlib.sha256(trade_bytes).hexdigest()
        from zitar_cost_replay_v1 import replay, observe_depth
        report['matched_replay'] = replay(trades)
        config_path=base/'zitar_research_automation_v1.json'
        if config_path.exists() and read(config_path).get('depth_enabled') is True:
            depth_path=base/'zitar_research_depth_v1.json'
            depth=read(depth_path) if depth_path.exists() else {}
            if not depth or age_seconds(depth.get('checked_utc')) is None or age_seconds(depth['checked_utc'])>=300:
                history=depth.get('history',[])
                symbols=set(master['account']['positions'])|{t['symbol'] for t in trades if t['side']=='SELL'}
                depth={'checked_utc':stamp(),'sample_interval_seconds':300,
                       'scope':'Master open positions and symbols with closed V3 trades',
                       'symbols':observe_depth(symbols,[master['current_period']['spot_slot_budget_try'],'5000','10000'],model['fee_rate'])}
                depth['history']=(history+[{'checked_utc':depth['checked_utc'],
                    'symbols':{s:{'status':v['status'],'spread_bps':v.get('analysis',{}).get('spread_bps')}
                               for s,v in depth['symbols'].items()}}])[-288:]
                atomic(depth_path,json.dumps(depth,ensure_ascii=False,indent=2).encode())
            report['depth_observation']=depth
        report['next_required']='LONGER_MATCHED_SAMPLE_AND_DEPTH_HISTORY'
    atomic(base/'zitar_cost_liquidity_study_v1.json', json.dumps(report,ensure_ascii=False,indent=2).encode())
    # Persist only stable, deterministic model results once; quotes remain observations.
    guard = FileLock(base/'zitar_research_memory_writer.lock')
    if not guard.acquire():
        raise ValueError('MEMORY_WRITER_BUSY')
    try:
        journal = base/'zitar_core_learning_journal_v1.jsonl'
        before = journal.read_bytes()
        records = rows(journal)
        check_chain(records)
        if not any(r.get('study_id') == study_id for r in records):
            rec = dict(schema='ZITAR_CORE_LEARNING_JOURNAL_V2', domain='ZITAR_CORE',
                       lesson_type='LOCAL_COST_MODEL_MEASUREMENT', study_id=study_id,
                       topic='ZITAR paper işlem maliyetleri',
                       observation='Configured fee/slippage model analyzed algebraically; no strategy profitability conclusion.',
                       claims=[{'claim': f"Master model: fee={model['fee_rate']}, slippage={model['slippage_rate']}; "
                                f"unchanged-reference roundtrip loss={model['flat_reference_roundtrip_loss_pct']}%; "
                                f"reference breakeven rise={model['reference_breakeven_rise_pct']}% before rounding."}],
                       evidence={'model':model,'engine_sha256':engine_hash,'formula_version':1},
                       outcome='LOCAL_MODEL_MEASUREMENT_NOT_MARKET_FACT', created_utc=stamp(), version=2,
                       previous_record_sha256=records[-1]['record_sha256'] if records else None,
                       execution_authority=False, silent_code_rewrite_authority=False)
            rec['record_sha256'] = sha(rec)
            check_chain(records+[rec])
            atomic(journal,before+(b'\n' if before and not before.endswith(b'\n') else b'')+
                   (json.dumps(rec,ensure_ascii=False)+'\n').encode(),before)
    finally:
        guard.close()
    return report




def load_web_snapshot_source(base, web_source):
    """Load and verify one immutable web evidence snapshot for corroboration."""
    if not isinstance(web_source, dict):
        raise ValueError('INVALID_WEB_SOURCE')

    if web_source.get('status') != 'FETCHED_NOT_FACT_CHECKED':
        raise ValueError('WEB_SOURCE_NOT_FETCHED')

    snapshot_name = web_source.get('snapshot')
    if not isinstance(snapshot_name, str) or not snapshot_name:
        raise ValueError('SNAPSHOT_REQUIRED')

    # Snapshot references are filenames only. Do not allow traversal or
    # arbitrary filesystem reads through research metadata.
    if Path(snapshot_name).name != snapshot_name:
        raise ValueError('INVALID_SNAPSHOT_NAME')

    snapshot_path = (
        Path(base) /
        'zitar_web_evidence_cache_v1' /
        snapshot_name
    )

    if not snapshot_path.is_file():
        raise ValueError('SNAPSHOT_NOT_FOUND')

    snapshot = read(snapshot_path)

    snapshot_text = snapshot.get('text')
    if not isinstance(snapshot_text, str) or not snapshot_text:
        raise ValueError('SOURCE_SNAPSHOT_REQUIRED')

    actual_text_sha256 = hashlib.sha256(
        snapshot_text.encode('utf-8')
    ).hexdigest()

    if actual_text_sha256 != snapshot.get('text_sha256'):
        raise ValueError('SNAPSHOT_TEXT_HASH_MISMATCH')

    provenance_fields = (
        'url',
        'final_url',
        'response_sha256',
        'role',
        'provider_family',
        'policy_reason',
    )

    for field in provenance_fields:
        if web_source.get(field) != snapshot.get(field):
            raise ValueError('SNAPSHOT_PROVENANCE_MISMATCH')

    return {
        'role': snapshot.get('role'),
        'provider': snapshot.get('provider_family'),
        'provider_family': snapshot.get('provider_family'),
        'policy_reason': snapshot.get('policy_reason'),
        'url': snapshot.get('final_url') or snapshot.get('url'),
        'final_url': snapshot.get('final_url'),
        'status': 'FETCHED_NOT_FACT_CHECKED',
        'snapshot_text': snapshot_text,
        'content_sha256': snapshot.get('text_sha256'),
        'response_sha256': snapshot.get('response_sha256'),
        'http_status': 200,
        'error': None,
        'retrieved_utc': snapshot.get('retrieved_utc'),
        'extraction': snapshot.get('extraction'),
        'snapshot': snapshot_name,
    }


def web_claim_semantic_equivalent(a, b):
    """
    Deterministic fail-closed semantic equivalence for explicitly
    allowlisted market-structure definitions.

    No model, embedding, paraphrase generation or open-ended inference
    is used here.
    """
    if not isinstance(a, str) or not isinstance(b, str):
        return False

    def normalize(value):
        value = value.casefold()
        value = value.replace("bid-ask", "bid ask")
        value = value.replace('"', " ")
        value = value.replace("?", " ").replace("?", " ")
        value = value.replace("'", " ")
        value = value.replace(".", " ")
        value = value.replace(",", " ")
        value = value.replace(";", " ")
        value = value.replace(":", " ")
        value = value.replace("(", " ").replace(")", " ")
        return " ".join(value.split())

    na = normalize(a)
    nb = normalize(b)

    if not na or not nb:
        return False

    # Exact normalized equality is safe.
    if na == nb:
        return True

    def spread_definition_signature(value):
        tokens = set(value.split())

        required = {
            "bid",
            "ask",
            "spread",
            "difference",
            "price",
        }

        if not required.issubset(tokens):
            return None

        # Both statements must describe spread as the difference
        # involving bid and ask prices. Merely mentioning the terms is
        # deliberately insufficient.
        relation_markers = (
            "difference between",
            "spread is the difference",
            "spread represents the difference",
            "called the spread",
        )

        if not any(marker in value for marker in relation_markers):
            return None

        return "BID_ASK_SPREAD_DEFINITION_V1"

    sa = spread_definition_signature(na)
    sb = spread_definition_signature(nb)

    return bool(sa and sb and sa == sb)


def corroborate_web_claim_semantically(claim, sources):
    """
    Corroborate a literal PRIMARY claim against a semantically equivalent
    INDEPENDENT source under the existing provider-family policy.

    PRIMARY support remains literal. Only the independent comparison may
    use the deterministic allowlisted semantic matcher.
    """
    from zitar_source_policy_v1 import corroboration_allowed

    if not isinstance(claim, str) or not claim.strip():
        raise ValueError("INVALID_CLAIM")

    if not isinstance(sources, list):
        raise ValueError("INVALID_SOURCES")

    valid_sources = []

    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("INVALID_SOURCE")

        snapshot_text = source.get("snapshot_text")
        content_sha256 = source.get("content_sha256")

        if not isinstance(snapshot_text, str) or not snapshot_text:
            raise ValueError("SOURCE_SNAPSHOT_REQUIRED")

        actual_sha256 = hashlib.sha256(
            snapshot_text.encode("utf-8")
        ).hexdigest()

        if actual_sha256 != content_sha256:
            raise ValueError("SOURCE_CONTENT_HASH_MISMATCH")

        if source.get("status") != "FETCHED_NOT_FACT_CHECKED":
            continue

        if source.get("error") is not None:
            continue

        if not source.get("provider_family"):
            raise ValueError("SOURCE_PROVIDER_FAMILY_REQUIRED")

        if not source.get("policy_reason"):
            raise ValueError("SOURCE_POLICY_REASON_REQUIRED")

        valid_sources.append(source)

    primary = [
        source
        for source in valid_sources
        if source.get("role") == "PRIMARY"
        and claim in source["snapshot_text"]
    ]

    if not primary:
        return {
            "status": "PRIMARY_LITERAL_SUPPORT_REQUIRED",
            "corroborated": False,
            "provider_families": [],
        }

    independent = [
        source
        for source in valid_sources
        if source.get("role") == "INDEPENDENT"
        and web_claim_semantic_equivalent(
            claim,
            source["snapshot_text"],
        )
    ]

    if not independent:
        return {
            "status": "INDEPENDENT_SEMANTIC_SUPPORT_REQUIRED",
            "corroborated": False,
            "provider_families": sorted({
                source["provider_family"]
                for source in primary
            }),
        }

    allowed_pairs = [
        (a, b)
        for a in primary
        for b in independent
        if corroboration_allowed(a, b)
    ]

    if not allowed_pairs:
        return {
            "status": "INDEPENDENT_PROVIDER_FAMILY_REQUIRED",
            "corroborated": False,
            "provider_families": sorted({
                source["provider_family"]
                for source in primary + independent
            }),
        }

    families = sorted({
        source["provider_family"]
        for pair in allowed_pairs
        for source in pair
    })

    return {
        "status": "SEMANTICALLY_CORROBORATED",
        "corroborated": True,
        "provider_families": families,
        "semantic_rule": "BID_ASK_SPREAD_DEFINITION_V1",
        "model_inference": False,
    }


def corroborate_web_claim(claim, sources):
    """Validate exact literal support across approved independent provider families."""
    from zitar_source_policy_v1 import corroboration_allowed

    if not isinstance(claim, str) or not claim.strip():
        raise ValueError('INVALID_CLAIM')

    if not isinstance(sources, list):
        raise ValueError('INVALID_SOURCES')

    valid_sources = []

    for source in sources:
        if not isinstance(source, dict):
            raise ValueError('INVALID_SOURCE')

        snapshot_text = source.get('snapshot_text')
        content_sha256 = source.get('content_sha256')

        if not isinstance(snapshot_text, str) or not snapshot_text:
            raise ValueError('SOURCE_SNAPSHOT_REQUIRED')

        actual_sha256 = hashlib.sha256(
            snapshot_text.encode('utf-8')
        ).hexdigest()

        if actual_sha256 != content_sha256:
            raise ValueError('SOURCE_CONTENT_HASH_MISMATCH')

        if source.get('status') != 'FETCHED_NOT_FACT_CHECKED':
            continue

        if source.get('error') is not None:
            continue

        if not source.get('provider_family'):
            raise ValueError('SOURCE_PROVIDER_FAMILY_REQUIRED')

        if not source.get('policy_reason'):
            raise ValueError('SOURCE_POLICY_REASON_REQUIRED')

        valid_sources.append(source)

    primary = [
        source for source in valid_sources
        if source.get('role') == 'PRIMARY'
        and claim in source['snapshot_text']
    ]

    independent = [
        source for source in valid_sources
        if source.get('role') == 'INDEPENDENT'
        and claim in source['snapshot_text']
    ]

    if not primary:
        return {
            'status': 'PRIMARY_LITERAL_SUPPORT_REQUIRED',
            'corroborated': False,
            'provider_families': [],
        }

    if not independent:
        return {
            'status': 'INDEPENDENT_LITERAL_SUPPORT_REQUIRED',
            'corroborated': False,
            'provider_families': sorted({
                source['provider_family']
                for source in primary
            }),
        }

    allowed_pairs = [
        (a, b)
        for a in primary
        for b in independent
        if corroboration_allowed(a, b)
    ]

    if not allowed_pairs:
        return {
            'status': 'INDEPENDENT_PROVIDER_FAMILY_REQUIRED',
            'corroborated': False,
            'provider_families': sorted({
                source['provider_family']
                for source in primary + independent
            }),
        }

    families = sorted({
        source['provider_family']
        for pair in allowed_pairs
        for source in pair
    })

    return {
        'status': 'CORROBORATED',
        'corroborated': True,
        'provider_families': families,
    }



def web_claim_quality_allowed(claim, claim_class):
    """
    Conservative quality gate for literal web claims.

    This gate does not infer, paraphrase, repair or complete source text.
    It only decides whether an already-literal source fragment is suitable
    for later controlled corroboration.
    """
    allowed_classes = {
        'GENERAL_MARKET_STRUCTURE',
        'EXCHANGE_SPECIFIC',
    }

    if claim_class not in allowed_classes:
        raise ValueError('UNKNOWN_CLAIM_CLASS')

    if not isinstance(claim, str):
        return False

    text = claim.strip()

    if not text:
        return False

    # Tiny headings / labels are not factual claims.
    if len(text) < 35:
        return False

    lowered = text.casefold()

    # Common navigation / chrome fragments observed in real snapshots.
    navigation_markers = (
        'main navigation',
        'skip to main content',
        'login for industry professionals',
        'finpro gateway',
        'check system status',
        'rules & guidance',
        'utility menu',
    )

    if any(marker in lowered for marker in navigation_markers):
        return False

    # Broken decimal / percentage fragments produced by naive sentence
    # splitting, e.g. "%0." from "%0.10".
    if text.endswith('.') and len(text) >= 3:
        before_dot = text[:-1].rstrip()

        if before_dot:
            token = before_dot.split()[-1]

            if token.startswith('%') and token[1:].isdigit():
                return False

    # Do not silently repair unbalanced quotation marks.
    straight_quotes = text.count('"')
    left_curly = text.count('?')
    right_curly = text.count('?')

    if straight_quotes % 2 != 0:
        return False

    if left_curly != right_curly:
        return False

    if claim_class == 'GENERAL_MARKET_STRUCTURE':
        concepts = (
            'bid',
            'ask',
            'spread',
            'liquidity',
        )

        if not any(concept in lowered for concept in concepts):
            return False

    elif claim_class == 'EXCHANGE_SPECIFIC':
        concepts = (
            'komisyon',
            'i?lem ?creti',
            'i?lem ?cret',
            'piyasa al?c?',
            'piyasa yap?c?',
            'maker',
            'taker',
        )

        if not any(concept.casefold() in lowered for concept in concepts):
            return False

    return True


def extract_controlled_web_claims(text, provider_family, role):
    """
    Extract only literal, source-backed atomic claims from approved
    provider families.

    This stage deliberately performs no semantic inference and no
    cross-domain synthesis.
    """
    approved_families = {'BINANCE', 'SEC', 'FINRA', 'CME_GROUP'}
    approved_roles = {'PRIMARY', 'INDEPENDENT'}

    if provider_family not in approved_families:
        raise ValueError('UNAPPROVED_PROVIDER_FAMILY')

    if role not in approved_roles:
        raise ValueError('INVALID_SOURCE_ROLE')

    if not isinstance(text, str) or not text.strip():
        return []

    if provider_family == 'BINANCE':
        claim_class = 'EXCHANGE_SPECIFIC'
        terms = (
            'komisyon',
            'i?lem ?creti',
            'i?lem ?cret',
            'piyasa al?c?',
            'piyasa yap?c?',
            'maker',
            'taker',
        )
    else:
        claim_class = 'GENERAL_MARKET_STRUCTURE'
        terms = (
            'bid',
            'ask',
            'spread',
            'liquidity',
        )

    # Controlled sentence segmentation only.  The returned claim is always
    # an exact substring of the source text; it is never paraphrased.
    sentences = []
    start = 0

    for index, char in enumerate(text):
        if char in '.!?':
            end = index + 1
            sentence = text[start:end].strip()
            if sentence:
                sentences.append(sentence)
            start = end

    tail = text[start:].strip()
    if tail:
        sentences.append(tail)

    claims = []
    seen = set()

    for sentence in sentences:
        lowered = sentence.casefold()

        if not any(term.casefold() in lowered for term in terms):
            continue

        # Defensive invariant: extraction may trim surrounding whitespace,
        # but it may never manufacture source language.
        if sentence not in text:
            raise ValueError('NON_LITERAL_CLAIM')

        if sentence in seen:
            continue

        seen.add(sentence)

        claims.append({
            'claim': sentence,
            'claim_class': claim_class,
            'provider_family': provider_family,
            'role': role,
            'inferred': False,
        })

    return claims



def controlled_web_claim_pipeline(sources):
    if not isinstance(sources, list):
        raise ValueError('INVALID_WEB_SOURCES')

    claims = []

    def add_candidate(source, claim_text, claim_class):
        snapshot_text = source.get('snapshot_text', '')

        if not isinstance(claim_text, str):
            return

        claim_text = claim_text.strip()

        # Absolute invariant: never manufacture source language.
        if not claim_text or claim_text not in snapshot_text:
            return

        if not web_claim_quality_allowed(claim_text, claim_class):
            return

        item = {
            'claim': claim_text,
            'claim_class': claim_class,
            'provider_family': source.get('provider_family'),
            'role': source.get('role'),
            'source_role': source.get('role'),
            'source_url': source.get('url'),
            'inferred': False,
        }

        key = (
            item['claim'],
            item['provider_family'],
            item['source_role'],
            item['source_url'],
        )

        for existing in claims:
            existing_key = (
                existing['claim'],
                existing.get('provider_family'),
                existing.get('source_role'),
                existing.get('source_url'),
            )
            if existing_key == key:
                return

        claims.append(item)

    def literal_market_candidates(snapshot_text):
        """
        Return only exact source substrings.

        This adapter recognizes narrowly controlled bid/ask/spread
        statements. It performs no paraphrase or semantic inference.
        """
        anchors = (
            'The difference between the bid price and the ask price',
            'The bid ask spread',
            'The bid-ask spread',
        )

        results = []

        for anchor in anchors:
            search_from = 0

            while True:
                pos = snapshot_text.find(anchor, search_from)

                if pos < 0:
                    break

                # Find sentence-ending punctuation after the literal anchor.
                punctuation = []

                for mark in '.!?':
                    mark_pos = snapshot_text.find(mark, pos)
                    if mark_pos >= 0:
                        punctuation.append(mark_pos)

                if punctuation:
                    stop = min(punctuation) + 1

                    # Preserve a closing quotation mark immediately following
                    # the punctuation.
                    while (
                        stop < len(snapshot_text)
                        and snapshot_text[stop] in '"\'??'
                    ):
                        stop += 1

                    candidate = snapshot_text[pos:stop].strip()
                else:
                    candidate = snapshot_text[pos:].strip()

                lowered = candidate.casefold()

                if (
                    'bid' in lowered
                    and 'ask' in lowered
                    and 'spread' in lowered
                    and candidate in snapshot_text
                ):
                    results.append(candidate)

                search_from = pos + len(anchor)

        return results

    for source in sources:
        if not isinstance(source, dict):
            raise ValueError('INVALID_WEB_SOURCE')

        family = source.get('provider_family')
        role = source.get('role')
        snapshot_text = source.get('snapshot_text')

        if not family or not role:
            raise ValueError('SOURCE_PROVENANCE_REQUIRED')

        if not isinstance(snapshot_text, str) or not snapshot_text:
            continue

        # Existing family-specific controlled extractor remains authoritative.
        extracted = extract_controlled_web_claims(
            snapshot_text,
            family,
            role,
        )

        for claim in extracted:
            if claim.get('inferred') is not False:
                continue

            add_candidate(
                source,
                claim.get('claim', ''),
                claim.get('claim_class'),
            )

        # Narrow literal adapter for general bid/ask/spread statements.
        for candidate in literal_market_candidates(snapshot_text):
            add_candidate(
                source,
                candidate,
                'GENERAL_MARKET_STRUCTURE',
            )

    verified_claims = []
    seen = set()

    for item in claims:
        claim_text = item['claim']

        if claim_text in seen:
            continue

        seen.add(claim_text)

        # Stage 1: exact literal corroboration.
        #
        # Pass the complete source set because corroborate_web_claim()
        # performs its own integrity, status, role and provider-policy
        # validation.
        result = corroborate_web_claim(
            claim_text,
            sources,
        )

        corroboration_mode = None

        if result.get('corroborated') is True:
            corroboration_mode = 'LITERAL'

        # Stage 2: narrowly allowlisted deterministic semantic fallback.
        #
        # Only GENERAL_MARKET_STRUCTURE claims are eligible. Exchange-
        # specific claims such as fees must never acquire cross-domain
        # semantic support from generic market-structure material.
        elif item.get('claim_class') == 'GENERAL_MARKET_STRUCTURE':
            semantic_result = corroborate_web_claim_semantically(
                claim_text,
                sources,
            )

            if semantic_result.get('corroborated') is True:
                result = semantic_result
                corroboration_mode = 'DETERMINISTIC_SEMANTIC'

        if corroboration_mode is not None:
            verified_claims.append({
                'claim': claim_text,
                'claim_class': item.get('claim_class'),
                'inferred': False,
                'corroboration_mode': corroboration_mode,
                'corroboration': result,
            })

    corroborated = bool(verified_claims)

    return {
        'claims': claims,
        'verified_claims': verified_claims,
        'corroborated': corroborated,
        'learning_ready': corroborated,
        'authorities': {
            'persistent_memory_write': False,
            'real_order': False,
            'silent_code_rewrite': False,
        },
    }




def apply_controlled_web_learning(sources):
    """
    Run the controlled web-learning validation pipeline.

    This function may produce verified learning candidates only.
    It never grants trading/order execution authority.
    """
    if not isinstance(sources, list):
        raise ValueError('INVALID_WEB_SOURCES')

    if not sources:
        return {
            'status': 'NO_CONTROLLED_WEB_EVIDENCE',
            'claims': [],
            'verified_claims': [],
            'corroborated': False,
            'learning_ready': False,
            'execution_authority': False,
        }

    pipeline = controlled_web_claim_pipeline(sources)

    claims = list(pipeline.get('claims', []))
    verified_claims = list(pipeline.get('verified_claims', []))
    corroborated = bool(pipeline.get('corroborated', False))
    learning_ready = bool(
        corroborated
        and verified_claims
        and pipeline.get('learning_ready', False)
    )

    return {
        'status': (
            'VALIDATED_CANDIDATE'
            if learning_ready
            else 'EVIDENCE_NOT_CORROBORATED'
        ),
        'claims': claims,
        'verified_claims': verified_claims,
        'corroborated': corroborated,
        'learning_ready': learning_ready,

        # Research/learning must remain completely separated
        # from order execution authority.
        'execution_authority': False,
    }


def web_cycle(base):
    config_path = base/'zitar_research_automation_v1.json'
    if not config_path.exists():
        return {'status':'NOT_CONFIGURED'}

    config = read(config_path)
    if config.get('web_enabled') is not True:
        return {'status':'DISABLED'}

    from zitar_web_research_v1 import research

    path = base/'zitar_web_research_v1.json'
    previous = read(path) if path.exists() else {}

    # Backward compatibility:
    # V1 configurations may contain one "web_job".
    # New configurations may contain multiple isolated "web_jobs".
    if 'web_jobs' in config:
        jobs = config['web_jobs']
        if not isinstance(jobs, list) or not jobs:
            raise ValueError('INVALID_WEB_JOBS')
    elif 'web_job' in config:
        jobs = [config['web_job']]
    else:
        raise ValueError('WEB_JOB_NOT_CONFIGURED')

    if not all(isinstance(job, dict) and job.get('id') for job in jobs):
        raise ValueError('INVALID_WEB_JOB')

    job_ids = [job['id'] for job in jobs]
    if len(job_ids) != len(set(job_ids)):
        raise ValueError('DUPLICATE_WEB_JOB_ID')

    config_id = sha(jobs if 'web_jobs' in config else config['web_job'])
    interval = 21600 if previous.get('status') == 'EVIDENCE_COLLECTED' else 1800

    if (previous and
            previous.get('config_sha256') == config_id and
            age_seconds(previous.get('checked_utc')) is not None and
            age_seconds(previous['checked_utc']) < interval):
        return previous

    job_results = [
        research(job, base/'zitar_web_evidence_cache_v1')
        for job in jobs
    ]

    # Preserve the historical single-job result shape.
    if len(jobs) == 1 and 'web_jobs' not in config:
        result = job_results[0]
    else:
        sources = []
        errors = []
        discovered = []

        for job_result in job_results:
            sources.extend(job_result.get('sources', []))
            errors.extend(job_result.get('errors', []))
            discovered.extend(job_result.get('discovered', []))

        statuses = [job_result.get('status') for job_result in job_results]

        if statuses and all(status == 'EVIDENCE_COLLECTED' for status in statuses):
            status = 'EVIDENCE_COLLECTED'
        elif any(status in ('EVIDENCE_COLLECTED', 'PARTIAL_EVIDENCE')
                 for status in statuses):
            status = 'PARTIAL_EVIDENCE'
        else:
            status = 'RETRY_REQUIRED'

        result = {
            'checked_utc': stamp(),
            'status': status,
            'jobs': job_results,
            'sources': sources,
            'discovered': discovered,
            'errors': errors,
            # Collection alone never promotes knowledge.
            'verified_claims': [],
            'learning_ready': False,
            'reason': (
                'Multiple research jobs collected evidence candidates; '
                'corroboration is a separate validation stage.'
            ),
            'execution_authority': False,
        }

    result['config_sha256'] = config_id

    old = {
        s['url']: s.get('response_sha256')
        for s in previous.get('sources', [])
        if s.get('url')
    }

    for source in result.get('sources', []):
        if source.get('response_sha256'):
            source['change_status'] = (
                'FIRST_OBSERVATION'
                if source.get('url') not in old
                else (
                    'UNCHANGED'
                    if old[source['url']] == source['response_sha256']
                    else 'CHANGED'
                )
            )

    result['refresh_seconds'] = (
        21600 if result['status'] == 'EVIDENCE_COLLECTED' else 1800
    )

    # ------------------------------------------------------------
    # Controlled web-learning integration.
    #
    # Raw fetched web sources are never promoted directly.
    # Every usable source must first pass immutable snapshot,
    # content-hash and provenance verification.
    # ------------------------------------------------------------
    adapted_sources = []
    adaptation_errors = []

    for web_source in result.get('sources', []):
        if web_source.get('status') != 'FETCHED_NOT_FACT_CHECKED':
            continue

        try:
            adapted_sources.append(
                load_web_snapshot_source(base, web_source)
            )
        except (ValueError, OSError, KeyError) as exc:
            adaptation_errors.append({
                'url': web_source.get('final_url') or web_source.get('url'),
                'error': str(exc),
            })

    try:
        controlled = apply_controlled_web_learning(adapted_sources)
    except (ValueError, OSError, KeyError) as exc:
        controlled = {
            'status': 'CONTROLLED_LEARNING_BLOCKED',
            'claims': [],
            'verified_claims': [],
            'corroborated': False,
            'learning_ready': False,
            'execution_authority': False,
            'error': str(exc),
        }

    result['controlled_learning'] = {
        'status': controlled.get('status'),
        'adapted_source_count': len(adapted_sources),
        'adaptation_errors': adaptation_errors,
        'claim_count': len(controlled.get('claims', [])),
        'verified_claim_count': len(
            controlled.get('verified_claims', [])
        ),
        'corroborated': bool(
            controlled.get('corroborated', False)
        ),
        'learning_ready': bool(
            controlled.get('learning_ready', False)
        ),
        'execution_authority': False,
    }

    result['verified_claims'] = list(
        controlled.get('verified_claims', [])
    )

    result['learning_ready'] = bool(
        controlled.get('learning_ready', False)
    )

    # Hard safety invariant:
    # research evidence can never grant trading authority.
    result['execution_authority'] = False

    result['history'] = (
        previous.get('history', []) +
        [{
            'checked_utc': result['checked_utc'],
            'status': result['status'],
            'source_hashes': [
                s.get('response_sha256')
                for s in result.get('sources', [])
            ],
        }]
    )[-120:]

    atomic(
        path,
        json.dumps(result, ensure_ascii=False, indent=2).encode()
    )
    return result


def age_seconds(value):
    return round((datetime.now(timezone.utc)-datetime.fromisoformat(value)).total_seconds(),1) if value else None


def trade_costs(trades):
    seen, totals = set(), {}
    for t in trades:
        if t['trade_id'] in seen:
            raise ValueError('DUPLICATE_SOURCE_TRADE')
        seen.add(t['trade_id'])
        q, ref, fill, fee, bid, ask = [Decimal(t[k]) for k in
            ('quantity','reference_price','modeled_fill_price','fee_try','observed_bid','observed_ask')]
        if not all(x.is_finite() for x in (q,ref,fill,fee,bid,ask)) or min(q,ref,fill,bid) <= 0 or ask < bid or fee < 0:
            raise ValueError('INVALID_TRADE_COST_INPUT')
        side = t['side']
        if side not in ('BUY','SELL'):
            raise ValueError('UNKNOWN_SIDE')
        acc = totals.setdefault(t['strategy'],dict(trades=0,sells=0,fee_try=Decimal(0),
             modeled_slippage_try=Decimal(0),spread_vs_mid_try=Decimal(0),closed_realized_try=Decimal(0)))
        acc['trades'] += 1
        acc['sells'] += side == 'SELL'
        acc['fee_try'] += fee
        acc['modeled_slippage_try'] += q*((fill-ref) if side=='BUY' else (ref-fill))
        mid=(bid+ask)/2
        acc['spread_vs_mid_try'] += q*((ref-mid) if side=='BUY' else (mid-ref))
        if side=='SELL':
            acc['closed_realized_try'] += Decimal(t['realized_pnl_try'])
    return {'scope':'Observed V3 executions at unchanged recorded quantities; not a counterfactual strategy backtest. Fees include open-position entries. Closed realized is separate.',
            'strategies':{name:{k:str(v) if isinstance(v,Decimal) else v for k,v in values.items()}
                          for name,values in totals.items()}}


def cycle(base):
    path = base / 'zitar_research_runtime_v1.json'
    state = read(path) if path.exists() else {'history': []}
    from zitar_market_memory_cycle_v1 import refresh
    refresh(base)
    jobs = local_jobs(base)
    known = {j['job_id'] for j in state['history']}
    state['history'].extend(j for j in jobs if j['job_id'] not in known)
    candidate_path = base / 'zitar_core_learning_candidate_v1.json'
    result = 'NO_CANDIDATE'
    if candidate_path.exists():
        try:
            result = promote(base, read(candidate_path), read(base / 'zitar_core_real_research_evidence_v1.json'))
        except (ValueError, OSError, KeyError) as exc:
            result = 'BLOCKED:' + str(exc)
    state.update(schema='ZITAR_RESEARCH_RUNTIME_V1', pid=os.getpid(), heartbeat_utc=stamp(),
                 state='WAITING_EVIDENCE' if jobs else 'IDLE', jobs=jobs, candidate_result=result,
                 authorities={'real_order': False, 'paper_order': False, 'modify_v3': False},
                 mode='LOCAL_EVIDENCE_AND_CONTROLLED_LEARNING')
    study = cost_study(base)
    from zitar_futures_paper_monitor_v1 import overview as futures_overview
    futures = futures_overview(base)
    study["futures_paper"] = {"state":futures["state"],"scope":"ISOLATED_3X_MODEL_NOT_EXCHANGE_PROOF","books":{name:{k:book.get(k) for k in ("equity","realized","funding_total","fees_total","max_drawdown_pct")} for name,book in futures["books"].items()}}
    try:
        from zitar_trade_context_v1 import report as trade_context_report
        study["trade_context"] = trade_context_report(base)
    except Exception as exc:
        study["trade_context"] = {"status":"ERROR", "reason":str(exc)}
    web = web_cycle(base)
    study['automatic_web']=web
    study['automatic_schedule']={'analysis_seconds':60,'depth_seconds':300,
                                  'web_seconds':web.get('refresh_seconds'),'checked_utc':stamp()}
    atomic(base/'zitar_cost_liquidity_study_v1.json',json.dumps(study,ensure_ascii=False,indent=2).encode())
    state['automatic_web']={'status':web['status'],'checked_utc':web.get('checked_utc'),
                            'learning_ready':web.get('learning_ready',False),'refresh_seconds':web.get('refresh_seconds')}
    state['active_study'] = {'study_id':study['study_id'], 'topic':study['topic'],
                             'status':'MATCHED_REPLAY_AND_DEPTH_OBSERVATION', 'next_required':study['next_required']}
    atomic(path, json.dumps(state, ensure_ascii=False, indent=2).encode())
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    guard = FileLock(args.base / 'zitar_research_runtime_v1.lock')
    if not guard.acquire():
        return
    try:
        if not args.once:
            from zitar_research_council_v1 import start_worker
            start_worker(args.base)
            from zitar_candidate_runtime_v1 import start_worker as start_candidate
            start_candidate(args.base)
            from zitar_futures_paper_runtime_v1 import start_worker as start_futures
            start_futures(args.base)
            from zitar_market_discovery_v1 import start_worker as start_discovery
            start_discovery(args.base)
            from zitar_discovery_spot_v1 import start_worker as start_discovery_spot
            start_discovery_spot(args.base)
        while True:
            started=time.monotonic()
            try:
                result = cycle(args.base)
                if args.once:
                    print(json.dumps(result, ensure_ascii=False))
                    return
            except Exception as exc:
                print(stamp(), repr(exc), flush=True)
                if args.once:
                    raise
                try:
                    path=args.base/'zitar_research_runtime_v1.json'
                    previous=read(path) if path.exists() else {}
                    previous.update(state='ERROR',heartbeat_utc=stamp(),pid=os.getpid(),last_error=str(exc))
                    atomic(path,json.dumps(previous,ensure_ascii=False,indent=2).encode())
                except Exception as write_error:
                    print(stamp(),repr(write_error),flush=True)
            time.sleep(max(1,60-(time.monotonic()-started)))
    finally:
        guard.close()


if __name__ == '__main__':
    main()
