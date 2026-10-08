from __future__ import annotations

import json
import re
from pathlib import Path


BASE = Path(__file__).resolve().parent

JOURNAL = BASE / "zitar_core_learning_journal_v1.jsonl"
OUT = BASE / "zitar_core_learning_journal_retrieval_test_v1.json"


ALIASES = {
    "ZITAR_CORE": {
        "zitar", "core", "çekirdek", "context", "bağlam",
        "hafıza", "memory", "öğren", "öğrendin", "gelişim",
        "kimlik", "benlik"
    },
    "GENERAL_RESEARCH": {
        "araştırma", "research", "öğren", "öğrendin",
        "doğrulama", "kaynak"
    }
}


STOP = {
    "ne", "nedir", "neler", "bundan", "bunu", "bu",
    "bir", "ve", "ile", "mi", "mı", "mu", "mü",
    "daha", "önce", "sonra", "şu", "an",
    "hakkında", "bana", "sen"
}


def norm(s):
    return re.sub(
        r"\s+",
        " ",
        str(s or "").strip().lower()
    )


def tokens(s):
    return {
        x
        for x in re.findall(
            r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9_]+",
            norm(s)
        )
        if x not in STOP and len(x) > 1
    }


def load():
    if not JOURNAL.exists():
        raise FileNotFoundError(
            f"Learning Journal bulunamadi: {JOURNAL}"
        )

    return [
        json.loads(x)
        for x in JOURNAL.read_text(
            encoding="utf-8"
        ).splitlines()
        if x.strip()
    ]


def claim_texts(row):
    out = []

    for item in row.get("claims") or []:

        if isinstance(item, dict):
            text = item.get("claim")

            if text:
                out.append(str(text))

        elif item:
            out.append(str(item))

    return out


def evidence_texts(row):
    out = []

    for item in row.get("evidence") or []:

        if isinstance(item, dict):
            out.append(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True
                )
            )

        elif item:
            out.append(str(item))

    return out


def searchable(row):

    # V1 + V2 backward-compatible searchable representation.
    return " ".join([
        str(row.get("domain", "")),
        str(row.get("lesson_type", "")),
        str(row.get("topic", "")),
        str(row.get("observation", "")),
        " ".join(claim_texts(row)),
        " ".join(evidence_texts(row)),
        str(row.get("prior_state", "")),
        str(row.get("updated_state", "")),
        str(row.get("outcome", "")),
        str(row.get("source", "")),
    ])


def public_hit(score, row):

    # Preserve fields required by both V1 and V2 consumers.
    return {
        "score": score,
        "schema": row.get("schema"),
        "domain": row.get("domain"),
        "lesson_type": row.get("lesson_type"),
        "topic": row.get("topic"),
        "observation": row.get("observation"),
        "claims": row.get("claims") or [],
        "prior_state": row.get("prior_state"),
        "updated_state": row.get("updated_state"),
        "outcome": row.get("outcome"),
        "source": row.get("source"),
        "created_utc": row.get("created_utc"),
    }


def retrieve(query, rows, top_k=3):

    q = norm(query)
    qt = tokens(query)

    scored = []

    for row in rows:

        searchable_text = searchable(row)
        rt = tokens(searchable_text)

        score = len(qt & rt)

        domain = row.get("domain", "")

        score += sum(
            4
            for alias in ALIASES.get(domain, set())
            if norm(alias) in q
        )

        # Explicit learning intent.
        if any(
            k in q
            for k in (
                "ne öğrendin",
                "neler öğrendin",
                "öğrendiğin",
                "gelişim"
            )
        ):
            score += 3

        # Strong topic match for V2 external learning.
        topic = norm(row.get("topic", ""))

        if topic and topic in q:
            score += 12

        # Exact query terms appearing in claims deserve extra weight.
        claims_blob = norm(
            " ".join(claim_texts(row))
        )

        claim_overlap = len(
            qt & tokens(claims_blob)
        )

        score += claim_overlap * 2

        if score > 0:
            scored.append(
                (score, row)
            )

    scored.sort(
        key=lambda x: (
            x[0],
            x[1].get("created_utc", "")
        ),
        reverse=True
    )

    return [
        public_hit(score, row)
        for score, row in scored[:top_k]
    ]


def synthesize_learning_answer(hits):

    if not hits:
        return {
            "status": "NO_SUPPORTED_LEARNING",
            "answer":
                "Bu soru için Learning Journal'da "
                "desteklenen bir öğrenme kaydı bulamadım."
        }

    parts = []

    for h in hits:

        claims = claim_texts(h)

        # V2 research learning.
        if claims:

            topic = h.get("topic")

            prefix = (
                f"{topic}: "
                if topic
                else ""
            )

            parts.append(
                prefix + " ".join(claims)
            )

            continue

        # Legacy V1 learning.
        observation = h.get("observation") or ""
        prior = h.get("prior_state") or ""
        updated = h.get("updated_state") or ""
        outcome = h.get("outcome") or ""

        text = observation

        if prior:
            text += f" Önceki durum: {prior}."

        if updated:
            text += f" Güncel durum: {updated}."

        if outcome:
            text += f" Sonuç: {outcome}."

        if text.strip():
            parts.append(text.strip())

    if not parts:
        return {
            "status": "NO_SUPPORTED_LEARNING",
            "answer":
                "Learning Journal kaydı bulundu ancak "
                "kullanılabilir doğrulanmış içerik yok."
        }

    return {
        "status": "SUPPORTED",
        "answer": " ".join(parts)
    }


TESTS = [
    ("Bundan ne öğrendin?", True),
    ("ZİTAR Core geliştirmelerinden ne öğrendin?", True),
    ("Context hatasından ne öğrendin?", True),
    ("Benlik yapın hakkında ne öğrendin?", True),
    ("Raspberry Pi 5 hakkında ne öğrendin?", True),
]


def main():

    rows = load()

    results = []
    passed = 0

    for query, should_find in TESTS:

        hits = retrieve(
            query,
            rows
        )

        answer = synthesize_learning_answer(
            hits
        )

        ok = (
            bool(hits) == should_find
        )

        if should_find:
            ok = (
                ok
                and answer["status"] == "SUPPORTED"
            )

        # Regression specifically proves V2 external learning recall.
        if query == "Raspberry Pi 5 hakkında ne öğrendin?":

            top = hits[0] if hits else {}

            ok = (
                ok
                and top.get("topic") == "Raspberry Pi 5"
                and bool(top.get("claims"))
            )

        passed += int(ok)

        results.append({
            "query": query,
            "hits": hits,
            "answer": answer,
            "pass": ok
        })

    payload = {
        "schema":
            "ZITAR_CORE_LEARNING_JOURNAL_RETRIEVAL_TEST_V1",
        "journal_records": len(rows),
        "tests": results,
        "passed": passed,
        "total": len(TESTS),
        "memory_write": False,
        "execution_authority": False,
        "llm_used": False,
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        "ZITAR CORE LEARNING JOURNAL "
        "RETRIEVAL V1"
    )

    print(
        "V1+V2 READ-ONLY • DETERMINISTIC • "
        "NO LLM • NO MEMORY WRITE"
    )

    print(
        "journal records:",
        len(rows)
    )

    for r in results:

        top = (
            r["hits"][0].get("topic")
            or r["hits"][0].get("lesson_type")
            if r["hits"]
            else "NONE"
        )

        print(
            f"{'PASS' if r['pass'] else 'FAIL':4} "
            f"| top={str(top):25} "
            f"| {r['query']}"
        )

    print(
        f"\nRESULT: {passed}/{len(TESTS)} PASS"
    )

    print(
        "output:",
        OUT
    )

    print(
        "STATUS:",
        "PASS"
        if passed == len(TESTS)
        else "FAIL"
    )


if __name__ == "__main__":
    main()
