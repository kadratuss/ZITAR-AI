from pathlib import Path
import json
import re
import urllib.request

from zitar_core_context_v1_2 import ConversationContext
from zitar_core_project_memory_retrieval_v2 import (
    load_records as load_project_records,
    retrieve as retrieve_project,
)
from zitar_core_learning_journal_retrieval_v1 import (
    load as load_learning_records,
    retrieve as retrieve_learning,
    synthesize_learning_answer,
)
from zitar_finance_unified_bridge_v1_1 import build as build_finance
from zitar_finance_grounded_renderer_v1 import render as render_finance


BASE = Path(__file__).resolve().parent

SESSIONS = {}


def norm(text):
    return re.sub(
        r"\s+",
        " ",
        (text or "").casefold()
    ).strip()


def get_session(session_id):

    sid = session_id or "default"

    if sid not in SESSIONS:
        SESSIONS[sid] = {
            "context": ConversationContext(),
            "history": [],
        }

    return SESSIONS[sid]


def looks_finance(question):

    q = norm(question)

    words = (
        "btc", "bitcoin", "eth", "ethereum",
        "usdt", "funding", "basis",
        "open interest", "long short",
        "taker", "vadeli", "futures",
        "piyasa", "sol", "solana"
    )

    return bool(re.search(r"\b[A-Z0-9]{2,12}(?:USDT|TRY)\b", question.upper())) or any(re.search(r"\b" + re.escape(x) + r"\b", q) for x in words)


def looks_learning(question):

    q = norm(question)

    words = (
        "ne öğrendin",
        "ne ogrendin",
        "öğrendiğin",
        "ogrendigin",
        "araştırmıştın",
        "arastirmistin",
        "araştırdın",
        "arastirdin"
    )

    return any(x in q for x in words)


def learning_hit_to_text(hit):

    if not isinstance(hit, dict):
        return str(hit)

    if "claims" in hit:
        claims = hit.get("claims") or []
        out = []

        for claim in claims:
            if isinstance(claim, dict):
                text = claim.get("claim")
                if text:
                    out.append(text)

        if out:
            return " ".join(out)

    for key in (
        "observation",
        "content",
        "updated_state"
    ):
        value = hit.get(key)
        if value:
            return str(value)

    return ""


def project_hit_to_text(hit):

    if not isinstance(hit, dict):
        return str(hit)

    return str(
        hit.get("content")
        or hit.get("observation")
        or ""
    )


def qwen_answer(question, context):

    prompt = f"""
Sen ZİTAR'sın.

SADECE aşağıdaki doğrulanmış bağlamı kullan.
Bağlamda olmayan bilgi ekleme.
Kullanıcıya doğal ve düzgün Türkçe cevap ver.
Teknik isimleri değiştirme.
Kanıt yetersizse açıkça söyle.

DOĞRULANMIŞ BAĞLAM:
{context}

KULLANICI:
{question}

ZİTAR:
""".strip()

    from zitar_model_provider_v1 import chat
    try:
        return chat([dict(role='user',content=prompt)],role='grounded_narration')
    except Exception:
        return context


def answer(question, session_id="default"):

    session = get_session(session_id)

    result = {
        "session_id": session_id,
        "question": question,
        "route": "UNKNOWN",
        "source": "NONE",
        "grounded": False,
        "answer": "",
    }

    # -------------------------------------------------
    # FINANCE
    # -------------------------------------------------

    if looks_finance(question):

        pairs = re.findall(r"\b[A-Z0-9]{2,12}(?:USDT|TRY)\b", question.upper())
        aliases = {"btc": "BTCUSDT", "bitcoin": "BTCUSDT", "eth": "ETHUSDT", "ethereum": "ETHUSDT", "sol": "SOLUSDT", "solana": "SOLUSDT"}
        requested = set(pairs)
        if not requested:
            requested = {pair for word, pair in aliases.items() if re.search(r"\b" + word + r"\b", norm(question))}
        if len(requested) != 1:
            result.update(route="CLARIFICATION", source="CORE_RUNTIME", answer="Hangi işlem çiftini inceleyelim? Örneğin BTCUSDT veya ETHUSDT.")
            return result
        symbol = requested.pop()
        result["symbol"] = symbol
        bridge = build_finance(symbol)
        text = render_finance(bridge)

        result.update({
            "route": "FINANCE_RESEARCH",
            "source": "FINANCE_DETERMINISTIC_RENDERER",
            "grounded": True,
            "answer": text,
        })

        session["history"].append(result)
        return result

    # -------------------------------------------------
    # LEARNING JOURNAL
    # -------------------------------------------------

    learning_rows = load_learning_records()

    learning_hits = retrieve_learning(
        question,
        learning_rows,
        top_k=3
    )

    if looks_learning(question) and learning_hits:

        # Verified Learning Journal evidence only.
        # No LLM generation is allowed in grounded recall.
        top_hit = learning_hits[0]

        text = learning_hit_to_text(
            top_hit
        ).strip()

        if text:

            result.update({
                "route": "LEARNING_RECALL",
                "source": "LEARNING_JOURNAL_DETERMINISTIC",
                "grounded": True,
                "answer": text,
            })

            session["history"].append(result)
            return result

    # -------------------------------------------------
    # PROJECT MEMORY
    # -------------------------------------------------

    project_rows = load_project_records()

    project_hits = retrieve_project(
        question,
        project_rows,
        top_k=1
    )

    if project_hits:

        # Verified Project Memory evidence only.
        # No LLM generation is allowed in grounded recall.
        top_hit = project_hits[0]

        text = project_hit_to_text(
            top_hit
        ).strip()

        if text:

            result.update({
                "route": "PROJECT_RECALL",
                "source": "PROJECT_MEMORY_DETERMINISTIC",
                "grounded": True,
                "answer": text,
            })

            session["history"].append(result)
            return result

    # -------------------------------------------------
    # NO GROUNDED ANSWER
    # -------------------------------------------------

    result.update({
        "route": "KNOWLEDGE_GAP",
        "source": "CORE_RUNTIME",
        "grounded": False,
        "answer":
            "Bu soru için mevcut doğrulanmış hafızamda "
            "yeterli kanıt bulamadım. Araştırma zincirine "
            "aktarılması gerekiyor."
    })

    session["history"].append(result)
    return result


