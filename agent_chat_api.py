import json
import re
import sqlite3
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_api import agent_history


router = APIRouter(prefix="/api/agent", tags=["agent-chat"])

ROOT = Path(__file__).resolve().parent
CHAT_DB = ROOT / "agent_chat.db"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:7b"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=100)


def init_chat_database():
    with sqlite3.connect(CHAT_DB) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # Her konuşmada en son hangi işlemden söz edildiğini saklar.
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_trade_context (
                session_id TEXT PRIMARY KEY,
                trade_id INTEGER NOT NULL
            )
            """
        )

        db.commit()


def load_messages(session_id):
    with sqlite3.connect(CHAT_DB) as db:
        rows = db.execute(
            """
            SELECT role, content
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT 8
            """,
            (session_id,),
        ).fetchall()

    return [
        {"role": role, "content": content}
        for role, content in reversed(rows)
    ]


def save_message(session_id, role, content):
    with sqlite3.connect(CHAT_DB) as db:
        db.execute(
            """
            INSERT INTO messages
                (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        db.commit()


def get_trade_context(session_id):
    with sqlite3.connect(CHAT_DB) as db:
        row = db.execute(
            """
            SELECT trade_id
            FROM chat_trade_context
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

    return int(row[0]) if row else None


def set_trade_context(session_id, trade_id):
    with sqlite3.connect(CHAT_DB) as db:
        db.execute(
            """
            INSERT INTO chat_trade_context (session_id, trade_id)
            VALUES (?, ?)
            ON CONFLICT(session_id)
            DO UPDATE SET trade_id = excluded.trade_id
            """,
            (session_id, int(trade_id)),
        )
        db.commit()


def normalize_question(text):
    text = text.casefold().replace("ı", "i")

    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )

    return re.sub(r"\s+", " ", text).strip()


def is_previous_trade_question(question):
    text = normalize_question(question)

    has_previous = re.search(
        r"\b(onceki|oncesi|once|evvelki|bir onceki)\b",
        text,
    ) is not None

    has_trade_reference = re.search(
        r"\b(islem\w*|alis\w*|satis\w*|trade\w*)\b",
        text,
    ) is not None

    # "Peki bundan önce ne yaptın?" gibi takip soruları.
    has_followup_reference = re.search(
        r"\b(bu|bundan|ondan|bunun|onun)\b",
        text,
    ) is not None

    return has_previous and (
        has_trade_reference or has_followup_reference
    )


def is_latest_trade_question(question):
    text = normalize_question(question)

    # Önceki işlem sorusunu yanlışlıkla "son işlem" sayma.
    if is_previous_trade_question(question):
        return False

    patterns = (
        r"\bson\b.{0,55}\bislem\w*",
        r"\ben son\b.{0,55}\balis\w*",
        r"\ben son\b.{0,55}\bsatis\w*",
        r"\bson\b.{0,55}\btrade\w*",
        r"\blast trade\b",
    )

    return any(
        re.search(pattern, text) is not None
        for pattern in patterns
    )


def trade_answer(trade, heading):
    side = {
        "BUY": "ALIŞ",
        "SELL": "SATIŞ",
    }.get(
        trade.get("side"),
        str(trade.get("side") or "Bilinmiyor"),
    )

    reason = trade.get("reason") or "Gerekçe kaydı bulunmuyor"
    pnl = trade.get("realized_pnl")

    return (
        f"{heading}: {side}\n"
        f"İşlem no: {trade.get('id')}\n"
        f"Parite: {trade.get('symbol')}\n"
        f"Zaman (UTC): {trade.get('created_at')}\n"
        f"Fiyat: {trade.get('price')} TRY\n"
        f"Miktar: {trade.get('quantity')}\n"
        f"Gerekçe: {reason}\n"
        f"Gerçekleşen K/Z kaydı: "
        f"{pnl if pnl is not None else 'Bulunmuyor'} TRY"
    )


def reply_from_record(session_id, question, trade, heading):
    answer = trade_answer(trade, heading)

    set_trade_context(session_id, trade["id"])
    save_message(session_id, "user", question)
    save_message(session_id, "assistant", answer)

    return {
        "session_id": session_id,
        "answer": answer,
        "mode": "paper_trading_read_only",
    }


@router.post("/chat")
def agent_chat(request: ChatRequest):
    question = request.message.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="Mesaj boş olamaz",
        )

    session_id = request.session_id or str(uuid4())

    # Ajanın işlem ve karar kayıtları yalnızca okunur.
    records = agent_history(limit=50)

    trades = records.get("trades") or []
    decisions = records.get("decisions") or []

    trades = sorted(
        trades,
        key=lambda item: int(item.get("id") or 0),
        reverse=True,
    )

    # "Bu satıştan önceki işlem" gibi takip soruları.
    if is_previous_trade_question(question):
        referenced_id = get_trade_context(session_id)

        if referenced_id is None:
            answer = (
                "Hangi işlemden öncesini sorduğunu belirleyemedim. "
                "Önce ilgili işlemi sorabilir veya işlem numarasını "
                "yazabilirsin."
            )
        else:
            previous_trade = next(
                (
                    trade
                    for trade in trades
                    if int(trade.get("id") or 0) < referenced_id
                ),
                None,
            )

            if previous_trade is None:
                answer = (
                    f"#{referenced_id} numaralı işlemden önceki "
                    "işlem, getirilen kayıtlar arasında bulunamadı."
                )
            else:
                return reply_from_record(
                    session_id,
                    question,
                    previous_trade,
                    f"#{referenced_id} numaralı işlemden önceki sanal işlem",
                )

        save_message(session_id, "user", question)
        save_message(session_id, "assistant", answer)

        return {
            "session_id": session_id,
            "answer": answer,
            "mode": "paper_trading_read_only",
        }

    # En güncel işlem sorularında model tahmin yürütmez.
    if is_latest_trade_question(question):
        if not trades:
            answer = "Kayıtlarda henüz sanal işlem bulunmuyor."

            save_message(session_id, "user", question)
            save_message(session_id, "assistant", answer)

            return {
                "session_id": session_id,
                "answer": answer,
                "mode": "paper_trading_read_only",
            }

        return reply_from_record(
            session_id,
            question,
            trades[0],
            "Son sanal işlem",
        )

    # Diğer sorular için serbest sohbet.
    previous_messages = load_messages(session_id)

    compact_records = {
        "latest_trade": trades[0] if trades else None,
        "recent_trades": trades[:8],
        "recent_decisions": decisions[:10],
        "conversation_trade_id": get_trade_context(session_id),
    }

    system_message = (
        "Sen PortfolioAI uygulamasının Türkçe sohbet asistanısın. "
        "Kullanıcı seninle serbestçe konuşabilir. "
        "Aşağıdaki kayıtlar gerçek ajanın SANAL işlem ve karar kayıtlarıdır. "
        "Gerçek para işlemi yapıldığını söyleme. "
        "latest_trade en güncel işlemdir. "
        "conversation_trade_id konuşmada en son doğrudan "
        "kayıttan yanıtlanan işlemin numarasıdır. "
        "Önceki sohbet mesajlarında farklı işlem bilgileri varsa "
        "güncel kayıtları esas al; önceki yanlış yanıtları tekrar etme. "
        "Kayıtlarda bulunmayan fiyat, işlem, gerekçe veya kâr bilgisi uydurma. "
        "Veri yetmiyorsa açıkça belirt. "
        "Gerçekleşen kâr/zarar alanı boşsa bunu kesin kâr veya zarar sayma. "
        "Kullanıcı başka bir konuda konuşursa da yardımcı ol; "
        "ancak genel bilgiyi ajan kaydıymış gibi gösterme. "
        "Emir veremezsin, strateji değiştiremezsin, kod çalıştıramazsın. "
        "Yanıtlarını doğal Türkçeyle, kısa ve anlaşılır yaz. "
        "Ham JSON dökme. Aynı bilgiyi veya hesabı tekrarlama. "
        "Markdown yıldızları kullanma. "
        "Kayıtlar dışındaki bir bilgiye erişimin olduğunu iddia etme.\n\n"
        "GÜNCEL AJAN KAYITLARI:\n"
        + json.dumps(
            compact_records,
            ensure_ascii=False,
            default=str,
        )
    )

    payload = {
        "model": MODEL,
        "stream": False,
        "messages": (
            [{"role": "system", "content": system_message}]
            + previous_messages
            + [{"role": "user", "content": question}]
        ),
        "options": {
            "temperature": 0.2,
            "num_ctx": 8192,
            "num_predict": 350,
        },
    }

    try:
        http_request = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(
                payload,
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8"
            },
            method="POST",
        )

        with urllib.request.urlopen(
            http_request,
            timeout=120,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        answer = result["message"]["content"].strip()

        if not answer:
            raise ValueError("Model boş yanıt verdi")

    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
    ):
        raise HTTPException(
            status_code=503,
            detail="Yerel sohbet modeli yanıt veremedi",
        )

    save_message(session_id, "user", question)
    save_message(session_id, "assistant", answer)

    return {
        "session_id": session_id,
        "answer": answer,
        "mode": "paper_trading_read_only",
    }


init_chat_database()