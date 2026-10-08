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
        "piyasa"
    )

    return any(x in q for x in words)


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

    payload = json.dumps({
        "model": "qwen2.5:7b",
        "prompt": prompt,
        "stream": False
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=60
        ) as response:

            data = json.loads(
                response.read().decode("utf-8")
            )

            text = (
                data.get("response") or ""
            ).strip()

            if text:
                return text

    except Exception:
        pass

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

        bridge = build_finance("BTCUSDT")
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

        context = " ".join(
            learning_hit_to_text(x)
            for x in learning_hits
        ).strip()

        if context:

            text = qwen_answer(
                question,
                context
            )

            result.update({
                "route": "LEARNING_RECALL",
                "source": "LEARNING_JOURNAL",
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

        context = "\n".join(
            project_hit_to_text(x)
            for x in project_hits
            if project_hit_to_text(x)
        )

        if context:

            text = qwen_answer(
                question,
                context
            )

            result.update({
                "route": "PROJECT_RECALL",
                "source": "PROJECT_MEMORY",
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


